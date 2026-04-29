"""Add DB-backed lockout fallback columns to users table

Adds failed_login_attempts and locked_until to the users table.
These columns are used as a fallback for brute-force protection when
Redis is unavailable, ensuring account lockout works even without Redis.

Revision ID: d6e0f3a4b567
Revises: c5d9e1f2a345
Create Date: 2026-07-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e0f3a4b567'
down_revision = 'c5d9e1f2a345'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column(
        'failed_login_attempts',
        sa.Integer(),
        nullable=False,
        server_default='0'
    ))
    op.add_column('users', sa.Column(
        'locked_until',
        sa.DateTime(),
        nullable=True
    ))


def downgrade():
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
