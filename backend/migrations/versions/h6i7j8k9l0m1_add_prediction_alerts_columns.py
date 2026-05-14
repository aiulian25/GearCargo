"""Add missing columns to prediction_alerts and vehicles

Revision ID: h6i7j8k9l0m1
Revises: g0h1i2j3k4l5
Create Date: 2025-07-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h6i7j8k9l0m1'
down_revision = 'g0h1i2j3k4l5'
branch_labels = None
depends_on = None


def upgrade():
    # Add missing columns to prediction_alerts
    with op.batch_alter_table('prediction_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('title', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('urgency', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('estimated_cost', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('recommended_action', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('source_data', sa.JSON(), nullable=True))
        batch_op.create_foreign_key('fk_prediction_alerts_user_id', 'users', ['user_id'], ['id'])
        batch_op.create_index('ix_prediction_alerts_user_id', ['user_id'], unique=False)

    # Add last_prediction_at to vehicles
    with op.batch_alter_table('vehicles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_prediction_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('vehicles', schema=None) as batch_op:
        batch_op.drop_column('last_prediction_at')

    with op.batch_alter_table('prediction_alerts', schema=None) as batch_op:
        batch_op.drop_index('ix_prediction_alerts_user_id')
        batch_op.drop_constraint('fk_prediction_alerts_user_id', type_='foreignkey')
        batch_op.drop_column('source_data')
        batch_op.drop_column('recommended_action')
        batch_op.drop_column('estimated_cost')
        batch_op.drop_column('urgency')
        batch_op.drop_column('title')
        batch_op.drop_column('user_id')
