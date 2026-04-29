"""Add repair_types JSON column for multi-select

Revision ID: a3b7c8d9e012
Revises: f9e4b6bc1451
Create Date: 2026-04-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b7c8d9e012'
down_revision = 'f9e4b6bc1451'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE repair_entries ADD COLUMN IF NOT EXISTS repair_types JSON"
    ))

    # Backfill existing entries: wrap repair_type in a JSON array
    conn.execute(sa.text("""
        UPDATE repair_entries
        SET repair_types = json_build_array(repair_type)
        WHERE repair_type IS NOT NULL AND repair_types IS NULL
    """))


def downgrade():
    op.drop_column('repair_entries', 'repair_types')
