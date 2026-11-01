"""Manual workshop appointments and explicit work/expense links."""
from alembic import op
import sqlalchemy as sa

revision = 'feature_appointments'
down_revision = 'feature_tires_lifecycle'
branch_labels = depends_on = None


def ownership():
    return [sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False)]


def parent():
    return sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id', ondelete='CASCADE'), nullable=False)


def upgrade():
    op.create_table('appointments', *ownership(),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('title', sa.String(255), nullable=False), sa.Column('shop_name', sa.String(100)),
        sa.Column('shop_contact', sa.String(255)), sa.Column('notes', sa.Text()),
        sa.Column('status', sa.String(12), nullable=False), sa.Column('time_zone', sa.String(64), nullable=False),
        sa.Column('start_at', sa.DateTime(), nullable=False), sa.Column('end_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime()), sa.Column('dropoff_at', sa.DateTime()), sa.Column('pickup_at', sa.DateTime()),
        sa.Column('prepare_minutes', sa.Integer(), nullable=False),
        sa.Column('notify_push', sa.Boolean(), nullable=False), sa.Column('notify_email', sa.Boolean(), nullable=False),
        sa.Column('preparation_reminder_id', sa.Integer(), sa.ForeignKey('reminders.id', ondelete='SET NULL'), unique=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('requested','confirmed','completed','cancelled')", name='ck_appointment_status'),
        sa.CheckConstraint('end_at > start_at', name='ck_appointment_interval'),
        sa.CheckConstraint('prepare_minutes >= 0 AND prepare_minutes <= 43200', name='ck_appointment_preparation'))
    op.create_table('appointment_tasks', *ownership(), parent(),
        sa.Column('title', sa.String(255), nullable=False), sa.Column('done', sa.Boolean(), nullable=False),
        sa.Column('reminder_id', sa.Integer(), sa.ForeignKey('reminders.id', ondelete='SET NULL')),
        sa.Column('todo_id', sa.Integer(), sa.ForeignKey('todos.id', ondelete='SET NULL')),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('service_entries.id', ondelete='SET NULL')),
        sa.Column('prediction_id', sa.Integer(), sa.ForeignKey('prediction_alerts.id', ondelete='SET NULL')),
        sa.Column('source_signature', sa.String(64)))
    op.create_table('appointment_expenses', *ownership(), parent(),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('entries.id', ondelete='CASCADE'), nullable=False, unique=True))
    for table in ('appointments', 'appointment_tasks', 'appointment_expenses'):
        for column in ('user_id', 'vehicle_id') + (() if table == 'appointments' else ('appointment_id',)):
            op.create_index(f'ix_{table}_{column}', table, [column])


def downgrade():
    for table in ('appointment_expenses', 'appointment_tasks', 'appointments'):
        op.drop_table(table)
