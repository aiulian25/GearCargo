"""Initial database schema

Revision ID: f9e4b6bc1451
Revises: 
Create Date: 2026-02-10 22:50:38.417786

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9e4b6bc1451'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=50), nullable=True),
        sa.Column('last_name', sa.String(length=50), nullable=True),
        sa.Column('avatar', sa.String(length=255), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=True),
        sa.Column('theme', sa.String(length=10), nullable=True),
        sa.Column('currency', sa.String(length=5), nullable=True),
        sa.Column('distance_unit', sa.String(length=10), nullable=True),
        sa.Column('volume_unit', sa.String(length=10), nullable=True),
        sa.Column('date_format', sa.String(length=20), nullable=True),
        sa.Column('country_preference', sa.String(length=3), nullable=True),
        sa.Column('preferences', sa.JSON(), nullable=True),
        sa.Column('two_factor_secret', sa.String(length=32), nullable=True),
        sa.Column('two_factor_enabled', sa.Boolean(), nullable=True),
        sa.Column('two_factor_backup_codes', sa.JSON(), nullable=True),
        sa.Column('email_otp_secret', sa.String(length=32), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=True),
        sa.Column('email_verification_token', sa.String(length=255), nullable=True),
        sa.Column('email_verification_expires', sa.DateTime(), nullable=True),
        sa.Column('password_reset_token', sa.String(length=255), nullable=True),
        sa.Column('password_reset_expires', sa.DateTime(), nullable=True),
        sa.Column('last_password_change', sa.DateTime(), nullable=True),
        sa.Column('security_questions', sa.JSON(), nullable=True),
        sa.Column('security_questions_set_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=True),
        sa.Column('is_dummy', sa.Boolean(), nullable=True),
        sa.Column('must_change_password', sa.Boolean(), nullable=True),
        sa.Column('vehicle_limit', sa.Integer(), nullable=True),
        sa.Column('max_sessions', sa.Integer(), nullable=True),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=True),
        sa.Column('notification_email', sa.String(length=120), nullable=True),
        sa.Column('email_insurance_alerts', sa.Boolean(), nullable=True),
        sa.Column('email_tax_alerts', sa.Boolean(), nullable=True),
        sa.Column('email_service_alerts', sa.Boolean(), nullable=True),
        sa.Column('email_reminder_alerts', sa.Boolean(), nullable=True),
        sa.Column('email_smart_alerts', sa.Boolean(), nullable=True),
        sa.Column('weekly_report_enabled', sa.Boolean(), nullable=True),
        sa.Column('monthly_report_enabled', sa.Boolean(), nullable=True),
        sa.Column('alert_days_before', sa.Integer(), nullable=True),
        sa.Column('last_weekly_report', sa.DateTime(), nullable=True),
        sa.Column('last_monthly_report', sa.DateTime(), nullable=True),
        sa.Column('location_lat', sa.Float(), nullable=True),
        sa.Column('location_lon', sa.Float(), nullable=True),
        sa.Column('location_name', sa.String(length=255), nullable=True),
        sa.Column('location_auto_detect', sa.Boolean(), nullable=True),
        sa.Column('calendar_enabled', sa.Boolean(), nullable=True),
        sa.Column('calendar_provider', sa.String(length=50), nullable=True),
        sa.Column('calendar_url', sa.String(length=500), nullable=True),
        sa.Column('calendar_username', sa.String(length=255), nullable=True),
        sa.Column('calendar_password', sa.Text(), nullable=True),
        sa.Column('calendar_id', sa.String(length=255), nullable=True),
        sa.Column('calendar_last_sync', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=False)

    # Create vehicles table
    op.create_table('vehicles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('make', sa.String(length=50), nullable=True),
        sa.Column('model', sa.String(length=50), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('vin', sa.String(length=17), nullable=True),
        sa.Column('license_plate', sa.String(length=20), nullable=True),
        sa.Column('fuel_type', sa.String(length=20), nullable=True),
        sa.Column('engine_cc', sa.Integer(), nullable=True),
        sa.Column('transmission', sa.String(length=20), nullable=True),
        sa.Column('drivetrain', sa.String(length=10), nullable=True),
        sa.Column('color', sa.String(length=30), nullable=True),
        sa.Column('vehicle_weight_kg', sa.Integer(), nullable=True),
        sa.Column('vehicle_height_cm', sa.Integer(), nullable=True),
        sa.Column('vehicle_length_cm', sa.Integer(), nullable=True),
        sa.Column('vehicle_width_cm', sa.Integer(), nullable=True),
        sa.Column('current_mileage', sa.Integer(), nullable=True),
        sa.Column('distance_unit', sa.String(length=10), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('purchase_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('monthly_budget', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('avg_trip_distance', sa.Float(), nullable=True),
        sa.Column('city_driving_percentage', sa.Integer(), nullable=True),
        sa.Column('highway_driving_percentage', sa.Integer(), nullable=True),
        sa.Column('cost_per_km', sa.Float(), nullable=True),
        sa.Column('avg_fuel_efficiency', sa.Float(), nullable=True),
        sa.Column('maintenance_score', sa.Integer(), nullable=True),
        sa.Column('prediction_accuracy_score', sa.Float(), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('photo', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vin')
    )
    op.create_index(op.f('ix_vehicles_user_id'), 'vehicles', ['user_id'], unique=False)
    op.create_index(op.f('ix_vehicles_vin'), 'vehicles', ['vin'], unique=False)

    # Create entries table (base for joined table inheritance)
    op.create_table('entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('odometer', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entries_user_id'), 'entries', ['user_id'], unique=False)
    op.create_index(op.f('ix_entries_vehicle_id'), 'entries', ['vehicle_id'], unique=False)

    # Create attachments table
    op.create_table('attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('filepath', sa.String(length=500), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('ocr_text', sa.Text(), nullable=True),
        sa.Column('ocr_processed', sa.Boolean(), nullable=True),
        sa.Column('vin_extracted', sa.String(length=17), nullable=True),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('expiry_notified', sa.Boolean(), nullable=True),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entry_id'], ['entries.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attachments_entry_id'), 'attachments', ['entry_id'], unique=False)
    op.create_index(op.f('ix_attachments_user_id'), 'attachments', ['user_id'], unique=False)
    op.create_index(op.f('ix_attachments_vehicle_id'), 'attachments', ['vehicle_id'], unique=False)

    # Create insurance_policies table
    op.create_table('insurance_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('policy_number', sa.String(length=100), nullable=True),
        sa.Column('provider', sa.String(length=255), nullable=False),
        sa.Column('policy_type', sa.String(length=50), nullable=True),
        sa.Column('coverage_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('deductible', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('coverage_details', sa.JSON(), nullable=True),
        sa.Column('premium', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_frequency', sa.String(length=20), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('agent_name', sa.String(length=255), nullable=True),
        sa.Column('agent_phone', sa.String(length=50), nullable=True),
        sa.Column('agent_email', sa.String(length=255), nullable=True),
        sa.Column('claims_phone', sa.String(length=50), nullable=True),
        sa.Column('document_attachment_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_attachment_id'], ['attachments.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_insurance_policies_user_id'), 'insurance_policies', ['user_id'], unique=False)
    op.create_index(op.f('ix_insurance_policies_vehicle_id'), 'insurance_policies', ['vehicle_id'], unique=False)

    # Create fuel_entries table
    op.create_table('fuel_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('liters', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('price_per_liter', sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column('total_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('fuel_type', sa.String(length=20), nullable=True),
        sa.Column('station', sa.String(length=100), nullable=True),
        sa.Column('station_address', sa.String(length=255), nullable=True),
        sa.Column('full_tank', sa.Boolean(), nullable=True),
        sa.Column('fuel_efficiency', sa.Float(), nullable=True),
        sa.Column('trip_distance', sa.Integer(), nullable=True),
        sa.Column('ocr_populated', sa.Boolean(), nullable=True),
        sa.Column('receipt_image', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create service_entries table
    op.create_table('service_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_type', sa.String(length=50), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('garage_name', sa.String(length=100), nullable=True),
        sa.Column('garage_address', sa.String(length=255), nullable=True),
        sa.Column('garage_phone', sa.String(length=20), nullable=True),
        sa.Column('postcode', sa.String(length=20), nullable=True),
        sa.Column('work_order_number', sa.String(length=50), nullable=True),
        sa.Column('labor_hours', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('labor_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('parts_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('parts_used', sa.JSON(), nullable=True),
        sa.Column('warranty_months', sa.Integer(), nullable=True),
        sa.Column('warranty_km', sa.Integer(), nullable=True),
        sa.Column('warranty_notes', sa.Text(), nullable=True),
        sa.Column('warranty_expires', sa.Date(), nullable=True),
        sa.Column('next_due_date', sa.Date(), nullable=True),
        sa.Column('next_due_mileage', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create repair_entries table
    op.create_table('repair_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repair_type', sa.String(length=50), nullable=True),
        sa.Column('diagnosis', sa.Text(), nullable=True),
        sa.Column('symptoms', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('garage_name', sa.String(length=100), nullable=True),
        sa.Column('garage_address', sa.String(length=255), nullable=True),
        sa.Column('labor_hours', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('labor_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('parts_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('parts_replaced', sa.JSON(), nullable=True),
        sa.Column('warranty_months', sa.Integer(), nullable=True),
        sa.Column('warranty_km', sa.Integer(), nullable=True),
        sa.Column('warranty_notes', sa.Text(), nullable=True),
        sa.Column('under_warranty', sa.Boolean(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create tax_entries table
    op.create_table('tax_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tax_type', sa.String(length=50), nullable=True),
        sa.Column('tax_year', sa.Integer(), nullable=True),
        sa.Column('tax_period', sa.String(length=20), nullable=True),
        sa.Column('tax_rate', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('insurance_policy_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('paid_date', sa.Date(), nullable=True),
        sa.Column('filing_date', sa.Date(), nullable=True),
        sa.Column('reference_number', sa.String(length=50), nullable=True),
        sa.Column('recurring', sa.Boolean(), nullable=True),
        sa.Column('recurrence_type', sa.String(length=20), nullable=True),
        sa.Column('next_due_date', sa.Date(), nullable=True),
        sa.Column('reminder_days', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['entries.id'], ),
        sa.ForeignKeyConstraint(['insurance_policy_id'], ['insurance_policies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tax_entries_insurance_policy_id'), 'tax_entries', ['insurance_policy_id'], unique=False)

    # Create parking_entries table
    op.create_table('parking_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('parking_type', sa.String(length=30), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('location_address', sa.String(length=255), nullable=True),
        sa.Column('start_datetime', sa.DateTime(), nullable=True),
        sa.Column('end_datetime', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('recurring', sa.Boolean(), nullable=True),
        sa.Column('recurrence_type', sa.String(length=20), nullable=True),
        sa.Column('next_due_date', sa.Date(), nullable=True),
        sa.Column('reminder_days', sa.Integer(), nullable=True),
        sa.Column('permit_number', sa.String(length=50), nullable=True),
        sa.Column('permit_expires', sa.Date(), nullable=True),
        sa.Column('fine_reason', sa.String(length=255), nullable=True),
        sa.Column('fine_status', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['entries.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create reminders table
    op.create_table('reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('due_mileage', sa.Integer(), nullable=True),
        sa.Column('reminder_type', sa.String(length=30), nullable=True),
        sa.Column('priority', sa.String(length=10), nullable=True),
        sa.Column('recurring', sa.Boolean(), nullable=True),
        sa.Column('frequency', sa.String(length=20), nullable=True),
        sa.Column('frequency_value', sa.Integer(), nullable=True),
        sa.Column('recurrence_end', sa.Date(), nullable=True),
        sa.Column('completed', sa.Boolean(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('dismissed', sa.Boolean(), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.Column('snoozed_until', sa.DateTime(), nullable=True),
        sa.Column('calendar_sync', sa.Boolean(), nullable=True),
        sa.Column('external_calendar_id', sa.String(length=255), nullable=True),
        sa.Column('calendar_service', sa.String(length=30), nullable=True),
        sa.Column('external_etag', sa.String(length=255), nullable=True),
        sa.Column('external_checksum', sa.String(length=64), nullable=True),
        sa.Column('sync_conflict', sa.Boolean(), nullable=True),
        sa.Column('local_version_data', sa.JSON(), nullable=True),
        sa.Column('remote_version_data', sa.JSON(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('title_translations', sa.JSON(), nullable=True),
        sa.Column('description_translations', sa.JSON(), nullable=True),
        sa.Column('notify_days_before', sa.Integer(), nullable=True),
        sa.Column('notify_email', sa.Boolean(), nullable=True),
        sa.Column('notify_push', sa.Boolean(), nullable=True),
        sa.Column('last_notified_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reminders_user_id'), 'reminders', ['user_id'], unique=False)
    op.create_index(op.f('ix_reminders_vehicle_id'), 'reminders', ['vehicle_id'], unique=False)

    # Create prediction_alerts table
    op.create_table('prediction_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('predicted_mileage', sa.Integer(), nullable=True),
        sa.Column('predicted_date', sa.Date(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.Column('dismissed', sa.Boolean(), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.Column('actioned', sa.Boolean(), nullable=True),
        sa.Column('actioned_at', sa.DateTime(), nullable=True),
        sa.Column('i18n_key', sa.String(length=100), nullable=True),
        sa.Column('i18n_params', sa.JSON(), nullable=True),
        sa.Column('description_en_us', sa.Text(), nullable=True),
        sa.Column('description_ro', sa.Text(), nullable=True),
        sa.Column('description_es', sa.Text(), nullable=True),
        sa.Column('generated_by', sa.String(length=30), nullable=True),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_alerts_vehicle_id'), 'prediction_alerts', ['vehicle_id'], unique=False)

    # Create todos table
    op.create_table('todos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('priority', sa.String(length=10), nullable=True),
        sa.Column('completed', sa.Boolean(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_todos_user_id'), 'todos', ['user_id'], unique=False)
    op.create_index(op.f('ix_todos_vehicle_id'), 'todos', ['vehicle_id'], unique=False)

    # Create activity_logs table
    op.create_table('activity_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_category', sa.String(length=30), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('browser', sa.String(length=100), nullable=True),
        sa.Column('browser_version', sa.String(length=20), nullable=True),
        sa.Column('os', sa.String(length=100), nullable=True),
        sa.Column('os_version', sa.String(length=20), nullable=True),
        sa.Column('device_language', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('country_code', sa.String(length=5), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activity_logs_created_at'), 'activity_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_activity_logs_event_category'), 'activity_logs', ['event_category'], unique=False)
    op.create_index(op.f('ix_activity_logs_event_type'), 'activity_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_activity_logs_user_id'), 'activity_logs', ['user_id'], unique=False)

    # Create backups table
    op.create_table('backups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('backup_type', sa.String(length=20), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('filepath', sa.String(length=500), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('cloud_provider', sa.String(length=50), nullable=True),
        sa.Column('cloud_file_id', sa.String(length=255), nullable=True),
        sa.Column('cloud_url', sa.String(length=500), nullable=True),
        sa.Column('vehicles_count', sa.Integer(), nullable=True),
        sa.Column('entries_count', sa.Integer(), nullable=True),
        sa.Column('reminders_count', sa.Integer(), nullable=True),
        sa.Column('attachments_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('encrypted', sa.Boolean(), nullable=True),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_backups_user_id'), 'backups', ['user_id'], unique=False)

    # Create blocked_ips table
    op.create_table('blocked_ips',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('block_type', sa.String(length=20), nullable=True),
        sa.Column('failed_attempts', sa.Integer(), nullable=True),
        sa.Column('last_failed_attempt', sa.DateTime(), nullable=True),
        sa.Column('blocked_by_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('unblocked_at', sa.DateTime(), nullable=True),
        sa.Column('unblocked_by_id', sa.Integer(), nullable=True),
        sa.Column('unblock_reason', sa.String(length=500), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('country_code', sa.String(length=5), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('isp', sa.String(length=200), nullable=True),
        sa.Column('target_user_id', sa.Integer(), nullable=True),
        sa.Column('target_email', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['blocked_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['unblocked_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip_address')
    )
    op.create_index(op.f('ix_blocked_ips_created_at'), 'blocked_ips', ['created_at'], unique=False)
    op.create_index(op.f('ix_blocked_ips_ip_address'), 'blocked_ips', ['ip_address'], unique=False)

    # Create blocked_devices table
    op.create_table('blocked_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('browser', sa.String(length=100), nullable=True),
        sa.Column('browser_version', sa.String(length=20), nullable=True),
        sa.Column('os', sa.String(length=100), nullable=True),
        sa.Column('os_version', sa.String(length=20), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('block_type', sa.String(length=20), nullable=True),
        sa.Column('failed_attempts', sa.Integer(), nullable=True),
        sa.Column('last_failed_attempt', sa.DateTime(), nullable=True),
        sa.Column('associated_ips', sa.JSON(), nullable=True),
        sa.Column('blocked_by_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('unblocked_at', sa.DateTime(), nullable=True),
        sa.Column('unblocked_by_id', sa.Integer(), nullable=True),
        sa.Column('unblock_reason', sa.String(length=500), nullable=True),
        sa.Column('target_user_id', sa.Integer(), nullable=True),
        sa.Column('target_email', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['blocked_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['unblocked_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_blocked_devices_created_at'), 'blocked_devices', ['created_at'], unique=False)
    op.create_index(op.f('ix_blocked_devices_device_fingerprint'), 'blocked_devices', ['device_fingerprint'], unique=False)

    # Create push_subscriptions table
    op.create_table('push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh_key', sa.String(length=255), nullable=False),
        sa.Column('auth_key', sa.String(length=255), nullable=False),
        sa.Column('device_name', sa.String(length=255), nullable=True),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('browser', sa.String(length=100), nullable=True),
        sa.Column('os', sa.String(length=100), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint', name='uq_push_endpoint')
    )
    op.create_index(op.f('ix_push_subscriptions_user_id'), 'push_subscriptions', ['user_id'], unique=False)


def downgrade():
    # Drop all tables in reverse order
    op.drop_table('push_subscriptions')
    op.drop_table('blocked_devices')
    op.drop_table('blocked_ips')
    op.drop_table('backups')
    op.drop_table('activity_logs')
    op.drop_table('todos')
    op.drop_table('prediction_alerts')
    op.drop_table('reminders')
    op.drop_table('parking_entries')
    op.drop_table('tax_entries')
    op.drop_table('repair_entries')
    op.drop_table('service_entries')
    op.drop_table('fuel_entries')
    op.drop_table('insurance_policies')
    op.drop_table('attachments')
    op.drop_table('entries')
    op.drop_table('vehicles')
    op.drop_table('users')
