"""Add login_alerts_enabled column for suspicious login opt-out (S18)

Revision ID: e3f4a5b6c789
Revises: c1b2a3e4f567
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c789'
down_revision = 'c1b2a3e4f567'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_alerts_enabled BOOLEAN DEFAULT true"
    ))


def downgrade():
    op.drop_column('users', 'login_alerts_enabled')
