#!/command/with-contenv bash
# Longrun: the Flask API + PWA served by gunicorn — the only network-exposed
# service (0.0.0.0:5000, set in gunicorn.conf.py). Depends on the migrate
# oneshot, so it never starts before the schema exists.
set -u
. /etc/gearcargo/env.sh
cd /app

echo "[gunicorn] Starting application server on 0.0.0.0:5000"
exec s6-setuidgid gearcargo env PATH="$PATH" \
    gunicorn --config gunicorn.conf.py "app:create_app()"
