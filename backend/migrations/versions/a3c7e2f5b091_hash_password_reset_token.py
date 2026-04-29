"""Hash password reset tokens — S08: null out any existing plaintext tokens.

The password_reset_token column previously stored raw URL-safe tokens.
After this migration the column stores sha256(raw_token) exclusively.

Existing plaintext tokens are voided (set to NULL) because:
  1. They are short-lived (≤24 h) — anyone mid-flow gets a harmless "invalid
     token" error and can simply request a new reset link.
  2. Forward-migration of plaintext values is impossible without the originals.
  3. Leaving them in place would let a DB reader replay a valid reset link
     until expiry, exactly the vulnerability this patch closes.

No schema change is required: the column keeps its String(255) type; it now
holds a 64-char hex SHA-256 digest instead of a ~43-char urlsafe string.

Revision ID: a3c7e2f5b091
Revises: f2a8b4c6d0e1
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
from sqlalchemy import text


# revision identifiers
revision = 'a3c7e2f5b091'
down_revision = 'f2a8b4c6d0e1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Void all existing plaintext reset tokens.  Short-lived; users can request
    # a fresh link.  This prevents any DB-visible token from being replayable.
    conn.execute(text(
        "UPDATE users SET password_reset_token = NULL, password_reset_expires = NULL"
        " WHERE password_reset_token IS NOT NULL"
    ))


def downgrade():
    # Tokens have already been voided — they cannot be restored.
    # Downgrade is a no-op: the column still exists and will simply be empty.
    pass
