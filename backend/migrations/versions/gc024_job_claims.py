"""Durable scheduler cursors, ownership and scheduled transport intents."""
from alembic import op
import sqlalchemy as sa

revision = 'gc024_job_claims'
down_revision = 'gc023_calendar_outbox'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('scheduled_job_runs',
        sa.Column('job_name', sa.String(80), primary_key=True),
        sa.Column('next_due_at', sa.DateTime()), sa.Column('occurrence_at', sa.DateTime()),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('owner_token', sa.String(36)), sa.Column('fence', sa.BigInteger(), nullable=False),
        sa.Column('lease_until', sa.DateTime()), sa.Column('next_attempt_at', sa.DateTime()),
        sa.Column('last_started_at', sa.DateTime()), sa.Column('last_finished_at', sa.DateTime()),
        sa.Column('last_success_at', sa.DateTime()), sa.Column('last_error', sa.String(80)),
        sa.Column('last_error_at', sa.DateTime()))
    op.create_index('ix_scheduled_job_runs_next_due_at', 'scheduled_job_runs', ['next_due_at'])
    op.create_table('scheduled_effects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('job_name', sa.String(80), nullable=False),
        sa.Column('occurrence_at', sa.DateTime(), nullable=False),
        sa.Column('effect_key', sa.String(64), nullable=False), sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('payload', sa.Text()), sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False), sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
        sa.Column('lease_until', sa.DateTime()), sa.Column('last_error', sa.String(40)),
        sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('completed_at', sa.DateTime()),
        sa.UniqueConstraint('job_name', 'occurrence_at', 'effect_key', name='uq_scheduled_effect_occurrence'))
    op.create_index('ix_scheduled_effects_user_id', 'scheduled_effects', ['user_id'])
    op.create_index('ix_scheduled_effect_due', 'scheduled_effects', ['status', 'next_attempt_at'])


def downgrade():
    op.drop_table('scheduled_effects')
    op.drop_table('scheduled_job_runs')
