"""Invalidate legacy sessions before enabling database-authoritative validation.

Older best-effort mirrors may omit a revocation recorded only in Redis. There
is no safe way to reconstruct a lost denylist: require a fresh sign-in once.
"""
from alembic import op

revision = 'gc026_session_authority'
down_revision = 'gc025_attachment_processing'
branch_labels = depends_on = None


def upgrade():
    op.execute('UPDATE user_sessions SET revoked = true, revoked_at = CURRENT_TIMESTAMP WHERE revoked = false')


def downgrade():
    # Never reactivate credentials invalidated for security, even on rollback.
    pass
