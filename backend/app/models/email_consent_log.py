"""
GearCargo - Email Consent Log Model
Immutable, append-only ledger for GDPR compliance.
Records every consent grant, revocation, verification, and change.
"""

from datetime import datetime
from app import db


class EmailConsentLog(db.Model):
    """Immutable consent ledger — insert only, never update or delete."""

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

    # Timestamp — set once, never changed
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

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
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def record(cls, user_id, action, email_hash, ip_address=None, user_agent=None,
               consent_text_version='1.0'):
        """Create an immutable consent record."""
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
