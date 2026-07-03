#!/command/with-contenv bash
# Longrun: the embedded Redis server (sessions, rate-limit, JWT blacklist, cache).
# Parks on sleep infinity when an external REDIS_URL is configured.
set -u
. /etc/gearcargo/env.sh

if [ "$EMBEDDED_REDIS" != "true" ]; then
    echo "[redis] External Redis ($GC_REDIS_HOST:$GC_REDIS_PORT) — embedded Redis disabled."
    exec sleep infinity
fi

args=(--dir /data
      --bind 127.0.0.1
      --port "${GC_REDIS_PORT}"
      --appendonly yes
      --maxmemory "${REDIS_MAXMEMORY:-128mb}"
      --maxmemory-policy allkeys-lru)
if [ -n "${GC_REDIS_PASS:-}" ]; then
    args+=(--requirepass "$GC_REDIS_PASS")
fi

echo "[redis] Starting embedded Redis 7 on 127.0.0.1:${GC_REDIS_PORT}"
exec s6-setuidgid redis redis-server "${args[@]}"
