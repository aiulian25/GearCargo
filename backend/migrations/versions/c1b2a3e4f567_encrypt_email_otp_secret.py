"""Encrypt email OTP secret column (S15)

Revision ID: c1b2a3e4f567
Revises: f2a8b4c6d0e1
Create Date: 2025-04-29

Changes:
- ``users.email_otp_secret``: VARCHAR(32) → TEXT

The column is widened to TEXT because Fernet ciphertext for a 32-byte base32
seed is ~120 characters — far larger than the original 32-char limit.

Existing plaintext rows are NOT migrated here; the application-level
_get_email_otp_secret() helper in auth.py handles legacy plaintext rows
gracefully by logging a WARNING and returning the raw value.  The secret is
automatically re-encrypted the next time any code path calls
_set_email_otp_secret() for that user.

Note: email_otp_secret has no active call-sites as of this migration —
the column was added speculatively but the email-OTP flow is not yet
implemented. The encryption helpers are added pre-emptively so the column
is ready for secure use when the feature lands.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c1b2a3e4f567'
down_revision = 'f2a8b4c6d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'email_otp_secret',
            existing_type=sa.String(length=32),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'email_otp_secret',
            existing_type=sa.Text(),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
