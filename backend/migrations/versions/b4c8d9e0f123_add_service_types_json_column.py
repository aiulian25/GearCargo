"""Add service_types JSON column for multi-select

Revision ID: b4c8d9e0f123
Revises: a3b7c8d9e012
Create Date: 2026-04-19 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c8d9e0f123'
down_revision = 'a3b7c8d9e012'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE service_entries ADD COLUMN IF NOT EXISTS service_types JSON"
    ))

    # Backfill existing entries: wrap service_type in a JSON array
    conn.execute(sa.text("""
        UPDATE service_entries
        SET service_types = json_build_array(service_type)
        WHERE service_type IS NOT NULL AND service_types IS NULL
    """))


def downgrade():
    op.drop_column('service_entries', 'service_types')
