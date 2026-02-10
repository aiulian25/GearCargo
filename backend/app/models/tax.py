"""
GearCargo - Tax Entry Model
"""

from app import db
from app.models.entry import Entry


class TaxEntry(Entry):
    """Tax entry for vehicle taxes."""
    
    __tablename__ = 'tax_entries'
    
    id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    
    # Tax specific
    tax_type = db.Column(db.String(50))  # road_tax, registration, emissions, etc.
    tax_year = db.Column(db.Integer)
    tax_period = db.Column(db.String(20))  # annual, semi_annual, quarterly
    tax_rate = db.Column(db.Numeric(10, 2))
    
    # Linked insurance policy (optional)
    insurance_policy_id = db.Column(db.Integer, db.ForeignKey('insurance_policies.id'), nullable=True, index=True)
    
    # Status
    status = db.Column(db.String(20), default='paid')  # paid, pending, overdue
    due_date = db.Column(db.Date)
    paid_date = db.Column(db.Date)
    
    # Filing
    filing_date = db.Column(db.Date)
    reference_number = db.Column(db.String(50))
    
    # Recurring
    recurring = db.Column(db.Boolean, default=False)
    recurrence_type = db.Column(db.String(20))  # monthly, quarterly, semi_annual, annual
    next_due_date = db.Column(db.Date)
    reminder_days = db.Column(db.Integer, default=30)  # Days before due date to remind
    
    __mapper_args__ = {
        'polymorphic_identity': 'tax'
    }
    
    # Relationship to insurance policy
    insurance_policy = db.relationship('InsurancePolicy', foreign_keys=[insurance_policy_id], lazy='joined')
    
    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            'tax_type': self.tax_type,
            'tax_year': self.tax_year,
            'tax_period': self.tax_period,
            'status': self.status,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'paid_date': self.paid_date.isoformat() if self.paid_date else None,
            'reference_number': self.reference_number,
            'recurring': self.recurring,
            'recurrence_type': self.recurrence_type,
            'next_due_date': self.next_due_date.isoformat() if self.next_due_date else None,
            'reminder_days': self.reminder_days,
            'insurance_policy_id': self.insurance_policy_id,
            'insurance_policy': self.insurance_policy.to_dict() if self.insurance_policy else None,
        })
        return data
