#!/bin/bash
set -e

echo "Starting GearCargo..."

# Fix volume permissions (entrypoint runs as root, volumes may be owned by host root)
if [ "$(id -u)" = "0" ]; then
    echo "Fixing volume permissions..."
    chown -R gearcargo:gearcargo /app/volumes /app/uploads 2>/dev/null || true
fi

# Wait for the database to genuinely accept QUERIES and be out of crash
# recovery — not just accept a TCP connection. After an unclean stop Postgres
# replays WAL on next boot; it may accept connect() while still recovering, so
# we run `SELECT 1` and require `pg_is_in_recovery()` to be false (true only on
# a standby/during recovery — this app runs a single primary). This prevents the
# app from opening connections against a not-yet-ready DB (see
# STARTUP_SLOWNESS_INVESTIGATION.md §4.4).
echo "Waiting for database to accept queries..."
for i in $(seq 1 30); do
    if python -c "
import psycopg2, os, sys
try:
    conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://gearcargo:password@db:5432/gearcargo'))
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.execute('SELECT pg_is_in_recovery()')
    in_recovery = cur.fetchone()[0]
    cur.close(); conn.close()
    sys.exit(1 if in_recovery else 0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "Database is ready (accepting queries, not in recovery)."
        break
    fi
    echo "  Waiting for database... ($i/30)"
    sleep 2
done

# Run database migrations
echo "Running database migrations..."
# NOTE (read_only: true): 'flask db upgrade' only writes to the database (network),
# not to the container filesystem — fully compatible with read_only: true.
# The fallback below ('flask db migrate') would write new migration scripts to
# migrations/versions/ which IS inside the read-only container filesystem and
# will therefore fail with "Read-only file system" in locked-down deployments.
# That fallback is a last-resort recovery path and should never trigger in a
# properly initialized deployment.
flask db upgrade 2>&1 || {
    echo "Migration failed, attempting to initialize database..."
    flask db init 2>/dev/null || true
    flask db migrate -m "Initial migration" 2>/dev/null || true
    flask db upgrade 2>&1 || echo "WARNING: Migration failed - tables may need manual setup"
}

# Schema is owned by Alembic migrations (the `flask db upgrade` above). The
# create_all() + per-column "ADD COLUMN IF NOT EXISTS" introspection below is a
# belt-and-suspenders self-heal for a DRIFTED schema. Running it on every boot
# spins up a second full create_app() and lengthens startup
# (STARTUP_SLOWNESS_INVESTIGATION.md §4.4), so it is now opt-in: set
# DB_SCHEMA_SYNC=true to run it (e.g. one-off recovery after a missed migration).
# Default off — a healthy, migrated database needs nothing here.
if [ "${DB_SCHEMA_SYNC:-false}" = "true" ]; then
echo "DB_SCHEMA_SYNC=true — verifying all model tables and columns exist..."
python << 'PYEOF'
from app import create_app, db
from sqlalchemy import inspect, text

app = create_app()
with app.app_context():
    db.create_all()

    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    for table in db.metadata.tables.values():
        if table.name not in existing_tables:
            continue

        existing_cols = {col['name'] for col in inspector.get_columns(table.name)}
        model_cols = {col.name for col in table.columns}
        missing_cols = model_cols - existing_cols

        if missing_cols:
            print(f'  Adding missing columns to {table.name}: {missing_cols}')
            for col_name in missing_cols:
                col = table.columns[col_name]
                col_type = col.type.compile(db.engine.dialect)
                nullable = 'NULL' if col.nullable else 'NOT NULL'
                default = ''
                if col.default is not None:
                    dv = col.default.arg
                    if callable(dv):
                        default = ''
                    elif isinstance(dv, bool):
                        default = ' DEFAULT true' if dv else ' DEFAULT false'
                    elif isinstance(dv, (int, float)):
                        default = f' DEFAULT {dv}'
                    elif isinstance(dv, str):
                        safe = dv.replace("'", "''")
                        default = f" DEFAULT '{safe}'"
                    else:
                        default = ''
                sql = f'ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {col_name} {col_type} {nullable}{default}'
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f'    + {col_name} ({col_type})')
                except Exception as e:
                    db.session.rollback()
                    print(f'    ! {col_name} failed: {e}')

    print('All tables and columns verified.')
PYEOF
else
    echo "Skipping model-introspection schema sync (set DB_SCHEMA_SYNC=true to enable); relying on migrations."
fi

echo "Database setup complete."

# Start Gunicorn (drop to non-root user if running as root)
if [ "$(id -u)" = "0" ]; then
    exec gosu gearcargo gunicorn --config gunicorn.conf.py "app:create_app()"
else
    exec gunicorn --config gunicorn.conf.py "app:create_app()"
fi
