"""F31 — per-vehicle maintenance-interval overrides.

JSON map of component key -> interval in the vehicle's own distance unit;
NULL means "all defaults". Validated on write (component allowlist,
positive int <= 500000).

Revision ID: w1x2y3z4a5b6
Revises: v0w1x2y3z4a5
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'w1x2y3z4a5b6'
down_revision = 'v0w1x2y3z4a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.add_column(sa.Column('maintenance_intervals', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.drop_column('maintenance_intervals')
