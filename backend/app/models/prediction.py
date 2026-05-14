"""
GearCargo - Prediction Alert Model
"""

from datetime import datetime, timezone
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
    
    # Extended prediction data (added via migration h6i7j8k9l0m1)
    title = db.Column(db.String(255))
    urgency = db.Column(db.String(20))  # low, medium, high (raw Ollama output)
    estimated_cost = db.Column(db.Numeric(10, 2))
    recommended_action = db.Column(db.Text)
    source_data = db.Column(db.JSON)  # metadata only — no PII.
    # Schema: {model, vehicle_id, prompt_sha256 (16-char hex), prompt_chars,
    #          anomaly_type?, trigger_entry_id?, mileage_notified?}
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<PredictionAlert {self.alert_type}: {self.severity}>'
    
    def dismiss(self):
        """Dismiss the alert."""
        self.dismissed = True
        self.dismissed_at = datetime.now(timezone.utc)
    
    def mark_actioned(self):
        """Mark as user took action."""
        self.actioned = True
        self.actioned_at = datetime.now(timezone.utc)
    
    @property
    def is_active(self):
        """Check if alert is still active."""
        if self.dismissed or self.actioned:
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
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
        _i18n = self.i18n_params or {}
        # Build localised title — fall back to the stored English title so
        # older predictions (before multilingual was added) still display.
        localized_title = (
            _i18n.get('title_ro', '') if locale == 'ro' else
            _i18n.get('title_es', '') if locale == 'es' else
            _i18n.get('title_en', '')
        ) or self.title

        # Localised recommended_action — falls back to English if translation absent
        localized_action = (
            _i18n.get('recommended_action_ro', '') if locale == 'ro' else
            _i18n.get('recommended_action_es', '') if locale == 'es' else
            None
        ) or self.recommended_action

        return {
            'id': self.id,
            'alert_type': self.alert_type,
            'title': localized_title,
            # Keep English variants for reference/debug and client-side locale switching
            'title_en': _i18n.get('title_en', self.title),
            'description': self.get_localized_description(locale),
            # All description variants so the frontend can switch locale client-side
            'description_en': self.description_en_us or self.description or '',
            'description_ro': self.description_ro or '',
            'description_es': self.description_es or '',
            # All title variants for the same reason
            'title_ro': _i18n.get('title_ro', ''),
            'title_es': _i18n.get('title_es', ''),
            'predicted_mileage': self.predicted_mileage,
            'predicted_date': self.predicted_date.isoformat() if self.predicted_date else None,
            'confidence_score': self.confidence_score,
            'severity': self.severity,
            'urgency': self.urgency,
            'estimated_cost': float(self.estimated_cost) if self.estimated_cost is not None else None,
            'recommended_action': localized_action,
            'recommended_action_en': self.recommended_action,
            'dismissed': self.dismissed,
            'actioned': self.actioned,
            'is_active': self.is_active,
            'generated_by': self.generated_by,
            'model_version': self.model_version,
            'user_id': self.user_id,
            'vehicle_id': self.vehicle_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
