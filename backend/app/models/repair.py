"""
GearCargo - Repair Entry Model
"""

from app import db
from app.models.entry import Entry


class RepairEntry(Entry):
    """Repair entry for tracking repairs."""
    
    __tablename__ = 'repair_entries'
    
    id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    
    # Repair specific
    repair_type = db.Column(db.String(50))
    diagnosis = db.Column(db.Text)
    symptoms = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    
    # Work details
    provider = db.Column(db.String(100))
    garage_name = db.Column(db.String(100))
    garage_address = db.Column(db.String(255))
    labor_hours = db.Column(db.Numeric(5, 2))
    labor_cost = db.Column(db.Numeric(10, 2))
    parts_cost = db.Column(db.Numeric(10, 2))
    parts_replaced = db.Column(db.JSON)
    
    # Warranty
    warranty_months = db.Column(db.Integer)
    warranty_km = db.Column(db.Integer)
    warranty_notes = db.Column(db.Text)
    under_warranty = db.Column(db.Boolean, default=False)  # Covered by existing warranty
    
    # Severity
    severity = db.Column(db.String(20))  # minor, moderate, major, critical
    
    __mapper_args__ = {
        'polymorphic_identity': 'repair'
    }
    
    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            'repair_type': self.repair_type,
            'diagnosis': self.diagnosis,
            'symptoms': self.symptoms,
            'provider': self.provider,
            'garage_name': self.garage_name,
            'labor_hours': float(self.labor_hours) if self.labor_hours else None,
            'labor_cost': float(self.labor_cost) if self.labor_cost else None,
            'parts_cost': float(self.parts_cost) if self.parts_cost else None,
            'parts_replaced': self.parts_replaced,
            'severity': self.severity,
            'under_warranty': self.under_warranty,
        })
        return data
