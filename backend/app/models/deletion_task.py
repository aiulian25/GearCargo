"""Committed cleanup work that must outlive the deleted account/vehicle."""
import uuid

from app import db
from app.utils.timeutils import utc_naive_now


class DeletionTask(db.Model):
    __tablename__ = 'deletion_tasks'

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    operation_id = db.Column(db.String(32), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(80))
