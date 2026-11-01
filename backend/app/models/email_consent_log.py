"""
GearCargo - Email Consent Log Model
Application-written history of notification-email consent actions.
These ordinary database rows are not tamper-proof and are deleted with the
account; recording consent does not by itself establish legal compliance.
"""

from datetime import datetime
from app.utils.timeutils import utc_naive_now, isoformat_utc
from app import db


class EmailConsentLog(db.Model):
    """Consent history; normal routes append rows, account deletion removes them."""

    __tablename__ = 'email_consent_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Action: grant | revoke | verify | change | bounce_disable | unsubscribe
    action = db.Column(db.String(30), nullable=False, index=True)

    # SHA-256 hash of the email address (allows audit without storing plaintext twice)
    email_hash = db.Column(db.String(64), nullable=False)

    # Version of consent text shown to user at the time of action
    consent_text_version = db.Column(db.String(20), default='1.0')

    # Request context at time of action
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))

    # Creation timestamp; no database immutability constraint is applied
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now, index=True)

    # Relationship
    user = db.relationship('User', backref=db.backref('email_consent_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<EmailConsentLog {self.id} user={self.user_id} action={self.action}>'

    def to_dict(self):
        return {
            'id': self.id,
            'action': self.action,
            'consent_text_version': self.consent_text_version,
            'ip_address': self.ip_address,
            'created_at': isoformat_utc(self.created_at) if self.created_at else None,
        }

    @classmethod
    def record(cls, user_id, action, email_hash, ip_address=None, user_agent=None,
               consent_text_version='1.0'):
        """Append a consent-action record to the current transaction."""
        entry = cls(
            user_id=user_id,
            action=action,
            email_hash=email_hash,
            consent_text_version=consent_text_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(entry)
        # Caller is responsible for db.session.commit()
        return entry
