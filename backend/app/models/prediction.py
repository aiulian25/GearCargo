"""
GearCargo - Prediction Alert Model
"""

from datetime import datetime
from app import db


class PredictionAlert(db.Model):
    """AI-generated maintenance prediction alerts."""
    
    __tablename__ = 'prediction_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Alert content
    alert_type = db.Column(db.String(50), nullable=False)  # oil_change, tire_rotation, etc.
    description = db.Column(db.Text)
    
    # Prediction details
    predicted_mileage = db.Column(db.Integer)  # Trigger at this mileage
    predicted_date = db.Column(db.Date)  # Or this date
    confidence_score = db.Column(db.Float)  # 0-1 confidence
    
    # Severity
    severity = db.Column(db.String(20), default='info')  # critical, warning, info
    
    # Status
    dismissed = db.Column(db.Boolean, default=False)
    dismissed_at = db.Column(db.DateTime)
    actioned = db.Column(db.Boolean, default=False)  # User took action
    actioned_at = db.Column(db.DateTime)
    
    # Translation support
    i18n_key = db.Column(db.String(100))  # Translation key
    i18n_params = db.Column(db.JSON)  # Parameters for translation
    description_en_us = db.Column(db.Text)
    description_ro = db.Column(db.Text)
    description_es = db.Column(db.Text)
    
    # Source
    generated_by = db.Column(db.String(30))  # rule_engine, ollama, manual
    model_version = db.Column(db.String(20))
    
    # Foreign keys
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<PredictionAlert {self.alert_type}: {self.severity}>'
    
    def dismiss(self):
        """Dismiss the alert."""
        self.dismissed = True
        self.dismissed_at = datetime.utcnow()
    
    def mark_actioned(self):
        """Mark as user took action."""
        self.actioned = True
        self.actioned_at = datetime.utcnow()
    
    @property
    def is_active(self):
        """Check if alert is still active."""
        if self.dismissed or self.actioned:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
    
    def get_localized_description(self, locale='en-US'):
        """Get description in specified locale."""
        locale_map = {
            'en-US': self.description_en_us,
            'ro': self.description_ro,
            'es': self.description_es,
        }
        return locale_map.get(locale) or self.description
    
    def to_dict(self, locale='en-US'):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'alert_type': self.alert_type,
            'description': self.get_localized_description(locale),
            'predicted_mileage': self.predicted_mileage,
            'predicted_date': self.predicted_date.isoformat() if self.predicted_date else None,
            'confidence_score': self.confidence_score,
            'severity': self.severity,
            'dismissed': self.dismissed,
            'actioned': self.actioned,
            'is_active': self.is_active,
            'vehicle_id': self.vehicle_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
