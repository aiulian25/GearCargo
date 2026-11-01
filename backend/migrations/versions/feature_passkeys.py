"""Passkeys: WebAuthn credentials for signing in without a password."""
from alembic import op
import sqlalchemy as sa

revision = 'feature_passkeys'
down_revision = 'feature_reconciliation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('passkeys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('relying_party_id', sa.String(253), nullable=False),
        sa.Column('credential_id', sa.String(512), nullable=False),
        sa.Column('public_key', sa.String(1024), nullable=False),
        sa.Column('sign_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('transports', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('backed_up', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('last_used_at', sa.DateTime()),
        sa.UniqueConstraint('credential_id', name='uq_passkey_credential_id'))
    op.create_index('ix_passkeys_user_id', 'passkeys', ['user_id'])


def downgrade():
    op.drop_index('ix_passkeys_user_id', table_name='passkeys')
    op.drop_table('passkeys')
