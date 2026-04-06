#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-${ROOT_DIR}/volumes/backups/system}"
ATTACHMENTS_DIR="${ATTACHMENTS_DIR:-${ROOT_DIR}/volumes/attachments}"
UPLOADS_DIR="${UPLOADS_DIR:-${ROOT_DIR}/volumes/uploads}"
DB_SERVICE="${DB_SERVICE:-db}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"
DB_USER="${DB_USER:-gearcargo}"
DB_NAME="${DB_NAME:-gearcargo}"
DB_PASSWORD="${DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"
RESTORE_FORCE="${RESTORE_FORCE:-false}"

if [[ $# -lt 1 ]]; then
    echo "Usage: ./restore.sh <backup_file.tar.gz>" >&2
    echo >&2
    echo "Available backups:" >&2
    find "${BACKUP_ROOT}" -type f -name '*.tar.gz' | sort -r >&2 || true
    exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "Backup file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

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

clear_directory() {
    local target_dir="$1"
    mkdir -p "${target_dir}"
    find "${target_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
}

copy_dir_contents() {
    local source_dir="$1"
    local target_dir="$2"

    mkdir -p "${target_dir}"
    if [[ -d "${source_dir}" ]]; then
        tar -C "${source_dir}" -cf - . | tar -C "${target_dir}" -xf -
    fi
}

TEMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

if [[ "${RESTORE_FORCE}" != "true" ]]; then
    echo "This will replace the GearCargo database, attachments, and uploads from ${BACKUP_FILE}."
    read -r -p "Type 'yes' to continue: " confirm
    if [[ "${confirm}" != "yes" ]]; then
        echo "Restore cancelled"
        exit 0
    fi
fi

echo "Extracting backup archive"
tar -xzf "${BACKUP_FILE}" -C "${TEMP_DIR}"

if [[ ! -f "${TEMP_DIR}/database/database.sql.gz" ]]; then
    echo "Backup archive is missing database/database.sql.gz" >&2
    exit 1
fi

echo "Stopping backend service"
"${DOCKER_COMPOSE[@]}" stop "${BACKEND_SERVICE}"

restore_ok=false
trap 'if [[ "${restore_ok}" != "true" ]]; then "${DOCKER_COMPOSE[@]}" start "${BACKEND_SERVICE}" >/dev/null 2>&1 || true; fi; cleanup' EXIT

echo "Restoring PostgreSQL database"
gunzip -c "${TEMP_DIR}/database/database.sql.gz" | run_db_command psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${DB_NAME}"

echo "Restoring attachments"
clear_directory "${ATTACHMENTS_DIR}"
copy_dir_contents "${TEMP_DIR}/media/attachments" "${ATTACHMENTS_DIR}"

echo "Restoring uploads"
clear_directory "${UPLOADS_DIR}"
copy_dir_contents "${TEMP_DIR}/media/uploads" "${UPLOADS_DIR}"

echo "Starting backend service"
"${DOCKER_COMPOSE[@]}" start "${BACKEND_SERVICE}"
restore_ok=true

echo "Restore completed successfully"
echo "Source archive: ${BACKUP_FILE}"
