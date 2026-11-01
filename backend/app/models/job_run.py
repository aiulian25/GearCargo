"""Installation-owned schedule cursors and transactional scheduled deliveries."""
from app import db


class JobRun(db.Model):
    __tablename__ = 'scheduled_job_runs'
    job_name = db.Column(db.String(80), primary_key=True)
    next_due_at = db.Column(db.DateTime, index=True)
    occurrence_at = db.Column(db.DateTime)
    status = db.Column(db.String(16), nullable=False, default='idle')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    owner_token = db.Column(db.String(36))
    fence = db.Column(db.BigInteger, nullable=False, default=0)
    lease_until = db.Column(db.DateTime)
    next_attempt_at = db.Column(db.DateTime)
    last_started_at = db.Column(db.DateTime)
    last_finished_at = db.Column(db.DateTime)
    last_success_at = db.Column(db.DateTime)
    last_error = db.Column(db.String(80))
    last_error_at = db.Column(db.DateTime)


class ScheduledEffect(db.Model):
    __tablename__ = 'scheduled_effects'
    __table_args__ = (
        db.UniqueConstraint('job_name', 'occurrence_at', 'effect_key', name='uq_scheduled_effect_occurrence'),
        db.Index('ix_scheduled_effect_due', 'status', 'next_attempt_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    job_name = db.Column(db.String(80), nullable=False)
    occurrence_at = db.Column(db.DateTime, nullable=False)
    effect_key = db.Column(db.String(64), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    # Addresses, message bodies and unsubscribe capabilities are encrypted.
    payload = db.Column(db.Text)
    status = db.Column(db.String(16), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=False)
    lease_until = db.Column(db.DateTime)
    last_error = db.Column(db.String(40))
    created_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime)
