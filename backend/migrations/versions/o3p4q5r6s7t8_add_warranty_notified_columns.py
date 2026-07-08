"""Add warranty_notified sentinel to service/repair/consumable entries (F2)

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-07-08 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o3p4q5r6s7t8'
down_revision = 'n2o3p4q5r6s7'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('service_entries', 'repair_entries', 'consumable_entries'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('warranty_notified', sa.Boolean(), nullable=False,
                          server_default=sa.false())
            )


def downgrade():
    for table in ('service_entries', 'repair_entries', 'consumable_entries'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('warranty_notified')
