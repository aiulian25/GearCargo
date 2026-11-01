"""Selected statement transactions and explicit signed allocations."""
from alembic import op
import sqlalchemy as sa

revision = 'feature_reconciliation'
down_revision = 'feature_appointments'
branch_labels = depends_on = None


def ownership():
    return [sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False)]


def upgrade():
    op.create_table('statement_batches', *ownership(),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('source_key', sa.String(64), nullable=False),
        sa.Column('selection_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id','source_key', name='uq_statement_source'),
        sa.CheckConstraint("status IN ('open','reconciled')", name='ck_statement_status'))
    op.create_table('statement_transactions', *ownership(),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('statement_batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('date', sa.Date(), nullable=False), sa.Column('amount', sa.Numeric(10,2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False), sa.Column('vendor', sa.String(120), nullable=False),
        sa.Column('exclusion_reason', sa.String(255)),
        sa.UniqueConstraint('batch_id','row_number', name='uq_statement_row'),
        sa.UniqueConstraint('user_id','fingerprint', name='uq_statement_fingerprint'),
        sa.CheckConstraint('amount != 0', name='ck_statement_amount'),
        sa.CheckConstraint('row_number > 0', name='ck_statement_row_number'))
    op.create_table('statement_matches', *ownership(),
        sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('statement_transactions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('entries.id', ondelete='SET NULL')),
        sa.Column('amount', sa.Numeric(10,2), nullable=False), sa.Column('entry_signature', sa.String(64), nullable=False),
        sa.UniqueConstraint('transaction_id','entry_id', name='uq_statement_match'),
        sa.CheckConstraint('amount != 0', name='ck_statement_match_amount'))
    for table, columns in {'statement_batches': ('user_id',), 'statement_transactions': ('user_id','batch_id'), 'statement_matches': ('user_id','transaction_id','entry_id')}.items():
        for column in columns: op.create_index(f'ix_{table}_{column}', table, [column])


def downgrade():
    for table in ('statement_matches', 'statement_transactions', 'statement_batches'): op.drop_table(table)
