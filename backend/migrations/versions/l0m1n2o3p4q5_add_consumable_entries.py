"""Add consumable_entries table (tires/battery/consumables tracking)

F03 (IMPROVEMENTS.md §3.2): a first-class consumable expense entry type with
mileage- and time-based wear estimation. Joined-table inheritance on `entries`
(like fuel/service/repair/tax/parking).

Idempotent (CREATE TABLE IF NOT EXISTS) so it is a no-op where db.create_all
already created the table (e.g. tests / fresh installs).

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l0m1n2o3p4q5'
down_revision = 'k9l0m1n2o3p4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS consumable_entries (
            id                       INTEGER PRIMARY KEY REFERENCES entries(id),
            consumable_type          VARCHAR(30),
            brand                    VARCHAR(100),
            quantity                 INTEGER,
            install_date             DATE,
            install_odometer         INTEGER,
            expected_lifespan_km     INTEGER,
            expected_lifespan_months INTEGER,
            warranty_months          INTEGER
        )
        """
    ))


def downgrade():
    op.drop_table('consumable_entries')
