"""
GearCargo - Insurance Policy Model
"""

from datetime import datetime, date
from app import db


class InsurancePolicy(db.Model):
    """Insurance policy model."""
    
    __tablename__ = 'insurance_policies'
    
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Policy details
    policy_number = db.Column(db.String(100))
    provider = db.Column(db.String(255), nullable=False)
    policy_type = db.Column(db.String(50))  # comprehensive, third_party, collision, etc.
    
    # Coverage
    coverage_amount = db.Column(db.Numeric(12, 2))
    deductible = db.Column(db.Numeric(10, 2))
    coverage_details = db.Column(db.JSON)  # Detailed breakdown
    
    # Cost
    premium = db.Column(db.Numeric(10, 2), nullable=False)
    payment_frequency = db.Column(db.String(20))  # monthly, quarterly, annual
    currency = db.Column(db.String(3), default='USD')
    
    # Dates
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    
    # Contact
    agent_name = db.Column(db.String(255))
    agent_phone = db.Column(db.String(50))
    agent_email = db.Column(db.String(255))
    claims_phone = db.Column(db.String(50))
    
    # Documents
    document_attachment_id = db.Column(db.Integer, db.ForeignKey('attachments.id'))
    
    # Status
    status = db.Column(db.String(20), default='active')  # active, expired, cancelled
    auto_renew = db.Column(db.Boolean, default=False)
    # F6: set on a policy auto-created by the renewal job; links back to the
    # policy it was renewed from. Drives dedup + the "confirm premium" UI prompt,
    # and is cleared once the user edits (confirms) the renewed policy.
    renewed_from_id = db.Column(db.Integer, db.ForeignKey('insurance_policies.id'), nullable=True, index=True)

    # Notes
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = db.relationship('Attachment', foreign_keys=[document_attachment_id])
    
    def __repr__(self):
        return f'<InsurancePolicy {self.policy_number}>'

    # F12: how many premium payments make up one year, per payment frequency.
    # Single source of truth for annualizing a premium in analytics/forecasts.
    FREQUENCY_MULTIPLIER = {
        'monthly': 12,
        'quarterly': 4,
        'semi-annual': 2,
        'semi_annual': 2,
        'annual': 1,
        'yearly': 1,
        'one_time': 1,
    }

    @property
    def annualized_premium(self):
        """Premium normalized to a yearly cost, respecting ``payment_frequency``.

        A €100/month policy and a €1,200/year policy both return 1200.0, so
        analytics compare like-for-like instead of double- or under-counting.
        An unknown/blank frequency is treated as annual (multiplier 1).
        """
        if self.premium is None:
            return 0.0
        mult = self.FREQUENCY_MULTIPLIER.get(self.payment_frequency or 'annual', 1)
        return float(self.premium) * mult

    @property
    def is_active(self):
        """Check if policy is currently active."""
        today = date.today()
        return self.start_date <= today <= self.end_date and self.status == 'active'
    
    @property
    def days_until_expiry(self):
        """Days until policy expires."""
        if self.end_date:
            delta = self.end_date - date.today()
            return delta.days
        return None
    
    @property
    def is_expiring_soon(self):
        """Check if expiring within 30 days."""
        days = self.days_until_expiry
        return days is not None and 0 < days <= 30
    
    def to_dict(self):
        """Convert to dictionary."""
        # Build attachments array from document if exists
        attachments = []
        if self.document:
            attachments.append(self.document.to_dict())
        
        return {
            'id': self.id,
            'vehicle_id': self.vehicle_id,
            'policy_number': self.policy_number,
            'provider': self.provider,
            'policy_type': self.policy_type,
            'coverage_amount': float(self.coverage_amount) if self.coverage_amount else None,
            'deductible': float(self.deductible) if self.deductible else None,
            'premium': float(self.premium) if self.premium else None,
            'payment_frequency': self.payment_frequency,
            'annualized_premium': self.annualized_premium,  # F12 — premium × freq
            'currency': self.currency,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'agent_name': self.agent_name,
            'agent_phone': self.agent_phone,
            'agent_email': self.agent_email,
            'claims_phone': self.claims_phone,
            'document_attachment_id': self.document_attachment_id,
            'attachments': attachments,  # Include attachments array for frontend compatibility
            'status': self.status,
            'is_active': self.is_active,
            'days_until_expiry': self.days_until_expiry,
            'is_expiring_soon': self.is_expiring_soon,
            'auto_renew': self.auto_renew,
            'renewed_from_id': self.renewed_from_id,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
