"""Add renewed_from_id to insurance_policies (F6 — honor auto_renew)

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-07-08 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'q5r6s7t8u9v0'
down_revision = 'p4q5r6s7t8u9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('insurance_policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('renewed_from_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_insurance_policies_renewed_from_id', ['renewed_from_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_insurance_policies_renewed_from_id', 'insurance_policies',
            ['renewed_from_id'], ['id'],
        )


def downgrade():
    with op.batch_alter_table('insurance_policies', schema=None) as batch_op:
        batch_op.drop_constraint('fk_insurance_policies_renewed_from_id', type_='foreignkey')
        batch_op.drop_index('ix_insurance_policies_renewed_from_id')
        batch_op.drop_column('renewed_from_id')
