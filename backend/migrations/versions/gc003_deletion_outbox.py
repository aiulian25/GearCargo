"""GC-003: durable cleanup after relational deletion, with an orphan preflight.

Existing foreign keys retain their restrictive semantics (sessions/shares keep
their existing CASCADE). The deletion service orders explicit deletes; broad
database cascades would silently destroy records belonging to another owner.
"""
from alembic import op
import sqlalchemy as sa

revision = 'gc003_deletion_outbox'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def check_orphans(connection):
    inspector = sa.inspect(connection)
    quote = connection.dialect.identifier_preparer.quote
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            columns = fk['constrained_columns']
            parents = fk['referred_columns']
            present = ' AND '.join(f'c.{quote(c)} IS NOT NULL' for c in columns)
            match = ' AND '.join(f'p.{quote(p)} = c.{quote(c)}'
                                 for c, p in zip(columns, parents))
            count = connection.execute(sa.text(
                f'SELECT count(*) FROM {quote(table)} c WHERE {present} '
                f'AND NOT EXISTS (SELECT 1 FROM {quote(fk["referred_table"])} p WHERE {match})'
            )).scalar_one()
            if count:
                raise RuntimeError(f'GC-003 migration stopped: {count} orphan rows in '
                                   f'{table}.{",".join(columns)}. Repair from a verified backup first.')


def upgrade():
    check_orphans(op.get_bind())
    op.create_table(
        'deletion_tasks',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('operation_id', sa.String(32), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(80)),
    )
    op.create_index('ix_deletion_tasks_operation_id', 'deletion_tasks', ['operation_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM deletion_tasks')).scalar_one():
        raise RuntimeError('Run flask cleanup-deleted-files before downgrading; pending cleanup must not be lost.')
    op.drop_table('deletion_tasks')
