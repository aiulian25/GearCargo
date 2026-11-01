"""
GearCargo - Todo Model
"""

from datetime import datetime, timezone
from app.utils.timeutils import utc_naive_now, isoformat_utc
from app import db
from app.utils.revisions import next_revision


class Todo(db.Model):
    """Todo model for vehicle-related tasks."""
    
    __tablename__ = 'todos'
    __table_args__ = (db.UniqueConstraint('completed_from_id', name='uq_todos_completed_from'),)
    
    id = db.Column(db.Integer, primary_key=True)
    revision = db.Column(db.BigInteger, nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": next_revision}
    
    # Content
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Scheduling
    due_date = db.Column(db.Date)
    priority = db.Column(db.String(10), default='medium')  # low, medium, high

    completed_from_id = db.Column(db.Integer, db.ForeignKey('todos.id', name='fk_todos_completed_from', ondelete='SET NULL'), nullable=True)

    # Recurrence (F15 — parity with reminders): a recurring todo respawns its
    # next occurrence on completion, advancing due_date by frequency×value.
    recurring = db.Column(db.Boolean, default=False)
    frequency = db.Column(db.String(20))  # daily, weekly, monthly, yearly
    frequency_value = db.Column(db.Integer, default=1)  # every X days/weeks/…

    # Status
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, default=utc_naive_now, onupdate=utc_naive_now)
    
    def __repr__(self):
        return f'<Todo {self.title}>'
    
    def mark_complete(self):
        """Mark todo as complete."""
        self.completed = True
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_incomplete(self):
        """Mark todo as incomplete."""
        self.completed = False
        self.completed_at = None
    
    @property
    def is_overdue(self):
        """Check if todo is overdue."""
        if self.completed:
            return False
        if self.due_date:
            return self.due_date < datetime.now(timezone.utc).date()
        return False
    
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
            'revision': self.revision,
            'title': self.title,
            'description': self.description,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'priority': self.priority,
            'recurring': self.recurring,
            'frequency': self.frequency,
            'frequency_value': self.frequency_value,
            'completed': self.completed,
            'completed_at': isoformat_utc(self.completed_at) if self.completed_at else None,
            'is_overdue': self.is_overdue,
            'days_until_due': self.days_until_due,
            'vehicle_id': self.vehicle_id,
            'user_id': self.user_id,
            'created_at': isoformat_utc(self.created_at) if self.created_at else None,
            'updated_at': isoformat_utc(self.updated_at) if self.updated_at else None,
        }
