"""Tire sets, immutable identities, fitment history and tread readings."""
from alembic import op
import sqlalchemy as sa

revision = 'feature_tires_lifecycle'
down_revision = 'gc034_fuel_history_index'
branch_labels = depends_on = None


def ownership():
    return [sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=False)]


def parent():
    return sa.Column('tire_set_id', sa.Integer(), sa.ForeignKey('tire_sets.id', ondelete='CASCADE'), nullable=False)


def upgrade():
    op.create_table('tire_sets', *ownership(),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('season', sa.String(12), nullable=False),
        sa.Column('storage_location', sa.String(200)),
        sa.Column('purchase_entry_id', sa.Integer(), sa.ForeignKey('entries.id', ondelete='SET NULL')),
        sa.Column('rotation_interval', sa.Numeric(16, 6)),
        sa.Column('tread_unit', sa.String(8), nullable=False),
        sa.Column('tread_threshold', sa.Numeric(10, 4)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_table('tires', *ownership(), parent(),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('identifier', sa.String(60), nullable=False),
        sa.UniqueConstraint('tire_set_id', 'identifier', name='uq_tire_set_identifier'))
    op.create_table('tire_fitments', *ownership(), parent(),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('odometer', sa.Numeric(16, 6)),
        sa.Column('positions', sa.JSON(), nullable=False),
        sa.CheckConstraint("kind IN ('install', 'remove', 'rotate')", name='ck_tire_fitment_kind'),
        sa.CheckConstraint('odometer IS NULL OR odometer >= 0', name='ck_tire_fitment_odometer'))
    op.create_table('tread_readings', *ownership(), parent(),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('tire_id', sa.Integer(), sa.ForeignKey('tires.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('depth', sa.Numeric(10, 4), nullable=False),
        sa.Column('unit', sa.String(8), nullable=False),
        sa.CheckConstraint('depth >= 0', name='ck_tread_depth'),
        sa.CheckConstraint("unit IN ('mm', '32nds')", name='ck_tread_unit'))
    for table in ('tire_sets', 'tires', 'tire_fitments', 'tread_readings'):
        for column in ('user_id', 'vehicle_id') + (() if table == 'tire_sets' else ('tire_set_id',)):
            op.create_index(f'ix_{table}_{column}', table, [column])
    op.create_index('ix_tread_readings_tire_id', 'tread_readings', ['tire_id'])
    op.create_index('ix_tire_fitments_vehicle_date_id', 'tire_fitments', ['vehicle_id', 'date', 'id'])


def downgrade():
    for table in ('tread_readings', 'tire_fitments', 'tires', 'tire_sets'):
        op.drop_table(table)
