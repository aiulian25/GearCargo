"""Add replace_notified sentinel to consumable_entries (F3)

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'n2o3p4q5r6s7'
down_revision = 'm1n2o3p4q5r6'
branch_labels = None
depends_on = None


def upgrade():
    # server_default=false so every existing consumable starts as "not notified".
    with op.batch_alter_table('consumable_entries', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('replace_notified', sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table('consumable_entries', schema=None) as batch_op:
        batch_op.drop_column('replace_notified')
