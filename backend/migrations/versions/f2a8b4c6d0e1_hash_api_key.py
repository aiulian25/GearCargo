"""Hash API key — S07: replace plaintext api_key with SHA-256 hash + 8-char prefix.

The raw api_key value is never stored; only sha256(api_key) is kept. Existing rows
are migrated in Python to avoid a pgcrypto dependency.  After migration the old
api_key column is kept (nullable) so the column can be dropped in a future cleanup
migration without touching this one's upgrade/downgrade logic.

Revision ID: f2a8b4c6d0e1
Revises: e7f5a3c1d892
Create Date: 2025-01-01 00:00:00.000000
"""

import hashlib

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers
revision = 'f2a8b4c6d0e1'
down_revision = 'e7f5a3c1d892'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Add new columns
    op.add_column('users', sa.Column('api_key_hash', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('api_key_prefix', sa.String(12), nullable=True))

    # 2. Migrate existing plaintext api_key values → hash + prefix (Python loop, no pgcrypto)
    rows = conn.execute(text("SELECT id, api_key FROM users WHERE api_key IS NOT NULL")).fetchall()
    for row in rows:
        raw_key = row[1]
        hashed = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
        prefix = raw_key[:8]
        conn.execute(
            text("UPDATE users SET api_key_hash = :h, api_key_prefix = :p WHERE id = :id"),
            {'h': hashed, 'p': prefix, 'id': row[0]}
        )

    # 3. Null out the old plaintext column (keep it for now; drop in a future migration)
    conn.execute(text("UPDATE users SET api_key = NULL"))

    # 4. Create unique index on api_key_hash
    op.create_index('ix_users_api_key_hash', 'users', ['api_key_hash'], unique=True)


def downgrade():
    op.drop_index('ix_users_api_key_hash', table_name='users')
    op.drop_column('users', 'api_key_prefix')
    op.drop_column('users', 'api_key_hash')
    # NOTE: plaintext api_key values are NOT restored on downgrade
    #       (they were deliberately nulled; hash is one-way).
