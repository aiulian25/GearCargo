"""GC-016: durable, owner-scoped import provenance without guessing legacy links."""
import uuid
from alembic import op
import sqlalchemy as sa

revision = 'gc016_import_provenance'
down_revision = 'gc008_mutation_identity'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('export_namespace', sa.String(36)))
    connection = op.get_bind()
    for user_id in connection.execute(sa.text('SELECT id FROM users')).scalars():
        connection.execute(sa.text('UPDATE users SET export_namespace=:namespace WHERE id=:id'),
                           {'namespace': str(uuid.uuid4()), 'id': user_id})
    with op.batch_alter_table('users') as batch:
        batch.alter_column('export_namespace', existing_type=sa.String(36), nullable=False)
        batch.create_unique_constraint('uq_user_export_namespace', ['export_namespace'])
    op.create_table('import_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('batch_key', sa.String(64), nullable=False),
        sa.Column('source_format', sa.String(30), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'batch_key', name='uq_import_batch_owner_key'))
    op.create_index('ix_import_batches_user_id', 'import_batches', ['user_id'])
    op.create_table('import_identities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('namespace', sa.String(160), nullable=False),
        sa.Column('entity_kind', sa.String(40), nullable=False),
        sa.Column('source_id', sa.String(160), nullable=False),
        sa.Column('target_id', sa.BigInteger(), nullable=False),
        sa.Column('target_created_at', sa.String(40)),
        sa.Column('source_hash', sa.String(64), nullable=False),
        sa.Column('source_payload', sa.JSON(), nullable=False),
        sa.Column('original_payload', sa.JSON(), nullable=False),
        sa.Column('first_batch_id', sa.Integer(), sa.ForeignKey('import_batches.id'), nullable=False),
        sa.Column('last_batch_id', sa.Integer(), sa.ForeignKey('import_batches.id'), nullable=False),
        sa.UniqueConstraint('user_id', 'namespace', 'entity_kind', 'source_id', name='uq_import_owner_source'))
    op.create_index('ix_import_identities_user_id', 'import_identities', ['user_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM import_identities')).scalar_one():
        raise RuntimeError('Preserve import provenance and stop import clients before downgrading GC-016.')
    op.drop_table('import_identities')
    op.drop_table('import_batches')
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('uq_user_export_namespace', type_='unique')
        batch.drop_column('export_namespace')
