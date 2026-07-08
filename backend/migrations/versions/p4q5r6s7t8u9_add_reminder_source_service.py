"""Add source_service_id to reminders (F5 — auto-generate next service)

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-07-08 00:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p4q5r6s7t8u9'
down_revision = 'o3p4q5r6s7t8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_service_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_reminders_source_service_id', ['source_service_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_reminders_source_service_id', 'service_entries',
            ['source_service_id'], ['id'],
        )


def downgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reminders_source_service_id', type_='foreignkey')
        batch_op.drop_index('ix_reminders_source_service_id')
        batch_op.drop_column('source_service_id')
