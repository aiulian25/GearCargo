"""F25 — keep the weekly national fuel-price points instead of overwriting.

One row per (country, price_date); accrues from the existing Monday refresh
and successful live fetches — never from baseline fallback data.

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'x2y3z4a5b6c7'
down_revision = 'w1x2y3z4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fuel_price_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('country', sa.String(2), nullable=False),
        sa.Column('price_date', sa.Date(), nullable=False),
        sa.Column('diesel', sa.Numeric(8, 3), nullable=True),
        sa.Column('petrol', sa.Numeric(8, 3), nullable=True),
        sa.Column('lpg', sa.Numeric(8, 3), nullable=True),
        sa.Column('premium', sa.Numeric(8, 3), nullable=True),
        sa.Column('currency_code', sa.String(3), nullable=True),
        sa.Column('source', sa.String(64), nullable=True),
        sa.UniqueConstraint('country', 'price_date',
                            name='uq_fuel_price_history_country_date'),
    )
    op.create_index('ix_fuel_price_history_country', 'fuel_price_history', ['country'])
    op.create_index('ix_fuel_price_history_price_date', 'fuel_price_history', ['price_date'])


def downgrade():
    op.drop_index('ix_fuel_price_history_price_date', table_name='fuel_price_history')
    op.drop_index('ix_fuel_price_history_country', table_name='fuel_price_history')
    op.drop_table('fuel_price_history')
