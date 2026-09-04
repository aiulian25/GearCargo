"""Hash unsubscribe tokens at rest — R4-24.

The unsubscribe_token column stored the raw one-click-unsubscribe token, so a
database or backup leak yielded a working unsubscribe link for every user. S08
and R7 already gave the password-reset and e-mail-verification tokens the
SHA-256-at-rest treatment; this closes the last plaintext token.

Unlike those two, existing values are HASHED rather than nulled. A reset token
lives ≤24 h, so voiding it costs a user one click; an unsubscribe link sits in
inboxes indefinitely, and voiding it would break a link the user is entitled to
use. Hashing the current value keeps every already-delivered link working —
`sha256(raw)` still matches when the user clicks it.

Rows whose value is already a 64-char hex digest are skipped, so the migration
is idempotent.

No schema change: the column is String(64) and a SHA-256 hex digest is exactly
64 characters.

Revision ID: b7c8d9e0f1a2
Revises: z4a5b6c7d8e9
"""

import hashlib
import re

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'z4a5b6c7d8e9'
branch_labels = None
depends_on = None

# A value that is already a SHA-256 hex digest needs no work.
_SHA256_HEX = re.compile(r'^[0-9a-f]{64}$')

_BATCH_SIZE = 500


def upgrade():
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        'SELECT id, unsubscribe_token FROM users WHERE unsubscribe_token IS NOT NULL'
    )).fetchall()

    pending = [
        {'user_id': user_id,
         'hashed': hashlib.sha256(token.encode('utf-8')).hexdigest()}
        for user_id, token in rows
        if token and not _SHA256_HEX.match(token)
    ]

    statement = sa.text(
        'UPDATE users SET unsubscribe_token = :hashed WHERE id = :user_id'
    )
    for start in range(0, len(pending), _BATCH_SIZE):
        for parameters in pending[start:start + _BATCH_SIZE]:
            connection.execute(statement, parameters)


def downgrade():
    # A hash cannot be turned back into its token. Clearing the column is the
    # only honest reversal: the next e-mail mints a fresh link for each user.
    op.execute('UPDATE users SET unsubscribe_token = NULL')
