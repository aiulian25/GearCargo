#!/command/with-contenv bash
# Dedicated scheduling role; migration success is a required s6 dependency.
set -eu
. /etc/gearcargo/env.sh
cd /app
/etc/gearcargo/scripts/cron-run.sh --prepare-only
if [ "${SCHEDULER_ENABLED:-true}" != "true" ]; then
    echo "[scheduler] Disabled on this instance."
    exec sleep infinity
fi
exec s6-setuidgid gearcargo env PATH="$PATH" GEARCARGO_PROCESS_ROLE=scheduler python scheduler.py
