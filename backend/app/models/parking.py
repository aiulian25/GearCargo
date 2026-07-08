"""
GearCargo - Parking Entry Model
"""

from app import db
from app.models.entry import Entry


class ParkingEntry(Entry):
    """Parking entry for parking expenses."""
    
    __tablename__ = 'parking_entries'
    
    id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    
    # Parking specific
    parking_type = db.Column(db.String(30))  # street, garage, lot, permit, fine
    location = db.Column(db.String(255))
    location_address = db.Column(db.String(255))
    
    # Time
    start_datetime = db.Column(db.DateTime)
    end_datetime = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Integer)
    
    # Recurring (for permits)
    recurring = db.Column(db.Boolean, default=False)
    recurrence_type = db.Column(db.String(20))  # daily, weekly, monthly, annual
    next_due_date = db.Column(db.Date)
    reminder_days = db.Column(db.Integer, default=7)  # Days before expiry to remind
    permit_number = db.Column(db.String(50))
    permit_expires = db.Column(db.Date)
    
    # Fine specific
    fine_reason = db.Column(db.String(255))
    fine_status = db.Column(db.String(20))  # pending, paid, contested
    
    __mapper_args__ = {
        'polymorphic_identity': 'parking'
    }
    
    def to_dict(self, **kwargs):
        """Convert to dictionary."""
        data = super().to_dict(**kwargs)
        data.update({
            'parking_type': self.parking_type,
            'location': self.location,
            'location_address': self.location_address,
            'start_datetime': self.start_datetime.isoformat() if self.start_datetime else None,
            'end_datetime': self.end_datetime.isoformat() if self.end_datetime else None,
            'duration_minutes': self.duration_minutes,
            'recurring': self.recurring,
            'recurrence_type': self.recurrence_type,
            'next_due_date': self.next_due_date.isoformat() if self.next_due_date else None,
            'reminder_days': self.reminder_days,
            'permit_number': self.permit_number,
            'permit_expires': self.permit_expires.isoformat() if self.permit_expires else None,
            # Fines (F14)
            'fine_reason': self.fine_reason,
            'fine_status': self.fine_status,
        })
        return data
