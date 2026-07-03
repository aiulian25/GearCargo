#!/command/with-contenv bash
# Longrun: the backup scheduler — replaces the separate 4-container `backup`
# service. It writes the credentials the backup job needs to a runtime env file
# (cron jobs don't inherit the container environment), then runs cron in the
# foreground. The schedule lives in the baked /etc/cron.d/gearcargo.
#
# Disable with BACKUP_ENABLED=false (e.g. if you back up externally).
set -u
. /etc/gearcargo/env.sh

if [ "${BACKUP_ENABLED:-true}" != "true" ]; then
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
    _emit ATTACHMENTS_DIR "/app/volumes/attachments"
    _emit UPLOADS_DIR     "/app/uploads"
    _emit KEEP_LAST       "${BACKUP_KEEP_LAST:-7}"
} > /run/gearcargo/backup.env
chown gearcargo:gearcargo /run/gearcargo/backup.env
chmod 600 /run/gearcargo/backup.env

echo "[cron] Backup scheduler ready — daily 03:00, weekly (Sun) 03:30 UTC."
exec cron -f -L 15
