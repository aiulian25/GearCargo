#!/bin/sh
# docker-backup.sh — Containerised GearCargo backup
#
# The archive builder for the single all-in-one image. Invoked by the in-image
# scheduler (run-backup.sh), which exports DB_HOST/PGPORT/credentials so pg_dump
# connects to the embedded PostgreSQL over the loopback interface.
#
# Called by the scheduler:
#   daily  — every day at 03:00 UTC
#   weekly — every Sunday at 03:30 UTC
#
# Archive format is restored through the in-app Backup page (Settings > Backup).
#
# Environment variables (all have defaults):
#   PGPASSWORD      — Postgres password              (required)
#   DB_HOST         — Postgres host                  (default: db)
#   DB_USER         — Postgres user                  (default: gearcargo)
#   DB_NAME         — Postgres database              (default: gearcargo)
#   BACKUP_ROOT     — Directory to write archives to (default: /backups)
#   ATTACHMENTS_DIR — Read-only attachments mount    (default: /attachments)
#   UPLOADS_DIR     — Read-only uploads mount        (default: /uploads)
#   KEEP_LAST       — Oldest archives to retain      (default: 7)

set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
ATTACHMENTS_DIR="${ATTACHMENTS_DIR:-/attachments}"
UPLOADS_DIR="${UPLOADS_DIR:-/uploads}"
DB_HOST="${DB_HOST:-db}"
DB_USER="${DB_USER:-gearcargo}"
DB_NAME="${DB_NAME:-gearcargo}"
KEEP_LAST="${KEEP_LAST:-7}"
FREQUENCY="${1:-daily}"

case "${FREQUENCY}" in
    daily|weekly|monthly|manual) ;;
    *)
        echo "[backup] ERROR: Invalid frequency '${FREQUENCY}'. Use: daily|weekly|monthly|manual" >&2
        exit 1
        ;;
esac

timestamp="$(date +"%Y%m%d_%H%M%S")"
backup_dir="${BACKUP_ROOT}/${FREQUENCY}"
archive_name="gearcargo_${FREQUENCY}_${timestamp}.tar.gz"
archive_path="${backup_dir}/${archive_name}"
temp_dir="$(mktemp -d /tmp/gc-backup.XXXXXX)"

cleanup() { rm -rf "${temp_dir}"; }
trap cleanup EXIT INT TERM

mkdir -p "${backup_dir}" \
         "${temp_dir}/database" \
         "${temp_dir}/media/attachments" \
         "${temp_dir}/media/uploads"

echo "[backup] ${FREQUENCY} backup started — $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# ── Database dump (PGPASSWORD inherited from environment) ────────────────────
echo "[backup] Dumping PostgreSQL database (${DB_HOST}/${DB_NAME})"
pg_dump \
    -h "${DB_HOST}" \
    -U "${DB_USER}" \
    "${DB_NAME}" \
    --clean --if-exists --no-owner --no-privileges \
    | gzip -c > "${temp_dir}/database/database.sql.gz"
echo "[backup] Database dump complete ($(du -h "${temp_dir}/database/database.sql.gz" | cut -f1))"

# ── Media directories (read-only mounts, best-effort) ───────────────────────
echo "[backup] Copying attachments"
if [ -d "${ATTACHMENTS_DIR}" ]; then
    cp -a "${ATTACHMENTS_DIR}/." "${temp_dir}/media/attachments/"
else
    echo "[backup] WARNING: attachments dir not found: ${ATTACHMENTS_DIR}"
fi

echo "[backup] Copying uploads"
if [ -d "${UPLOADS_DIR}" ]; then
    cp -a "${UPLOADS_DIR}/." "${temp_dir}/media/uploads/"
else
    echo "[backup] WARNING: uploads dir not found: ${UPLOADS_DIR}"
fi

# ── Manifest (compatible with restore.sh) ───────────────────────────────────
cat > "${temp_dir}/manifest.json" << MANIFEST
{
  "version": "3.0",
  "type": "system_full",
  "frequency": "${FREQUENCY}",
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "database": {
    "engine": "postgresql",
    "host": "${DB_HOST}",
    "name": "${DB_NAME}"
  },
  "media": {
    "attachments": true,
    "uploads": true
  }
}
MANIFEST

# ── Archive ──────────────────────────────────────────────────────────────────
tar -C "${temp_dir}" -czf "${archive_path}" manifest.json database media
archive_size="$(du -h "${archive_path}" | cut -f1)"
echo "[backup] Archive: ${archive_path} (${archive_size})"

# ── Rotation: remove oldest archives beyond KEEP_LAST ───────────────────────
set +e
ls -1t "${backup_dir}"/gearcargo_*.tar.gz 2>/dev/null \
    | tail -n "+$((KEEP_LAST + 1))" \
    | xargs -r rm -f
set -e

echo "[backup] Done — retaining last ${KEEP_LAST} ${FREQUENCY} backup(s)"
