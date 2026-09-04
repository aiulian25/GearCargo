#!/command/with-contenv bash
# Oneshot (runs as root, first in the boot order): create the mounted data dirs
# and fix ownership. Host bind-mounts often arrive root-owned; the app, Postgres
# and Redis each run as their own unprivileged user, so we chown their dirs here
# while we still have root — before any service drops privileges.
set -u
. /etc/gearcargo/env.sh

echo "[init-perms] Preparing data directories (EMBEDDED_DB=$EMBEDDED_DB EMBEDDED_REDIS=$EMBEDDED_REDIS)"

mkdir -p /app/volumes/attachments /app/volumes/backups/system \
         /app/uploads /app/volumes/logs /run/gearcargo
# R4-21: chown only what is not already correct. `chown -R` issued a syscall
# per file on EVERY boot, so start-up time grew with the number of stored
# attachments; on a settled volume this find selects nothing and returns at
# once. Same end state — a host bind-mount arriving root-owned is still
# fixed, because those files match the predicate.
find /app/volumes /app/uploads \( ! -user gearcargo -o ! -group gearcargo \) \
     -exec chown gearcargo:gearcargo {} + 2>/dev/null || true
chown gearcargo:gearcargo /run/gearcargo 2>/dev/null || true

if [ "$EMBEDDED_DB" = "true" ]; then
    mkdir -p "$PGDATA"
    chown postgres:postgres "$PGDATA" 2>/dev/null || true
    chmod 700 "$PGDATA" 2>/dev/null || true
fi

if [ "$EMBEDDED_REDIS" = "true" ]; then
    mkdir -p /data
    chown redis:redis /data 2>/dev/null || true
fi

echo "[init-perms] Done."
