#!/command/with-contenv bash
# Legacy cron service, no longer activated. The dedicated scheduler calls
# --prepare-only to retain the protected environment for manual archive commands.
# The baked cron schedule is inert; all scheduled work belongs to scheduler.py.
set -u
. /etc/gearcargo/env.sh

if [ "${1:-}" != "--prepare-only" ] && [ "${BACKUP_ENABLED:-true}" != "true" ]; then
    echo "[cron] BACKUP_ENABLED=false — in-container scheduled backups disabled."
    exec sleep infinity
fi

# Emit KEY='value' with safe single-quote escaping for the /bin/sh-sourced wrapper.
_emit() { printf "%s='%s'\n" "$1" "$(printf '%s' "$2" | sed "s/'/'\\\\''/g")"; }

mkdir -p /run/gearcargo
{
    _emit PGPASSWORD      "$GC_DB_PASS"
    _emit PGPORT          "$GC_DB_PORT"
    _emit DB_HOST         "$GC_DB_HOST"
    _emit DB_USER         "$GC_DB_USER"
    _emit DB_NAME         "$GC_DB_NAME"
    _emit BACKUP_ROOT     "/app/volumes/backups/system"
    _emit RESTORE_STATE_FOLDER "${RESTORE_STATE_FOLDER:-${BACKUP_FOLDER:-/app/volumes/backups}/.restore}"
    _emit ATTACHMENTS_DIR "/app/volumes/attachments"
    _emit UPLOADS_DIR     "/app/uploads"
    _emit KEEP_LAST       "${BACKUP_KEEP_LAST:-7}"
    _emit BACKUP_PASSPHRASE_FILE "${BACKUP_PASSPHRASE_FILE:-}"
} > /run/gearcargo/backup.env
chown gearcargo:gearcargo /run/gearcargo/backup.env
chmod 600 /run/gearcargo/backup.env

# Keep the documented manual backup command usable after cron is retired.
if [ "${1:-}" = "--prepare-only" ]; then
    exit 0
fi

echo "[cron] Backup scheduler ready — daily 03:00, weekly (Sun) 03:30 UTC."
exec cron -f -L 15
