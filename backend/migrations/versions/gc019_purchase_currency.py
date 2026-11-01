"""Preserve purchase currency; historical prices remain unknown until reviewed."""
from alembic import op
import sqlalchemy as sa

revision = 'gc019_purchase_currency'
down_revision = 'gc016_import_provenance'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vehicles', sa.Column('purchase_currency', sa.String(3), nullable=True))


def downgrade():
    op.drop_column('vehicles', 'purchase_currency')
