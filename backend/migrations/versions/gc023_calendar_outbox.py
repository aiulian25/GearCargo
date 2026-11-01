"""Durable calendar desired state and deletion tombstones."""
from alembic import op
import sqlalchemy as sa

revision = 'gc023_calendar_outbox'
down_revision = 'gc021_reminder_occurrences'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('calendar_outbox',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False), sa.Column('source_key', sa.String(64), nullable=False),
        sa.Column('entry_type', sa.String(20), nullable=False), sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer()), sa.Column('uid', sa.String(255), nullable=False),
        sa.Column('operation', sa.String(10), nullable=False), sa.Column('payload', sa.JSON()),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False), sa.Column('revision', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(), nullable=False), sa.Column('lease_token', sa.String(36)),
        sa.Column('lease_until', sa.DateTime()), sa.Column('last_error', sa.String(40)), sa.Column('synced_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'source_key', 'entry_type', 'entry_id', name='uq_calendar_outbox_target'))
    op.create_index('ix_calendar_outbox_user_id', 'calendar_outbox', ['user_id'])
    op.create_index('ix_calendar_outbox_due', 'calendar_outbox', ['status', 'next_attempt_at'])


def downgrade():
    op.drop_table('calendar_outbox')
