"""
GearCargo - Service Entry Model
"""

from app import db
from app.models.entry import Entry


class ServiceEntry(Entry):
    """Service entry for maintenance records."""
    
    __tablename__ = 'service_entries'
    
    id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    
    # Service specific
    service_type = db.Column(db.String(50))  # Legacy single type (first selected type)
    service_types = db.Column(db.JSON)  # Multi-select: list of service type values
    provider = db.Column(db.String(100))
    garage_name = db.Column(db.String(100))
    garage_address = db.Column(db.String(255))
    garage_phone = db.Column(db.String(20))
    postcode = db.Column(db.String(20))
    
    # Work details
    work_order_number = db.Column(db.String(50))
    labor_hours = db.Column(db.Numeric(5, 2))
    labor_cost = db.Column(db.Numeric(10, 2))
    parts_cost = db.Column(db.Numeric(10, 2))
    parts_used = db.Column(db.JSON)  # List of parts
    
    # Warranty
    warranty_months = db.Column(db.Integer)
    warranty_km = db.Column(db.Integer)
    warranty_notes = db.Column(db.Text)
    warranty_expires = db.Column(db.Date)
    
    # Next service
    next_due_date = db.Column(db.Date)
    next_due_mileage = db.Column(db.Integer)
    
    __mapper_args__ = {
        'polymorphic_identity': 'service'
    }
    
    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            'service_type': self.service_type,
            'service_types': self.service_types or ([self.service_type] if self.service_type else []),
            'provider': self.provider,
            'garage_name': self.garage_name,
            'garage_address': self.garage_address,
            'labor_hours': float(self.labor_hours) if self.labor_hours else None,
            'labor_cost': float(self.labor_cost) if self.labor_cost else None,
            'parts_cost': float(self.parts_cost) if self.parts_cost else None,
            'parts_used': self.parts_used,
            'warranty_months': self.warranty_months,
            'next_due_date': self.next_due_date.isoformat() if self.next_due_date else None,
            'next_due_mileage': self.next_due_mileage,
        })
        return data
