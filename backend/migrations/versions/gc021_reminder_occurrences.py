"""Reminder intervals, calendar anchors and portable per-channel delivery state."""
import hashlib
from alembic import op
import sqlalchemy as sa

revision = 'gc021_reminder_occurrences'
down_revision = 'gc019_purchase_currency'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reminders', sa.Column('repeat_mileage', sa.Integer(), nullable=True))
    op.add_column('reminders', sa.Column('recurrence_anchor_date', sa.Date(), nullable=True))
    op.add_column('reminders', sa.Column('notification_state', sa.JSON(), nullable=True))
    reminders = sa.table('reminders', sa.column('id', sa.Integer), sa.column('due_date', sa.Date),
        sa.column('due_mileage', sa.Integer), sa.column('snoozed_until', sa.DateTime),
        sa.column('recurring', sa.Boolean), sa.column('last_notified_at', sa.DateTime),
        sa.column('mileage_notified', sa.Boolean), sa.column('recurrence_anchor_date', sa.Date),
        sa.column('notification_state', sa.JSON))
    bind = op.get_bind()
    for row in bind.execute(sa.select(reminders)).mappings().yield_per(500):
        fields = (row['due_date'].isoformat() if row['due_date'] else '',
                  str(row['due_mileage']) if row['due_mileage'] is not None else '',
                  row['snoozed_until'].isoformat() if row['snoozed_until'] else '')
        key = hashlib.sha256('|'.join(fields).encode()).hexdigest()
        channels = {channel: {'status': 'legacy_unknown'} for channel in ('push', 'email')} if row['last_notified_at'] or row['mileage_notified'] else {}
        bind.execute(reminders.update().where(reminders.c.id == row['id']).values(
            recurrence_anchor_date=row['due_date'] if row['recurring'] else None,
            notification_state={'version': 1, 'occurrence': key, 'channels': channels}))


def downgrade():
    for name in ('notification_state', 'recurrence_anchor_date', 'repeat_mileage'):
        op.drop_column('reminders', name)
