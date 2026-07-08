"""Add mileage_notified sentinel to reminders (F7 — mileage-crossing pushes)

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-07-08 00:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'r6s7t8u9v0w1'
down_revision = 'q5r6s7t8u9v0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('mileage_notified', sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.drop_column('mileage_notified')
