"""F22 — add vehicles.tank_capacity (litres).

The Add/Edit Vehicle forms have always collected tank_capacity, but no column
existed — the value was silently dropped. Nullable, no backfill.

Revision ID: u9v0w1x2y3z4
Revises: t8u9v0w1x2y3
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'u9v0w1x2y3z4'
down_revision = 't8u9v0w1x2y3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.add_column(sa.Column('tank_capacity', sa.Numeric(5, 1), nullable=True))


def downgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.drop_column('tank_capacity')
