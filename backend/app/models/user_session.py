"""
GearCargo - User Session Model

S01 (IMPROVEMENTS.md §1.1): durable, database-backed mirror of the Redis
session store.  Redis remains the fast path for session validation, single-device
enforcement, the 48-hour absolute-expiry wall, and logout/blacklist revocation.
This table is the *fallback* consulted only when Redis is unavailable, so a Redis
outage no longer silently fails OPEN (accepting stale / revoked / cross-device
tokens).  It mirrors the existing DB-backed account-lockout fallback pattern
(see ``_db_is_account_locked`` in routes/auth.py).

All timestamps are stored as naive UTC (``datetime.utcnow``) to match the rest of
the schema (e.g. blocked_entity, user).  Helper comparisons in routes/auth.py
always compare against a naive-UTC "now", so there is never an aware/naive mix.
"""

from datetime import datetime
from app import db


class UserSession(db.Model):
    """A single authenticated session, keyed by its JWT ``jti``.

    One row is written per ``generate_tokens()`` call (login + every refresh).
    Rows are revoked (not deleted) on logout / session invalidation so the
    Redis-down validation path can reject them; expired and revoked rows are
    purged by the daily ``cleanup_old_data`` scheduler job.
    """

    __tablename__ = 'user_sessions'

    id = db.Column(db.Integer, primary_key=True)

    # Owner of the session. Indexed for fast per-user lookups / bulk revoke.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    # JWT ID — the session identifier embedded in both access and refresh tokens.
    # Unique + indexed: validation looks a session up by (user_id, jti).
    jti = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # Non-sliding 48h wall. Copied from the original login on every refresh so
    # refreshing never extends the window. Validation rejects once this passes.
    absolute_expires_at = db.Column(db.DateTime, nullable=False, index=True)

    # Revocation — set True on logout / single-device invalidation. The Redis-down
    # validation path treats a revoked row as invalid, preserving logout semantics
    # without Redis.
    revoked = db.Column(db.Boolean, nullable=False, default=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Diagnostic context (mirrors the Redis session payload). Never used for auth
    # decisions — purely for an "active sessions" view / audit.
    user_agent = db.Column(db.String(255))
    ip = db.Column(db.String(45))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        state = 'revoked' if self.revoked else 'active'
        return f'<UserSession user={self.user_id} jti={self.jti[:8]}… {state}>'

    def to_dict(self):
        """Serialise for an active-sessions UI (no secrets are exposed)."""
        return {
            'id': self.id,
            'jti_prefix': (self.jti[:8] + '…') if self.jti else None,
            'absolute_expires_at': self.absolute_expires_at.isoformat() if self.absolute_expires_at else None,
            'revoked': self.revoked,
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'user_agent': self.user_agent,
            'ip': self.ip,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
