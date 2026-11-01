"""Selected statement data and explicit allocations, never ledger expenses."""
from app import db
from app.utils.revisions import next_revision
from app.utils.timeutils import utc_naive_now


class StatementBatch(db.Model):
    __tablename__ = 'statement_batches'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    revision = db.Column(db.BigInteger, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': revision, 'version_id_generator': next_revision}
    name = db.Column(db.String(100), nullable=False)
    source_key = db.Column(db.String(64), nullable=False)
    selection_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(12), nullable=False, default='open')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now, onupdate=utc_naive_now)
    transactions = db.relationship('StatementTransaction', cascade='all, delete-orphan', lazy='selectin', order_by='StatementTransaction.row_number')
    __table_args__ = (db.UniqueConstraint('user_id', 'source_key', name='uq_statement_source'),
        db.CheckConstraint("status IN ('open','reconciled')", name='ck_statement_status'))

    def to_dict(self):
        # Mutation receipts contain identifiers only, never source transactions.
        return dict(id=self.id, revision=self.revision, status=self.status)


class StatementTransaction(db.Model):
    __tablename__ = 'statement_transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('statement_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    vendor = db.Column(db.String(120), nullable=False, default='')
    exclusion_reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    matches = db.relationship('StatementMatch', cascade='all, delete-orphan', lazy='selectin', order_by='StatementMatch.id')
    __table_args__ = (db.UniqueConstraint('batch_id', 'row_number', name='uq_statement_row'),
        db.UniqueConstraint('user_id', 'fingerprint', name='uq_statement_fingerprint'),
        db.CheckConstraint('amount != 0', name='ck_statement_amount'),
        db.CheckConstraint('row_number > 0', name='ck_statement_row_number'))


class StatementMatch(db.Model):
    __tablename__ = 'statement_matches'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('statement_transactions.id', ondelete='CASCADE'), nullable=False, index=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entries.id', ondelete='SET NULL'), index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    entry_signature = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    entry = db.relationship('Entry')
    __table_args__ = (db.UniqueConstraint('transaction_id', 'entry_id', name='uq_statement_match'),
        db.CheckConstraint('amount != 0', name='ck_statement_match_amount'))
