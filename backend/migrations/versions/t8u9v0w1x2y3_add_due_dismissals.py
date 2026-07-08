"""Add due_dismissals table (dismiss items from the "Coming up" feed)

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-07-08 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 't8u9v0w1x2y3'
down_revision = 's7t8u9v0w1x2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'due_dismissals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('ref_id', sa.Integer(), nullable=False),
        # The occurrence being dismissed. NULL for kinds without a date
        # (consumable wear, fines). A future occurrence (different date)
        # resurfaces in the feed.
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_due_dismissals_user_id', 'due_dismissals', ['user_id'])
    op.create_index('ix_due_dismissals_lookup', 'due_dismissals',
                    ['user_id', 'kind', 'ref_id'])


def downgrade():
    op.drop_index('ix_due_dismissals_lookup', table_name='due_dismissals')
    op.drop_index('ix_due_dismissals_user_id', table_name='due_dismissals')
    op.drop_table('due_dismissals')
