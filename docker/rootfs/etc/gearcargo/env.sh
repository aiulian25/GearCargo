#!/command/with-contenv bash
# GearCargo single-image — shared environment for all s6 services.
#
# Sourced (never executed) by every service run/up script. It:
#   1. Puts the s6 tools (/command) and the embedded PostgreSQL 16 binaries on PATH.
#   2. Derives EMBEDDED_DB / EMBEDDED_REDIS (dual-mode): embedded datastores are
#      used only when DATABASE_URL / REDIS_URL point at loopback (or are unset).
#      An explicit EMBEDDED_DB / EMBEDDED_REDIS env value always wins.
#   3. Parses user/password/db/port out of DATABASE_URL / REDIS_URL so the
#      embedded servers are initialised with exactly the credentials the app uses.
#
# Nothing here starts a process — it only exports variables.

export PATH="/command:/usr/lib/postgresql/16/bin:${PATH}"

# Defaults mirror backend/app/config.py so an unset URL still means "embedded".
: "${DATABASE_URL:=postgresql://gearcargo:password@127.0.0.1:5432/gearcargo}"
: "${REDIS_URL:=redis://127.0.0.1:6379/0}"

_gc_host_is_local() {
    case "$1" in
        127.0.0.1|localhost|::1|"") return 0 ;;
        *) return 1 ;;
    esac
}

# Robust URL parsing via python (present in the image) — avoids fragile sed.
# Emits shell-quoted assignments; eval is safe because values are shlex.quote'd.
eval "$(python3 - "$DATABASE_URL" "$REDIS_URL" <<'PY'
import sys, shlex
from urllib.parse import urlparse

db = urlparse(sys.argv[1])
rd = urlparse(sys.argv[2])

def q(v):
    return shlex.quote("" if v is None else str(v))

print("GC_DB_HOST=" + q(db.hostname or "127.0.0.1"))
print("GC_DB_PORT=" + q(db.port or 5432))
print("GC_DB_USER=" + q(db.username or "gearcargo"))
print("GC_DB_PASS=" + q(db.password or ""))
print("GC_DB_NAME=" + q((db.path or "/gearcargo").lstrip("/") or "gearcargo"))

print("GC_REDIS_HOST=" + q(rd.hostname or "127.0.0.1"))
print("GC_REDIS_PORT=" + q(rd.port or 6379))
print("GC_REDIS_PASS=" + q(rd.password or ""))
PY
)"

# EMBEDDED_DB: explicit env wins; otherwise auto from the DATABASE_URL host.
if [ -z "${EMBEDDED_DB:-}" ]; then
    if _gc_host_is_local "$GC_DB_HOST"; then EMBEDDED_DB=true; else EMBEDDED_DB=false; fi
fi
if [ -z "${EMBEDDED_REDIS:-}" ]; then
    if _gc_host_is_local "$GC_REDIS_HOST"; then EMBEDDED_REDIS=true; else EMBEDDED_REDIS=false; fi
fi
export EMBEDDED_DB EMBEDDED_REDIS
export GC_DB_HOST GC_DB_PORT GC_DB_USER GC_DB_PASS GC_DB_NAME
export GC_REDIS_HOST GC_REDIS_PORT GC_REDIS_PASS

# Embedded PostgreSQL data directory (kept separate from the 4-container
# ./volumes/db so an existing install's data dir is never touched — see the
# migration plan §8.4 rollback).
export PGDATA="${PGDATA:-/var/lib/postgresql/data}"
