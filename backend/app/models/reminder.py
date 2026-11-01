"""
GearCargo - Reminder Model
"""

from datetime import datetime, timezone
from app.utils.timeutils import utc_naive_now, isoformat_utc
from app import db
from app.utils.revisions import next_revision


class Reminder(db.Model):
    """Reminder model for maintenance tasks and notifications."""
    
    __tablename__ = 'reminders'
    __table_args__ = (db.UniqueConstraint('completed_from_id', name='uq_reminders_completed_from'),)
    
    id = db.Column(db.Integer, primary_key=True)
    revision = db.Column(db.BigInteger, nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": next_revision}
    
    # Content
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Scheduling
    due_date = db.Column(db.Date, nullable=False)
    due_mileage = db.Column(db.Integer)
    reminder_type = db.Column(db.String(30))  # maintenance, insurance, inspection, custom
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    
    completed_from_id = db.Column(db.Integer, db.ForeignKey('reminders.id', name='fk_reminders_completed_from', ondelete='SET NULL'), nullable=True)

    # Recurrence
    recurring = db.Column(db.Boolean, default=False)
    frequency = db.Column(db.String(20))  # daily, weekly, monthly, yearly
    frequency_value = db.Column(db.Integer, default=1)  # Every X days/weeks/etc.
    recurrence_end = db.Column(db.Date)
    repeat_mileage = db.Column(db.Integer)
    recurrence_anchor_date = db.Column(db.Date)
    
    # Status
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    dismissed = db.Column(db.Boolean, default=False)
    dismissed_at = db.Column(db.DateTime)
    snoozed_until = db.Column(db.DateTime)
    
    # Calendar sync
    calendar_sync = db.Column(db.Boolean, default=False)
    external_calendar_id = db.Column(db.String(255))
    calendar_service = db.Column(db.String(30))  # google, webdav, nextcloud
    external_etag = db.Column(db.String(255))
    external_checksum = db.Column(db.String(64))
    sync_conflict = db.Column(db.Boolean, default=False)
    local_version_data = db.Column(db.JSON)
    remote_version_data = db.Column(db.JSON)
    last_synced_at = db.Column(db.DateTime)
    
    # Translation support
    title_translations = db.Column(db.JSON)
    description_translations = db.Column(db.JSON)
    
    # Notification
    notify_days_before = db.Column(db.Integer, default=7)
    notify_email = db.Column(db.Boolean, default=True)
    notify_push = db.Column(db.Boolean, default=True)
    last_notified_at = db.Column(db.DateTime)
    # Portable per-occurrence/channel outcomes and short-lived dispatch claims.
    # Claims are acquired with a revision compare-and-set before transport.
    notification_state = db.Column(db.JSON, default=dict)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), index=True)
    # F5: set when this reminder was auto-generated from a ServiceEntry's
    # next_due_date/next_due_mileage. Links back to that service AND dedups the
    # generator (one auto-reminder per source service).
    source_service_id = db.Column(db.Integer, db.ForeignKey('service_entries.id'), nullable=True, index=True)
    # Compatibility flag, set only after accepted delivery while mileage is due.
    # notification_state controls shared date/mileage deduplication and retries.
    mileage_notified = db.Column(db.Boolean, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, default=utc_naive_now, onupdate=utc_naive_now)
    
    def __repr__(self):
        return f'<Reminder {self.title}>'
    
    def mark_complete(self):
        """Mark reminder as complete."""
        self.completed = True
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_dismissed(self):
        """Dismiss reminder."""
        self.dismissed = True
        self.dismissed_at = datetime.now(timezone.utc)
    
    def snooze(self, until):
        """Snooze reminder until specified datetime."""
        self.snoozed_until = until
    
    @property
    def is_overdue(self):
        """Check if reminder is overdue."""
        if self.completed or self.dismissed:
            return False
        return self.due_date < datetime.now(timezone.utc).date()
    
    @property
    def days_until_due(self):
        """Days until due date."""
        if self.due_date:
            delta = self.due_date - datetime.now(timezone.utc).date()
            return delta.days
        return None
    
    def _repeat_interval_token(self):
        """UI 'Repeats' token derived from the recurrence columns (F18)."""
        if not self.recurring or not self.frequency:
            return ''
        return {
            ('weekly', 1): '1_week',
            ('monthly', 1): '1_month',
            ('monthly', 3): '3_months',
            ('monthly', 6): '6_months',
            ('yearly', 1): '1_year',
            ('yearly', 2): '2_years',
        }.get((self.frequency, self.frequency_value or 1), '')

    def to_dict(self, **kwargs):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'revision': self.revision,
            'title': self.title,
            'description': self.description,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'due_mileage': self.due_mileage,
            'reminder_type': self.reminder_type,
            'priority': self.priority,
            'recurring': self.recurring,
            'frequency': self.frequency,
            'frequency_value': self.frequency_value,
            'repeat_interval': self._repeat_interval_token(),
            'repeat_mileage': self.repeat_mileage,
            'recurrence_anchor_date': self.recurrence_anchor_date.isoformat() if self.recurrence_anchor_date else None,
            'notify_days_before': self.notify_days_before,
            'notify_push': self.notify_push,
            'notify_email': self.notify_email,
            'completed': self.completed,
            'completed_at': isoformat_utc(self.completed_at) if self.completed_at else None,
            'dismissed': self.dismissed,
            'snoozed_until': isoformat_utc(self.snoozed_until) if self.snoozed_until else None,
            'is_overdue': self.is_overdue,
            'days_until_due': self.days_until_due,
            'vehicle_id': self.vehicle_id,
            'vehicle_name': self.vehicle.name if self.vehicle else None,
            'vehicle_distance_unit': self.vehicle.distance_unit if self.vehicle else 'km',
            'calendar_sync': self.calendar_sync,
            'sync_conflict': self.sync_conflict,
            'source_service_id': self.source_service_id,
            'created_at': isoformat_utc(self.created_at) if self.created_at else None,
        }
