"""Latest desired remote state per account, calendar destination and entry."""
from app import db
from app.utils.timeutils import utc_naive_now


class CalendarOutbox(db.Model):
    __tablename__ = 'calendar_outbox'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'source_key', 'entry_type', 'entry_id', name='uq_calendar_outbox_target'),
        db.Index('ix_calendar_outbox_due', 'status', 'next_attempt_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    # No source/vehicle FK: deletion tombstones must outlive the local record.
    source_id = db.Column(db.Text, nullable=False)
    source_key = db.Column(db.String(64), nullable=False)
    entry_type = db.Column(db.String(20), nullable=False)
    entry_id = db.Column(db.Integer, nullable=False)
    vehicle_id = db.Column(db.Integer)
    uid = db.Column(db.String(255), nullable=False)
    operation = db.Column(db.String(10), nullable=False)
    payload = db.Column(db.JSON)
    payload_hash = db.Column(db.String(64), nullable=False)
    generation = db.Column(db.Integer, nullable=False, default=1)
    revision = db.Column(db.BigInteger, nullable=False, default=1)
    status = db.Column(db.String(16), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    lease_token = db.Column(db.String(36))
    lease_until = db.Column(db.DateTime)
    last_error = db.Column(db.String(40))
    synced_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
