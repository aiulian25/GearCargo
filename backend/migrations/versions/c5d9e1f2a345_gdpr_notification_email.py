"""GDPR notification email - encrypted field, consent ledger, verification, unsubscribe

Revision ID: c5d9e1f2a345
Revises: b4c8d9e0f123
Create Date: 2026-04-19 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c5d9e1f2a345'
down_revision = 'b4c8d9e0f123'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
    ), {'t': table_name})
    return result.scalar()


def _column_exists(table_name, column_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c)"
    ), {'t': table_name, 'c': column_name})
    return result.scalar()


def _index_exists(index_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :i)"
    ), {'i': index_name})
    return result.scalar()


def upgrade():
    # --- EmailConsentLog table (immutable ledger) ---
    if not _table_exists('email_consent_logs'):
        op.create_table(
            'email_consent_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
            sa.Column('action', sa.String(30), nullable=False, index=True),
            sa.Column('email_hash', sa.String(64), nullable=False),
            sa.Column('consent_text_version', sa.String(20), server_default='1.0'),
            sa.Column('ip_address', sa.String(45)),
            sa.Column('user_agent', sa.String(500)),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        )

    # --- New columns on users table ---
    op.alter_column('users', 'notification_email',
                    existing_type=sa.String(120),
                    type_=sa.Text(),
                    existing_nullable=True)

    new_columns = {
        'notification_email_hash': sa.Column('notification_email_hash', sa.String(64)),
        'notification_email_verified': sa.Column('notification_email_verified', sa.Boolean(), server_default=sa.false()),
        'notification_email_token': sa.Column('notification_email_token', sa.String(255)),
        'notification_email_token_exp': sa.Column('notification_email_token_exp', sa.DateTime()),
        'notification_email_consented_at': sa.Column('notification_email_consented_at', sa.DateTime()),
        'notification_email_consent_ip': sa.Column('notification_email_consent_ip', sa.String(45)),
        'notification_email_bounce_count': sa.Column('notification_email_bounce_count', sa.Integer(), server_default='0'),
        'unsubscribe_token': sa.Column('unsubscribe_token', sa.String(64)),
    }

    for col_name, col in new_columns.items():
        if not _column_exists('users', col_name):
            op.add_column('users', col)

    if not _index_exists('ix_users_notification_email_hash'):
        op.create_index('ix_users_notification_email_hash', 'users', ['notification_email_hash'])
    if not _index_exists('ix_users_unsubscribe_token'):
        op.create_index('ix_users_unsubscribe_token', 'users', ['unsubscribe_token'], unique=True)

    # Clear existing plaintext notification_email values
    op.execute("UPDATE users SET notification_email = NULL WHERE notification_email IS NOT NULL")


def downgrade():
    op.drop_index('ix_users_unsubscribe_token', table_name='users')
    op.drop_index('ix_users_notification_email_hash', table_name='users')
    op.drop_column('users', 'unsubscribe_token')
    op.drop_column('users', 'notification_email_bounce_count')
    op.drop_column('users', 'notification_email_consent_ip')
    op.drop_column('users', 'notification_email_consented_at')
    op.drop_column('users', 'notification_email_token_exp')
    op.drop_column('users', 'notification_email_token')
    op.drop_column('users', 'notification_email_verified')
    op.drop_column('users', 'notification_email_hash')

    op.alter_column('users', 'notification_email',
                    existing_type=sa.Text(),
                    type_=sa.String(120),
                    existing_nullable=True)

    op.drop_table('email_consent_logs')
