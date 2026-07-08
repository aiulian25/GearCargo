"""
GearCargo - Due Dismissal Model

Stores a user's "don't show me this again" choices for the unified
"Coming up" feed (F4). One row = one dismissed OCCURRENCE of one item:
``kind`` + ``ref_id`` identify the source record and ``due_date`` pins the
occurrence, so a recurring obligation reappears once it advances to a new
due date. Kinds without a date (consumable wear, fines) store NULL and stay
hidden until un-dismissed.

Reminders are NOT stored here — dismissing a reminder sets the existing
``Reminder.dismissed`` flag, which also silences its push/email pipeline.
"""

from datetime import datetime
from app import db


class DueDismissal(db.Model):
    __tablename__ = 'due_dismissals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    ref_id = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_due_dismissals_lookup', 'user_id', 'kind', 'ref_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'kind': self.kind,
            'ref_id': self.ref_id,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
