"""Add daily_alerts_enabled to users

Revision ID: h5i6j7k8l9m0
Revises: g0h1i2j3k4l5
Create Date: 2026-05-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h5i6j7k8l9m0'
down_revision = 'g0h1i2j3k4l5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_alerts_enabled BOOLEAN DEFAULT TRUE"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE users DROP COLUMN IF EXISTS daily_alerts_enabled"
    ))
