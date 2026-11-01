"""Store an explicit backup encryption policy and correct legacy artifact flags."""
from alembic import op
import sqlalchemy as sa

revision = 'gc028_backup_protection'
down_revision = 'gc027_consumer_readiness'
branch_labels = depends_on = None


def upgrade():
    op.add_column('backup_schedules', sa.Column('encryption_enabled', sa.Boolean(),
                                               nullable=False, server_default=sa.false()))
    op.add_column('backup_schedules', sa.Column('backup_passphrase_encrypted', sa.Text()))
    # Every pre-GC028 writer produced plaintext, despite the old ORM default.
    op.execute(sa.text('UPDATE backups SET encrypted = false'))


def downgrade():
    op.drop_column('backup_schedules', 'backup_passphrase_encrypted')
    op.drop_column('backup_schedules', 'encryption_enabled')
    # Do not reinstate the false legacy promise that all artifacts are encrypted.
