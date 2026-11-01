#!/bin/sh
# docker-backup.sh — Containerised GearCargo backup
#
# The archive builder for the single all-in-one image. Invoked by the in-image
# scheduler service or manual run-backup.sh, which export DB_HOST/PGPORT/credentials so pg_dump
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
#   BACKUP_PASSPHRASE_FILE — Optional mounted secret; enables .tar.gz.gcb encryption

set -eu
umask 077

crypto_script="$(dirname "$0")/../backup_crypto.py"
if [ ! -f "$crypto_script" ]; then crypto_script="$(dirname "$0")/../backend/backup_crypto.py"; fi
protection=plaintext
if [ -n "${BACKUP_PASSPHRASE_FILE:-}" ]; then
    python3 "$crypto_script" check-key --passphrase-file "$BACKUP_PASSPHRASE_FILE"
    protection=encrypted
fi

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

timestamp="${BACKUP_OCCURRENCE:-$(date +"%Y%m%d_%H%M%S")}"
case "$timestamp" in *[!0-9_]*|'') echo '[backup] Invalid occurrence identity' >&2; exit 1;; esac
backup_dir="${BACKUP_ROOT}/${FREQUENCY}"
archive_name="gearcargo_${FREQUENCY}_${timestamp}.tar.gz"
if [ "$protection" = encrypted ]; then archive_name="${archive_name}.gcb"; fi
archive_path="${backup_dir}/${archive_name}"
if [ -n "${BACKUP_OCCURRENCE:-}" ] && [ -f "$archive_path" ]; then
    if [ "$protection" = encrypted ]; then
        # Authenticate the existing artifact before treating a retry as complete.
        python3 "$crypto_script" verify --passphrase-file "$BACKUP_PASSPHRASE_FILE" --input "$archive_path"
        echo '[backup] Encrypted scheduled occurrence already archived.'
        exit 0
    elif tar -tzf "$archive_path" >/dev/null 2>&1; then
        echo '[backup] Plaintext scheduled occurrence already archived.'
        exit 0
    fi
fi
partial_archive=""
temp_dir="$(mktemp -d /tmp/gc-backup.XXXXXX)"

cleanup() { rm -rf "${temp_dir}"; if [ -n "$partial_archive" ]; then rm -f "$partial_archive"; fi; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "${backup_dir}" \
         "${temp_dir}/database" \
         "${temp_dir}/media/attachments" \
         "${temp_dir}/media/uploads"
partial_archive="$(mktemp "${archive_path}.partial.XXXXXX")"

echo "[backup] ${FREQUENCY} backup started — $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[backup] Artifact protection: ${protection}"
if [ "$protection" = plaintext ]; then
    echo '[backup] Contents are readable without a backup key. Use access-restricted encrypted storage.'
fi

# ── Database dump (PGPASSWORD inherited from environment) ────────────────────
echo "[backup] Dumping PostgreSQL database (${DB_HOST}/${DB_NAME})"
pg_dump \
    -h "${DB_HOST}" \
    -U "${DB_USER}" \
    "${DB_NAME}" \
    --clean --if-exists --no-owner --no-privileges \
    > "${temp_dir}/database/database.sql"
gzip "${temp_dir}/database/database.sql"
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
  "artifact_protection": "${protection}",
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
tar -C "${temp_dir}" -czf "$partial_archive" manifest.json database media
if [ "$protection" = encrypted ]; then
    python3 "$crypto_script" encrypt --format tar.gz --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
        --input "$partial_archive" --output "$archive_path"
    rm -f "$partial_archive"
else
    mv -f "$partial_archive" "$archive_path"
fi
archive_size="$(du -h "${archive_path}" | cut -f1)"
echo "[backup] Archive: ${archive_path} (${archive_size})"

# ── Rotation: remove oldest archives beyond KEEP_LAST ───────────────────────
set +e
ls -1t "${backup_dir}"/gearcargo_*.tar.gz "${backup_dir}"/gearcargo_*.tar.gz.gcb 2>/dev/null \
    | tail -n "+$((KEEP_LAST + 1))" \
    | xargs -r rm -f
set -e

echo "[backup] Done — retaining last ${KEEP_LAST} ${FREQUENCY} backup(s)"
