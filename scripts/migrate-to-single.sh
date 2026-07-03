#!/usr/bin/env bash
# ============================================================
# GearCargo — migrate 4-container stack → single image (Option A)
# ============================================================
# SAFE + REVERSIBLE (Single-Image.md §8). This script:
#   1. Verifies your ENCRYPTION_KEY is present (PII is unrecoverable without it).
#   2. Takes a portable backup with the app's own tool + a raw tarball.
#   3. Records source row counts.
#   4. Stops the 4-container stack (volumes are NOT deleted).
#   5. Starts the single image with a FRESH embedded PG at ./volumes/pgdata
#      (your old ./volumes/db is never touched → instant rollback).
#   6. Restores the DB dump into the embedded PG.
#   7. Verifies row counts match. On ANY failure it auto-rolls back to the
#      4-container stack.
#
# Attachments/uploads/backups are shared mounts — no copy needed.
#
# Usage:
#   scripts/migrate-to-single.sh [--yes] [--archive PATH_TO_EXISTING_ARCHIVE]
#
#   --yes       non-interactive (assume yes to prompts)
#   --archive   skip taking a new backup; restore from this existing archive
set -euo pipefail

# --- locate repo root (script lives in ./scripts) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

PROD_COMPOSE="docker-compose.prod.yml"
SINGLE_COMPOSE="docker-compose.single.yml"
ENV_FILE=".env"

ASSUME_YES=0
ARCHIVE_OVERRIDE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) ASSUME_YES=1 ;;
        --archive) ARCHIVE_OVERRIDE="${2:?--archive needs a path}"; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

log()  { printf '\033[1;34m[migrate]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[migrate]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[migrate]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[migrate] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

confirm() {
    [ "$ASSUME_YES" = "1" ] && return 0
    printf '%s [y/N] ' "$1"; read -r ans
    case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

dc() { docker compose "$@"; }

# --- preflight ---------------------------------------------------------------
command -v docker >/dev/null || die "docker not found"
[ -f "$PROD_COMPOSE" ]   || die "$PROD_COMPOSE not found — run from the repo."
[ -f "$SINGLE_COMPOSE" ] || die "$SINGLE_COMPOSE not found."
[ -f "$ENV_FILE" ]       || die "$ENV_FILE not found — cannot read secrets."

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${DB_PASSWORD:?DB_PASSWORD missing in .env}"
[ -n "${ENCRYPTION_KEY:-}" ] || die "ENCRYPTION_KEY missing in .env — refusing to migrate (PII would be unrecoverable)."

log "Encryption key present. Old data dir ./volumes/db will be left UNTOUCHED."
log "Embedded PostgreSQL will use ./volumes/pgdata (fresh)."
if [ -e ./volumes/pgdata ] && [ -n "$(ls -A ./volumes/pgdata 2>/dev/null || true)" ]; then
    warn "./volumes/pgdata is not empty."
    confirm "Reuse the existing ./volumes/pgdata contents?" || die "Aborted. Move ./volumes/pgdata aside and retry."
fi

confirm "Proceed with migration to the single image?" || { log "Aborted by user."; exit 0; }

# --- helper: row-count fingerprint ------------------------------------------
COUNT_SQL="SELECT 'users='||count(*) FROM users UNION ALL SELECT 'vehicles='||count(*) FROM vehicles UNION ALL SELECT 'entries='||count(*) FROM entries ORDER BY 1"

counts_prod()  { dc -f "$PROD_COMPOSE" exec -T db psql -U gearcargo -d gearcargo -tAc "$COUNT_SQL" | tr -d '[:space:]' ; }
counts_single(){ dc -f "$SINGLE_COMPOSE" exec -T gearcargo env PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U gearcargo -d gearcargo -tAc "$COUNT_SQL" | tr -d '[:space:]' ; }

# --- 1. backup ---------------------------------------------------------------
ARCHIVE=""
if [ -n "$ARCHIVE_OVERRIDE" ]; then
    [ -f "$ARCHIVE_OVERRIDE" ] || die "Archive not found: $ARCHIVE_OVERRIDE"
    ARCHIVE="$ARCHIVE_OVERRIDE"
    log "Using existing archive: $ARCHIVE"
else
    log "Ensuring the 4-container stack is up to take a fresh backup..."
    dc -f "$PROD_COMPOSE" up -d db backup
    log "Waiting for database..."
    for _ in $(seq 1 30); do
        dc -f "$PROD_COMPOSE" exec -T db pg_isready -U gearcargo -d gearcargo >/dev/null 2>&1 && break
        sleep 2
    done
    log "Taking portable backup (manual)..."
    dc -f "$PROD_COMPOSE" exec -T backup sh /usr/local/bin/backup.sh manual
    ARCHIVE="$(ls -1t ./volumes/backups/system/manual/gearcargo_manual_*.tar.gz 2>/dev/null | head -1 || true)"
    [ -n "$ARCHIVE" ] || die "Could not find the backup archive just created."
    ok "Backup archive: $ARCHIVE"
fi

log "Taking an independent raw safety tarball (belt & suspenders)..."
RAW_TARBALL="gearcargo-preupgrade-$(date +%F_%H%M%S).tar.gz"
tar czf "$RAW_TARBALL" volumes/attachments volumes/uploads volumes/backups secrets "$ENV_FILE" 2>/dev/null || \
    warn "Raw tarball had warnings (continuing) — $RAW_TARBALL"
ok "Raw safety tarball: $RAW_TARBALL"

# --- 2. record source counts -------------------------------------------------
log "Recording source row counts..."
SRC_COUNTS="$(counts_prod)" || die "Failed to read source row counts."
log "Source: $SRC_COUNTS"

# --- 3. cut over -------------------------------------------------------------
log "Stopping the 4-container stack (volumes preserved)..."
dc -f "$PROD_COMPOSE" down

rollback() {
    warn "Rolling back to the 4-container stack..."
    dc -f "$SINGLE_COMPOSE" down 2>/dev/null || true
    dc -f "$PROD_COMPOSE" up -d
    warn "Rolled back. Your original ./volumes/db was never modified."
    warn "Raw safety tarball: $RAW_TARBALL ; portable archive: $ARCHIVE"
}

log "Building + starting the single image (fresh embedded PG at ./volumes/pgdata)..."
if ! dc -f "$SINGLE_COMPOSE" up -d --build; then
    rollback; die "Single image failed to start."
fi

log "Waiting for the single container to become healthy (schema migration runs now)..."
healthy=0
for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{.State.Health.Status}}' gearcargo 2>/dev/null || echo starting)"
    [ "$status" = "healthy" ] && { healthy=1; break; }
    sleep 3
done
if [ "$healthy" != "1" ]; then
    dc -f "$SINGLE_COMPOSE" logs --tail 60 || true
    rollback; die "Single container did not become healthy."
fi
ok "Single container healthy."

# --- 4. restore DB dump into embedded PG -------------------------------------
log "Restoring database into the embedded PostgreSQL..."
TMP_RESTORE="$(mktemp -d)"
trap 'rm -rf "$TMP_RESTORE"' EXIT
tar -xzf "$ARCHIVE" -C "$TMP_RESTORE" database/database.sql.gz
if ! gunzip -c "$TMP_RESTORE/database/database.sql.gz" | \
        dc -f "$SINGLE_COMPOSE" exec -T gearcargo env PGPASSWORD="$DB_PASSWORD" \
            psql -h 127.0.0.1 -U gearcargo -d gearcargo -v ON_ERROR_STOP=1 >/dev/null; then
    rollback; die "Database restore failed."
fi
ok "Database restored."

# --- 5. verify ---------------------------------------------------------------
log "Verifying row counts match the source..."
DST_COUNTS="$(counts_single)" || { rollback; die "Failed to read restored row counts."; }
log "Restored: $DST_COUNTS"
if [ "$SRC_COUNTS" != "$DST_COUNTS" ]; then
    warn "Row counts DIFFER: source=[$SRC_COUNTS] restored=[$DST_COUNTS]"
    rollback; die "Verification failed — rolled back."
fi

ok "Row counts match. Migration verified."
cat <<DONE

============================================================
 Migration complete and verified.
============================================================
 • Single container 'gearcargo' is running on port ${APP_PORT:-5000}.
 • Log in (you'll get a fresh session), then confirm:
     - a vehicle attachment + a receipt open (uploads mount)
     - the Backup page lists your history (backups mount)
     - settings / 2FA intact; a PII field decrypts (ENCRYPTION_KEY carried over)
 • Trigger a manual backup to confirm the in-container scheduler works:
     docker compose -f $SINGLE_COMPOSE exec gearcargo \\
         /etc/gearcargo/scripts/run-backup.sh manual

 Rollback (anytime): the old stack is intact.
     docker compose -f $SINGLE_COMPOSE down
     docker compose -f $PROD_COMPOSE up -d

 Keep the safety artifacts until you've run stable for days:
     raw tarball:      $RAW_TARBALL
     portable archive: $ARCHIVE
     old PG data dir:  ./volumes/db  (untouched)
============================================================
DONE
