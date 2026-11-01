#!/bin/bash
# Manual archive entry point. Load the protected credentials prepared at boot,
# then hand off to the archive builder, including its optional artifact-encryption policy.
set -eu

envfile="/run/gearcargo/backup.env"
if [ ! -r "$envfile" ]; then
    echo "[run-backup] ERROR: $envfile missing — scheduler not ready." >&2
    exit 1
fi
# shellcheck disable=SC1090
. "$envfile"
export PGPASSWORD PGPORT DB_HOST DB_USER DB_NAME BACKUP_ROOT ATTACHMENTS_DIR UPLOADS_DIR KEEP_LAST
export BACKUP_PASSPHRASE_FILE

# Never capture a database/media combination while restore is switching it.
restore_state="${RESTORE_STATE_FOLDER:-/app/volumes/backups/.restore}"
mkdir -p "$restore_state"
exec 9>"$restore_state/lock"
flock --shared 9
if [ -e "$restore_state/active.json" ]; then
    echo "[run-backup] Restore recovery is pending; backup deferred." >&2
    exit 1
fi

exec /app/scripts/docker-backup.sh "${1:-daily}"
