#!/command/with-contenv bash
# Oneshot: initialise the embedded PostgreSQL 16 cluster on first boot.
#
# Skipped entirely when an external DATABASE_URL is configured (EMBEDDED_DB=false).
# On an already-initialised data dir it is a no-op, so it is safe to run every boot.
#
# The cluster is created with the SAME superuser/password/database the app uses
# (parsed from DATABASE_URL in env.sh), listening on loopback only, with password
# auth required over TCP. A fresh cluster is created empty; the app schema is
# applied by the separate `migrate` service (flask db upgrade), and — for a
# migrating install — data is loaded from a portable backup afterwards.
set -eu
. /etc/gearcargo/env.sh

if [ "$EMBEDDED_DB" != "true" ]; then
    echo "[postgres-setup] External database configured ($GC_DB_HOST) — skipping embedded initdb."
    exit 0
fi

if [ -s "$PGDATA/PG_VERSION" ]; then
    echo "[postgres-setup] Existing cluster found (PG_VERSION=$(cat "$PGDATA/PG_VERSION")) — no initdb."
    exit 0
fi

echo "[postgres-setup] Initialising new PostgreSQL 16 cluster at $PGDATA ..."

# initdb refuses a non-empty dir; a bind-mount can contain a stray lost+found.
chown postgres:postgres "$PGDATA"
chmod 700 "$PGDATA"

pwfile="$(mktemp)"
chmod 600 "$pwfile"
printf '%s' "$GC_DB_PASS" > "$pwfile"
chown postgres:postgres "$pwfile"

# --username sets the bootstrap superuser to the app's DB user (e.g. gearcargo);
# --pwfile gives it the app's password. Collation C matches the 4-container
# cluster (POSTGRES_INITDB_ARGS --lc-collate=C --lc-ctype=C) so restored dumps
# and index/collation behaviour line up.
s6-setuidgid postgres initdb \
    --pgdata="$PGDATA" \
    --username="$GC_DB_USER" \
    --pwfile="$pwfile" \
    --auth-local=trust \
    --auth-host=scram-sha-256 \
    --encoding=UTF8 --lc-collate=C --lc-ctype=C
rm -f "$pwfile"

# Loopback-only, sane defaults (tunable via env at build/run time).
cat >> "$PGDATA/postgresql.conf" <<CONF

# --- GearCargo single-image overrides ---
listen_addresses = '127.0.0.1'
port = ${GC_DB_PORT}
unix_socket_directories = '/tmp'
shared_buffers = '${PG_SHARED_BUFFERS:-128MB}'
max_connections = ${PG_MAX_CONNECTIONS:-100}
CONF

# Socket (local) is trust; loopback TCP requires the password.
cat > "$PGDATA/pg_hba.conf" <<HBA
# GearCargo single-image — loopback-only access
local   all   all                 trust
host    all   all   127.0.0.1/32  scram-sha-256
host    all   all   ::1/128       scram-sha-256
HBA
chown postgres:postgres "$PGDATA/postgresql.conf" "$PGDATA/pg_hba.conf"

# Start briefly on the unix socket only to create the application database
# (initdb created the role + a same-named db, but not GC_DB_NAME unless it
# equals the role name — create it idempotently).
echo "[postgres-setup] Creating database '$GC_DB_NAME' ..."
# Local admin connects over the /tmp socket only (no TCP during bootstrap).
export PGHOST=/tmp
s6-setuidgid postgres pg_ctl -D "$PGDATA" -w \
    -o "-c listen_addresses='' -c unix_socket_directories='/tmp' -c port=${GC_DB_PORT}" start
# Connect as the bootstrap superuser (GC_DB_USER) over the local trust socket;
# the default 'postgres' database always exists and is owned by that superuser.
if ! s6-setuidgid postgres psql -U "$GC_DB_USER" -d postgres -v ON_ERROR_STOP=1 -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${GC_DB_NAME}'" | grep -q 1; then
    s6-setuidgid postgres createdb -U "$GC_DB_USER" -O "$GC_DB_USER" "$GC_DB_NAME"
fi
s6-setuidgid postgres pg_ctl -D "$PGDATA" -m fast -w stop

echo "[postgres-setup] Cluster initialised."
