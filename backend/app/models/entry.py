"""
GearCargo - Base Entry Model (Joined Table Inheritance)
"""

from datetime import datetime
from app.utils.timeutils import utc_naive_now, isoformat_utc
from app import db
from app.utils.revisions import next_revision


class Entry(db.Model):
    """Base entry model for all expense types."""
    
    __tablename__ = 'entries'
    
    id = db.Column(db.Integer, primary_key=True)
    revision = db.Column(db.BigInteger, nullable=False, default=1, server_default="1")
    type = db.Column(db.String(50))  # Discriminator column
    
    # Common fields
    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(3), default='EUR')
    odometer = db.Column(db.Integer)
    date = db.Column(db.Date, nullable=False, default=utc_naive_now)
    notes = db.Column(db.Text)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, default=utc_naive_now, onupdate=utc_naive_now)
    
    # Relationships
    # R4-15: a plain (not 'dynamic') relationship, so the paginated list
    # endpoints can batch it with selectinload. to_dict is its only consumer,
    # and it wants the whole collection every time — a query object bought
    # nothing and cost one round trip per serialized row.
    attachments = db.relationship('Attachment', backref='entry',
                                  foreign_keys='Attachment.entry_id')

    __table_args__ = (
        db.Index('ix_entries_user_vehicle_date_id', 'user_id', 'vehicle_id', 'date', 'id'),
    )
    
    __mapper_args__ = {
        'polymorphic_identity': 'entry',
        'polymorphic_on': type,
        'version_id_col': revision,
        'version_id_generator': next_revision
    }
    
    def __repr__(self):
        return f'<Entry {self.type}: {self.title}>'
    
    def to_dict(self, include_attachments=True):
        """Convert to dictionary."""
        amount_value = float(self.amount) if self.amount else 0
        data = {
            'id': self.id,
            'revision': self.revision,
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
            'created_at': isoformat_utc(self.created_at) if self.created_at else None,
        }
        
        # Include attachments if requested. Batched by the list endpoints via
        # selectinload; a single-entry read still costs one query.
        if include_attachments:
            data['attachments'] = [a.to_dict() for a in self.attachments]
        
        return data
