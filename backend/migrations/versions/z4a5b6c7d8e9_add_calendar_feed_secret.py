"""R8 — revocable ICS calendar feed links.

Feed URLs were plain 90-day JWTs with no jti and no server-side state, so a
leaked link could not be revoked: issuing a new one left the old one working
until it expired. Every feed token now carries a fingerprint of this per-user
secret; rotating the secret (DELETE /calendar/feed-token) invalidates every
outstanding link at once.

Nullable with no backfill: the secret is created lazily on the next
POST /calendar/feed-token. Tokens issued before this migration carry no
fingerprint and are rejected (fail closed) — subscribers re-copy the link once.

Revision ID: z4a5b6c7d8e9
Revises: y3z4a5b6c7d8
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'z4a5b6c7d8e9'
down_revision = 'y3z4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('calendar_feed_secret', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('calendar_feed_secret')
