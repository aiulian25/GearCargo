"""
GearCargo - Report Share Model (F05)

Signed, expiring, revocable read-only share links for expense reports.

Security model
--------------
* The raw share token (``secrets.token_urlsafe(32)`` — 256 bits) is shown to the
  owner ONCE at creation and never stored. Only its SHA-256 hash is persisted,
  so a database leak cannot reconstruct working links (same pattern as
  api_key_hash / password_reset_token).
* Links are time-limited (``expires_at``) AND revocable (``revoked``), giving the
  owner both automatic and manual access control.
* Public access reveals only the aggregate report (vehicle make/model/name +
  expense totals) — never email, VIN, plate, addresses or attachments.
"""

import hashlib
import secrets
from datetime import datetime, timezone

from app import db


class ReportShare(db.Model):
    __tablename__ = 'report_shares'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)

    # SHA-256 hex of the raw token (unique) + a short non-secret prefix for display.
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    token_prefix = db.Column(db.String(12))

    label = db.Column(db.String(120))

    # Report parameters (mirror the /reports endpoints). vehicle_ids = None → all.
    vehicle_ids = db.Column(db.JSON)
    period = db.Column(db.String(20), default='current_month')
    year = db.Column(db.Integer)
    month = db.Column(db.Integer)

    # Lifecycle / access controls
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked = db.Column(db.Boolean, nullable=False, default=False, index=True)
    revoked_at = db.Column(db.DateTime)

    # Access telemetry (transparency for the owner)
    access_count = db.Column(db.Integer, nullable=False, default=0)
    last_accessed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])

    # ------------------------------------------------------------------
    @staticmethod
    def hash_token(raw_token: str) -> str:
        """SHA-256 hex of a raw token, for storage and lookup."""
        return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()

    @classmethod
    def new_token(cls):
        """Return (raw_token, token_hash, token_prefix). Raw is shown once."""
        raw = secrets.token_urlsafe(32)
        return raw, cls.hash_token(raw), raw[:8]

    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= datetime.utcnow()

    def is_active(self) -> bool:
        return not self.revoked and not self.is_expired()

    def status(self) -> str:
        if self.revoked:
            return 'revoked'
        if self.is_expired():
            return 'expired'
        return 'active'

    def to_dict(self):
        """Owner-facing serialisation. Never includes the raw token."""
        return {
            'id': self.id,
            'label': self.label,
            'token_prefix': self.token_prefix,
            'vehicle_ids': self.vehicle_ids,
            'period': self.period,
            'year': self.year,
            'month': self.month,
            'status': self.status(),
            'revoked': self.revoked,
            'expires_at': self.expires_at.replace(tzinfo=timezone.utc).isoformat() if self.expires_at else None,
            'access_count': self.access_count,
            'last_accessed_at': self.last_accessed_at.replace(tzinfo=timezone.utc).isoformat() if self.last_accessed_at else None,
            'created_at': self.created_at.replace(tzinfo=timezone.utc).isoformat() if self.created_at else None,
        }
