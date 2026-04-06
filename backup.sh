#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-${ROOT_DIR}/volumes/backups/system}"
ATTACHMENTS_DIR="${ATTACHMENTS_DIR:-${ROOT_DIR}/volumes/attachments}"
UPLOADS_DIR="${UPLOADS_DIR:-${ROOT_DIR}/volumes/uploads}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-gearcargo}"
DB_NAME="${DB_NAME:-gearcargo}"
DB_PASSWORD="${DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"
KEEP_LAST="${KEEP_LAST:-3}"
BACKUP_FREQUENCY="${BACKUP_FREQUENCY:-${1:-daily}}"

case "${BACKUP_FREQUENCY}" in
    daily|weekly|monthly|manual)
        ;;
    *)
        echo "Invalid backup frequency: ${BACKUP_FREQUENCY}" >&2
        echo "Use one of: daily, weekly, monthly, manual" >&2
        exit 1
        ;;
esac

if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE=(docker compose)
else
    DOCKER_COMPOSE=(docker-compose)
fi

run_db_command() {
    if [[ -n "${DB_PASSWORD}" ]]; then
        "${DOCKER_COMPOSE[@]}" exec -T -e PGPASSWORD="${DB_PASSWORD}" "${DB_SERVICE}" "$@"
    else
        "${DOCKER_COMPOSE[@]}" exec -T "${DB_SERVICE}" "$@"
    fi
}

copy_dir_contents() {
    local source_dir="$1"
    local target_dir="$2"

    mkdir -p "${target_dir}"
    if [[ -d "${source_dir}" ]]; then
        tar -C "${source_dir}" -cf - . | tar -C "${target_dir}" -xf -
    fi
}

rotate_backups() {
    local target_dir="$1"
    shopt -s nullglob
    local archives=("${target_dir}"/gearcargo_*.tar.gz)
    if (( ${#archives[@]} <= KEEP_LAST )); then
        shopt -u nullglob
        return
    fi

    mapfile -t archives < <(ls -1t "${target_dir}"/gearcargo_*.tar.gz)
    local index
    for (( index=KEEP_LAST; index<${#archives[@]}; index++ )); do
        rm -f "${archives[$index]}"
    done
    shopt -u nullglob
}

timestamp="$(date +"%Y%m%d_%H%M%S")"
backup_dir="${BACKUP_ROOT}/${BACKUP_FREQUENCY}"
archive_name="gearcargo_${BACKUP_FREQUENCY}_${timestamp}.tar.gz"
archive_path="${backup_dir}/${archive_name}"
temp_dir="$(mktemp -d)"

cleanup() {
    rm -rf "${temp_dir}"
}
trap cleanup EXIT

mkdir -p "${backup_dir}" "${temp_dir}/database" "${temp_dir}/media/attachments" "${temp_dir}/media/uploads"

echo "Creating ${BACKUP_FREQUENCY} GearCargo backup"
echo "Dumping PostgreSQL database"
run_db_command pg_dump --clean --if-exists --no-owner --no-privileges -U "${DB_USER}" "${DB_NAME}" | gzip -c > "${temp_dir}/database/database.sql.gz"

echo "Copying attachments"
copy_dir_contents "${ATTACHMENTS_DIR}" "${temp_dir}/media/attachments"

echo "Copying uploads"
copy_dir_contents "${UPLOADS_DIR}" "${temp_dir}/media/uploads"

cat > "${temp_dir}/manifest.json" <<EOF
{
  "version": "3.0",
  "type": "system_full",
  "frequency": "${BACKUP_FREQUENCY}",
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "database": {
    "engine": "postgresql",
    "service": "${DB_SERVICE}",
    "name": "${DB_NAME}"
  },
  "media": {
    "attachments": true,
    "uploads": true
  }
}
EOF

tar -C "${temp_dir}" -czf "${archive_path}" manifest.json database media
rotate_backups "${backup_dir}"

archive_size="$(du -h "${archive_path}" | cut -f1)"
echo "Backup completed"
echo "Archive: ${archive_path}"
echo "Size: ${archive_size}"
echo "Retention: keeping last ${KEEP_LAST} ${BACKUP_FREQUENCY} backup(s)"
