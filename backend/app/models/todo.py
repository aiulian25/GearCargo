"""
GearCargo - Todo Model
"""

from datetime import datetime
from app import db


class Todo(db.Model):
    """Todo model for vehicle-related tasks."""
    
    __tablename__ = 'todos'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Content
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Scheduling
    due_date = db.Column(db.Date)
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    
    # Status
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Todo {self.title}>'
    
    def mark_complete(self):
        """Mark todo as complete."""
        self.completed = True
        self.completed_at = datetime.utcnow()
    
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
            return self.due_date < datetime.utcnow().date()
        return False
    
    @property
    def days_until_due(self):
        """Days until due date."""
        if self.due_date:
            delta = self.due_date - datetime.utcnow().date()
            return delta.days
        return None
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'priority': self.priority,
            'completed': self.completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'is_overdue': self.is_overdue,
            'days_until_due': self.days_until_due,
            'vehicle_id': self.vehicle_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
