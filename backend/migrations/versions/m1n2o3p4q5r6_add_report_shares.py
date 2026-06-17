"""Add report_shares table (shareable read-only report links)

F05 (IMPROVEMENTS.md §3.2): signed, expiring, revocable public share links for
expense reports. Stores only the SHA-256 hash of the share token.

Idempotent (CREATE TABLE IF NOT EXISTS).

Revision ID: m1n2o3p4q5r6
Revises: l0m1n2o3p4q5
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'm1n2o3p4q5r6'
down_revision = 'l0m1n2o3p4q5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS report_shares (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash       VARCHAR(64) NOT NULL UNIQUE,
            token_prefix     VARCHAR(12),
            label            VARCHAR(120),
            vehicle_ids      JSON,
            period           VARCHAR(20) DEFAULT 'current_month',
            year             INTEGER,
            month            INTEGER,
            expires_at       TIMESTAMP NOT NULL,
            revoked          BOOLEAN NOT NULL DEFAULT FALSE,
            revoked_at       TIMESTAMP,
            access_count     INTEGER NOT NULL DEFAULT 0,
            last_accessed_at TIMESTAMP,
            created_at       TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
        )
        """
    ))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_report_shares_user_id ON report_shares (user_id)"))
    conn.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_report_shares_token_hash ON report_shares (token_hash)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_report_shares_expires_at ON report_shares (expires_at)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_report_shares_revoked ON report_shares (revoked)"))


def downgrade():
    op.drop_table('report_shares')
