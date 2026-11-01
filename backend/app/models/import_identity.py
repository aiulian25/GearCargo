"""GC-016: owner-scoped source identities; never business-field deduplication."""
from app import db
from app.utils.timeutils import utc_naive_now


class ImportBatch(db.Model):
    __tablename__ = 'import_batches'
    __table_args__ = (db.UniqueConstraint('user_id', 'batch_key', name='uq_import_batch_owner_key'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    batch_key = db.Column(db.String(64), nullable=False)
    source_format = db.Column(db.String(30), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)


class ImportIdentity(db.Model):
    __tablename__ = 'import_identities'
    __table_args__ = (db.UniqueConstraint('user_id', 'namespace', 'entity_kind', 'source_id', name='uq_import_owner_source'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    namespace = db.Column(db.String(160), nullable=False)
    entity_kind = db.Column(db.String(40), nullable=False)
    source_id = db.Column(db.String(160), nullable=False)
    # No cascading business FK: retaining a missing target prevents an import
    # retry from resurrecting a deliberately deleted record. The creation stamp
    # also prevents an old integer ID being mistaken for a replacement record.
    target_id = db.Column(db.BigInteger, nullable=False)
    target_created_at = db.Column(db.String(40))
    source_hash = db.Column(db.String(64), nullable=False)
    source_payload = db.Column(db.JSON, nullable=False)
    original_payload = db.Column(db.JSON, nullable=False)
    first_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id'), nullable=False)
    last_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id'), nullable=False)
