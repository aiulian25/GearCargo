"""
GearCargo - Base Entry Model (Joined Table Inheritance)
"""

from datetime import datetime
from app import db


class Entry(db.Model):
    """Base entry model for all expense types."""
    
    __tablename__ = 'entries'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50))  # Discriminator column
    
    # Common fields
    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(3), default='EUR')
    odometer = db.Column(db.Integer)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    attachments = db.relationship('Attachment', backref='entry', lazy='dynamic',
                                  foreign_keys='Attachment.entry_id')
    
    __mapper_args__ = {
        'polymorphic_identity': 'entry',
        'polymorphic_on': type
    }
    
    def __repr__(self):
        return f'<Entry {self.type}: {self.title}>'
    
    def to_dict(self, include_attachments=True):
        """Convert to dictionary."""
        amount_value = float(self.amount) if self.amount else 0
        data = {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'description': self.description or self.title or '',
            'amount': amount_value,
            'cost': amount_value,  # Alias for frontend compatibility
            'currency': self.currency,
            'odometer': self.odometer,
            'date': self.date.isoformat() if self.date else None,
            'notes': self.notes,
            'vehicle_id': self.vehicle_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        
        # Include attachments if requested
        if include_attachments:
            data['attachments'] = [a.to_dict() for a in self.attachments.all()]
        
        return data
