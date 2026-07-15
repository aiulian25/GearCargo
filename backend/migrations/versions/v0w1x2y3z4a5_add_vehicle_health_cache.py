"""F30 — cache the computed health score on the Vehicle row.

health_score mirrors the /health endpoint's overall_score; health_computed_at
records when it was last refreshed (view-driven, no scheduled job).

Revision ID: v0w1x2y3z4a5
Revises: u9v0w1x2y3z4
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'v0w1x2y3z4a5'
down_revision = 'u9v0w1x2y3z4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.add_column(sa.Column('health_score', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('health_computed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.drop_column('health_computed_at')
        batch_op.drop_column('health_score')
