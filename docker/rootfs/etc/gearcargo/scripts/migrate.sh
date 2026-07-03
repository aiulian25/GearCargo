#!/command/with-contenv bash
# Oneshot (gated on the postgres service having started): wait until the database
# genuinely accepts queries and is out of crash recovery, then apply migrations.
# gunicorn and cron depend on this oneshot, so the schema is guaranteed present
# before the app or backups run. Works for both embedded and external databases.
set -u
. /etc/gearcargo/env.sh
cd /app

echo "[migrate] Waiting for database to accept queries ($GC_DB_HOST:$GC_DB_PORT)..."
ready=0
for i in $(seq 1 60); do
    if python3 - <<'PY'
import os, sys
try:
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.execute("SELECT pg_is_in_recovery()")
    in_recovery = cur.fetchone()[0]
    cur.close(); conn.close()
    sys.exit(1 if in_recovery else 0)
except Exception:
    sys.exit(1)
PY
    then
        echo "[migrate] Database ready (accepting queries, not in recovery)."
        ready=1
        break
    fi
    echo "[migrate]   waiting for database... ($i/60)"
    sleep 2
done

if [ "$ready" != "1" ]; then
    echo "[migrate] ERROR: database never became ready after 120s." >&2
    exit 1
fi

echo "[migrate] Running flask db upgrade ..."
# Migrations only write to the database (network), never the container FS — so
# this is compatible with a read-only rootfs. Run as the unprivileged app user.
s6-setuidgid gearcargo env PATH="$PATH" DATABASE_URL="$DATABASE_URL" flask db upgrade

# Opt-in belt-and-suspenders schema self-heal, mirrored from the 4-container
# entrypoint. Default OFF (a healthy migrated DB needs nothing here). Set
# DB_SCHEMA_SYNC=true only for one-off recovery after a missed migration.
if [ "${DB_SCHEMA_SYNC:-false}" = "true" ]; then
    echo "[migrate] DB_SCHEMA_SYNC=true — verifying model tables/columns exist ..."
    s6-setuidgid gearcargo env PATH="$PATH" DATABASE_URL="$DATABASE_URL" python3 - <<'PY'
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
        existing_cols = {c['name'] for c in inspector.get_columns(table.name)}
        missing = {c.name for c in table.columns} - existing_cols
        for col_name in missing:
            col = table.columns[col_name]
            col_type = col.type.compile(db.engine.dialect)
            nullable = 'NULL' if col.nullable else 'NOT NULL'
            sql = f'ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {col_name} {col_type} {nullable}'
            try:
                db.session.execute(text(sql)); db.session.commit()
                print(f'  + {table.name}.{col_name}')
            except Exception as e:
                db.session.rollback(); print(f'  ! {table.name}.{col_name} failed: {e}')
    print('[migrate] Schema verification complete.')
PY
fi

echo "[migrate] Database setup complete."
