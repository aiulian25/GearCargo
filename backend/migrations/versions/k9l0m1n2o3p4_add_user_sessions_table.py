"""Add user_sessions table (DB-backed session fallback)

S01 (IMPROVEMENTS.md §1.1): creates a durable mirror of the Redis session store
so session validation, the 48h absolute-expiry wall, single-device enforcement,
and logout revocation continue to work (fail CLOSED, not OPEN) when Redis is
unavailable. Redis stays the fast path; this table is the fallback.

Uses CREATE TABLE IF NOT EXISTS so re-running on an environment that already has
the table (e.g. created via db.create_all in tests) is a no-op.

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k9l0m1n2o3p4'
down_revision = 'j8k9l0m1n2o3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            jti                 VARCHAR(64) NOT NULL UNIQUE,
            absolute_expires_at TIMESTAMP NOT NULL,
            revoked             BOOLEAN NOT NULL DEFAULT FALSE,
            revoked_at          TIMESTAMP,
            user_agent          VARCHAR(255),
            ip                  VARCHAR(45),
            created_at          TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
        )
        """
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id)"
    ))
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_sessions_jti ON user_sessions (jti)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_absolute_expires_at ON user_sessions (absolute_expires_at)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_revoked ON user_sessions (revoked)"
    ))


def downgrade():
    op.drop_table('user_sessions')
