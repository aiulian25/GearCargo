"""merge prediction_alerts and daily_alerts heads

Revision ID: i7j8k9l0m1n2
Revises: h5i6j7k8l9m0, h6i7j8k9l0m1
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'i7j8k9l0m1n2'
down_revision = ('h5i6j7k8l9m0', 'h6i7j8k9l0m1')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
