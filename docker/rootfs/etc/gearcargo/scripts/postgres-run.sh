#!/command/with-contenv bash
# Longrun: the embedded PostgreSQL server.
#
# When an external DATABASE_URL is set (EMBEDDED_DB=false) this service parks on
# `sleep infinity` so the supervision tree stays simple and the app talks to the
# remote database instead.
#
# Clean shutdown matters: the s6 service dir sets down-signal=SIGINT so Postgres
# does a FAST shutdown on `docker stop`. A default SIGTERM triggers a SMART
# shutdown that waits for clients and can be SIGKILLed mid-flush, forcing WAL
# recovery on the next boot — the exact post-restart outage fixed earlier.
set -u
. /etc/gearcargo/env.sh

if [ "$EMBEDDED_DB" != "true" ]; then
    echo "[postgres] External database ($GC_DB_HOST:$GC_DB_PORT) — embedded PostgreSQL disabled."
    exec sleep infinity
fi

echo "[postgres] Starting embedded PostgreSQL 16 on 127.0.0.1:${GC_DB_PORT}"
exec s6-setuidgid postgres postgres -D "$PGDATA"
