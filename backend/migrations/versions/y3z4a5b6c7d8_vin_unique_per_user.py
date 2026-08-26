"""R1 — VIN is unique PER USER, not instance-wide.

The initial schema declared ``sa.UniqueConstraint('vin')``, so a VIN could
exist only once across the whole instance. That blocked legitimate cases (a car
sold between two users of the same server, spouse accounts recording the same
vehicle) and let any user probe whether a VIN existed in someone else's garage.

Replaced with a composite UNIQUE on (user_id, vin). NULLs compare distinct in
Postgres, so any number of vehicles without a VIN remain legal per user.

Relaxation only: every row that satisfied the old global constraint also
satisfies the new one, so no data cleanup is required on upgrade.

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'y3z4a5b6c7d8'
down_revision = 'x2y3z4a5b6c7'
branch_labels = None
depends_on = None

NEW_CONSTRAINT = 'uq_vehicle_user_vin'


def _vin_only_unique_constraints(conn):
    """Names of existing UNIQUE constraints covering exactly (vin).

    Reflected rather than hard-coded: the auto-generated name is
    'vehicles_vin_key' on Postgres, but a database created by create_all() or
    an older tool may differ.
    """
    inspector = sa.inspect(conn)
    return [
        uc['name']
        for uc in inspector.get_unique_constraints('vehicles')
        if list(uc.get('column_names') or []) == ['vin'] and uc.get('name')
    ]


def upgrade():
    conn = op.get_bind()

    for name in _vin_only_unique_constraints(conn):
        op.drop_constraint(name, 'vehicles', type_='unique')

    # Some deployments carry the uniqueness as a unique INDEX instead.
    inspector = sa.inspect(conn)
    for ix in inspector.get_indexes('vehicles'):
        if ix.get('unique') and list(ix.get('column_names') or []) == ['vin']:
            op.drop_index(ix['name'], table_name='vehicles')

    op.create_unique_constraint(NEW_CONSTRAINT, 'vehicles', ['user_id', 'vin'])


def downgrade():
    """Restore instance-wide uniqueness.

    NOTE: this fails if two users have since recorded the same VIN — exactly the
    case the upgrade was made to allow. De-duplicate before downgrading.
    """
    op.drop_constraint(NEW_CONSTRAINT, 'vehicles', type_='unique')
    op.create_unique_constraint('vehicles_vin_key', 'vehicles', ['vin'])
