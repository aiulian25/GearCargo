"""
GearCargo - Reminder Model
"""

from datetime import datetime, timezone
from app import db


class Reminder(db.Model):
    """Reminder model for maintenance tasks and notifications."""
    
    __tablename__ = 'reminders'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Content
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Scheduling
    due_date = db.Column(db.Date, nullable=False)
    due_mileage = db.Column(db.Integer)
    reminder_type = db.Column(db.String(30))  # maintenance, insurance, inspection, custom
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    
    # Recurrence
    recurring = db.Column(db.Boolean, default=False)
    frequency = db.Column(db.String(20))  # daily, weekly, monthly, yearly
    frequency_value = db.Column(db.Integer, default=1)  # Every X days/weeks/etc.
    recurrence_end = db.Column(db.Date)
    
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
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    
    def to_dict(self, **kwargs):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'due_mileage': self.due_mileage,
            'reminder_type': self.reminder_type,
            'priority': self.priority,
            'recurring': self.recurring,
            'frequency': self.frequency,
            'completed': self.completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'dismissed': self.dismissed,
            'is_overdue': self.is_overdue,
            'days_until_due': self.days_until_due,
            'vehicle_id': self.vehicle_id,
            'vehicle_name': self.vehicle.name if self.vehicle else None,
            'vehicle_distance_unit': self.vehicle.distance_unit if self.vehicle else 'km',
            'calendar_sync': self.calendar_sync,
            'sync_conflict': self.sync_conflict,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
