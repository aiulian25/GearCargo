"""Encrypt TOTP 2FA secret column (S06)

Revision ID: e7f5a3c1d892
Revises: d6e0f3a4b567
Create Date: 2026-04-28

Changes:
- `users.two_factor_secret`: VARCHAR(32) → TEXT

The column is widened to TEXT because Fernet ciphertext for a 32-byte base32
seed is ~120 characters — far larger than the original 32-char limit.

Existing plaintext rows are NOT migrated here because Alembic env.py does not
have access to Flask's app context (and therefore the ENCRYPTION_KEY).  The
application-level _get_totp_secret() helper handles legacy plaintext rows
gracefully by logging a WARNING and returning the raw value on reads.  The
value is automatically re-encrypted the next time the user modifies their 2FA
settings (setup / disable / regenerate).

If you prefer to bulk-encrypt all existing rows in one pass, run the
provided management script after deploying this migration:

    flask encrypt-totp-secrets
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f5a3c1d892'
down_revision = 'd6e0f3a4b567'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'two_factor_secret',
            existing_type=sa.String(length=32),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    # Truncation risk: any encrypted value (> 32 chars) will be silently
    # truncated by PostgreSQL if the downgrade is applied while encrypted rows
    # exist.  Disable 2FA for all users or migrate back to plaintext first.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'two_factor_secret',
            existing_type=sa.Text(),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
