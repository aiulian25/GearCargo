"""Committed API outcomes, scoped to the authenticated owner."""
from app import db
from app.utils.timeutils import utc_naive_now


class MutationOperation(db.Model):
    __tablename__ = 'mutation_operations'
    __table_args__ = (db.UniqueConstraint('user_id', 'operation_key', name='uq_mutation_owner_key'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    operation_key = db.Column(db.String(128), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    status = db.Column(db.Integer)
    body = db.Column(db.Text)
    headers = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
