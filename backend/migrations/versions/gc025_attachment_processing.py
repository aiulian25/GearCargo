"""Durable bounded OCR admission and two deployment-wide processing slots."""
from alembic import op
import sqlalchemy as sa

revision = 'gc025_attachment_processing'
down_revision = 'gc024_job_claims'
branch_labels = depends_on = None


def upgrade():
    op.add_column('attachments', sa.Column('ocr_state', sa.String(16)))
    op.add_column('attachments', sa.Column('ocr_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('attachments', sa.Column('ocr_generation', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('attachments', sa.Column('ocr_owner', sa.String(36)))
    op.add_column('attachments', sa.Column('ocr_lease_until', sa.DateTime()))
    op.add_column('attachments', sa.Column('ocr_next_attempt_at', sa.DateTime()))
    op.add_column('attachments', sa.Column('ocr_error', sa.String(40)))
    op.create_index('ix_attachments_ocr_state', 'attachments', ['ocr_state'])
    op.execute("UPDATE attachments SET ocr_state = 'done' WHERE ocr_processed = true")
    table = op.create_table('ocr_slots', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('revision', sa.BigInteger(), nullable=False), sa.Column('owner', sa.String(36)),
        sa.Column('attachment_id', sa.Integer()), sa.Column('lease_until', sa.DateTime()),
        sa.Column('last_seen_at', sa.DateTime()))
    op.bulk_insert(table, [{'id': slot, 'revision': 0} for slot in range(3)])


def downgrade():
    op.drop_table('ocr_slots')
    with op.batch_alter_table('attachments') as batch:
        batch.drop_index('ix_attachments_ocr_state')
        for name in ('ocr_state', 'ocr_attempts', 'ocr_generation', 'ocr_owner', 'ocr_lease_until',
                     'ocr_next_attempt_at', 'ocr_error'):
            batch.drop_column(name)
