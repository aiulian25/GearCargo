"""Index stable owner/vehicle fuel-history traversal and interval lookups."""
from alembic import op

revision = 'gc034_fuel_history_index'
down_revision = 'gc028_backup_protection'
branch_labels = depends_on = None


def upgrade():
    op.create_index('ix_entries_user_vehicle_date_id', 'entries',
                    ['user_id', 'vehicle_id', 'date', 'id'], unique=False)


def downgrade():
    op.drop_index('ix_entries_user_vehicle_date_id', table_name='entries')
