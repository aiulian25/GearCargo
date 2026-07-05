#!/bin/bash
# Cron entry point for scheduled backups. Cron jobs get an empty environment, so
# we load the credentials the scheduler wrote at boot, then hand off to the
# docker-backup.sh archive builder (the archive format is unchanged, so backups
# restore through the in-app Backup page).
set -eu

envfile="/run/gearcargo/backup.env"
if [ ! -r "$envfile" ]; then
    echo "[run-backup] ERROR: $envfile missing — scheduler not ready." >&2
    exit 1
fi
# shellcheck disable=SC1090
. "$envfile"
export PGPASSWORD PGPORT DB_HOST DB_USER DB_NAME BACKUP_ROOT ATTACHMENTS_DIR UPLOADS_DIR KEEP_LAST

exec /app/scripts/docker-backup.sh "${1:-daily}"
