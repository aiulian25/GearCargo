"""Add recurrence columns to todos (F15 — recurring todos, parity with reminders)

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-07-08 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's7t8u9v0w1x2'
down_revision = 'r6s7t8u9v0w1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('todos', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('recurring', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('frequency', sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column('frequency_value', sa.Integer(), nullable=True, server_default='1')
        )


def downgrade():
    with op.batch_alter_table('todos', schema=None) as batch_op:
        batch_op.drop_column('frequency_value')
        batch_op.drop_column('frequency')
        batch_op.drop_column('recurring')
