"""GC-008: atomic mutation receipts, record revisions and recurrence origins."""
from alembic import op
import sqlalchemy as sa

revision = 'gc008_mutation_identity'
down_revision = 'gc003_deletion_outbox'
branch_labels = None
depends_on = None

VERSIONED = ('entries', 'vehicles', 'insurance_policies', 'todos', 'reminders', 'attachments')


def upgrade():
    for table in VERSIONED:
        op.add_column(table, sa.Column('revision', sa.BigInteger(), server_default='1', nullable=False))
    # Historical successors have no reliable source link. Preserve them all;
    # uniqueness applies only to new, explicitly linked successors.
    for table in ('reminders', 'todos'):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('completed_from_id', sa.Integer(), nullable=True))
            batch.create_foreign_key(f'fk_{table}_completed_from', table, ['completed_from_id'], ['id'], ondelete='SET NULL')
            batch.create_unique_constraint(f'uq_{table}_completed_from', ['completed_from_id'])
    op.create_table('mutation_operations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('operation_key', sa.String(128), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('status', sa.Integer()), sa.Column('body', sa.Text()),
        sa.Column('headers', sa.JSON()), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'operation_key', name='uq_mutation_owner_key'))
    op.create_index('ix_mutation_operations_user_id', 'mutation_operations', ['user_id'])


def downgrade():
    # Dropping receipts while a browser can retry would re-enable duplicate
    # writes. A separate, explicit retention/rollback decision is required.
    if op.get_bind().execute(sa.text('SELECT count(*) FROM mutation_operations')).scalar_one():
        raise RuntimeError('Disable offline replay and preserve mutation receipts before downgrading GC-008.')
    op.drop_table('mutation_operations')
    for table in ('reminders', 'todos'):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'uq_{table}_completed_from', type_='unique')
            batch.drop_constraint(f'fk_{table}_completed_from', type_='foreignkey')
            batch.drop_column('completed_from_id')
    for table in VERSIONED:
        op.drop_column(table, 'revision')
