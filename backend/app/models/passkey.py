"""
GearCargo - Passkey Model

A passkey signs a person in with their device's own lock (fingerprint, face or
PIN) instead of a password and a code. Only the public key is kept here: the
private half never leaves the authenticator.

Each passkey belongs to the hostname it was created for, so ``relying_party_id``
is stored alongside it. A self-hosted deployment reached by a new name keeps the
old rows, and they are shown as belonging elsewhere rather than silently
refusing to work.
"""

import json

from app import db
from app.utils.timeutils import isoformat_utc, utc_naive_now

CREDENTIAL_ID_LENGTH = 512
PUBLIC_KEY_LENGTH = 1024
RELYING_PARTY_ID_LENGTH = 253
PASSKEY_NAME_LENGTH = 100


class Passkey(db.Model):
    """A WebAuthn credential registered by one user."""

    __tablename__ = 'passkeys'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    relying_party_id = db.Column(db.String(RELYING_PARTY_ID_LENGTH), nullable=False)
    credential_id = db.Column(db.String(CREDENTIAL_ID_LENGTH), nullable=False)
    public_key = db.Column(db.String(PUBLIC_KEY_LENGTH), nullable=False)

    # Raised by the authenticator on every use; a value that fails to advance
    # suggests a cloned credential, so the sign-in is refused.
    sign_count = db.Column(db.BigInteger, nullable=False, default=0)

    transports = db.Column(db.Text, nullable=False, default='[]')
    # True when the authenticator syncs the key between a person's devices.
    backed_up = db.Column(db.Boolean, nullable=False, default=False)

    name = db.Column(db.String(PASSKEY_NAME_LENGTH), nullable=False)

    created_at = db.Column(db.DateTime, default=utc_naive_now)
    last_used_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('credential_id', name='uq_passkey_credential_id'),
    )

    def __repr__(self):
        return f'<Passkey {self.id} - {self.name}>'

    @property
    def transport_list(self):
        """Transports the authenticator reported, or an empty list when unreadable."""
        try:
            stored = json.loads(self.transports or '[]')
        except (TypeError, ValueError):
            return []
        if not isinstance(stored, list):
            return []
        return [item for item in stored if isinstance(item, str)]

    @transport_list.setter
    def transport_list(self, values):
        self.transports = json.dumps([str(value) for value in (values or [])])

    def to_dict(self, current_relying_party_id=None):
        """Serialise for the API.

        ``other_relying_party`` names the hostname a passkey was created for when
        that is not the one being served now, which is why it cannot be used.
        """
        belongs_here = (
            current_relying_party_id is not None
            and self.relying_party_id == current_relying_party_id
        )
        return {
            'id': self.id,
            'name': self.name,
            'backed_up': self.backed_up,
            'created_at': isoformat_utc(self.created_at) if self.created_at else None,
            'last_used_at': isoformat_utc(self.last_used_at) if self.last_used_at else None,
            'other_relying_party': None if belongs_here else self.relying_party_id,
        }
