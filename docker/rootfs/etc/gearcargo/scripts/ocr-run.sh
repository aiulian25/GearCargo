#!/command/with-contenv bash
set -eu
. /etc/gearcargo/env.sh
cd /app
slot="$1"
capacity="${OCR_MAX_CONCURRENCY:-2}"
enabled="${OCR_WORKER_ENABLED:-true}"
if [ "$capacity" -lt 1 ]; then capacity=1; fi
if [ "$capacity" -gt 2 ]; then capacity=2; fi
if [ "${enabled,,}" != "true" ] || [ "$slot" -gt "$capacity" ]; then
    echo "[ocr] Slot $slot disabled."
    exec sleep infinity
fi
echo "[ocr] Starting durable worker for slot $slot."
exec s6-setuidgid gearcargo env PATH="$PATH" python ocr_worker.py --slot "$slot"
