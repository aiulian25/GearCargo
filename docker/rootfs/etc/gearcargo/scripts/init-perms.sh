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
give_to() { # user, then the data trees that must belong to it
    local owner="$1"; shift
    find "$@" \( ! -user "$owner" -o ! -group "$owner" \) \
         -exec chown "$owner:$owner" {} + 2>/dev/null || true
}

give_to gearcargo /app/volumes /app/uploads
chown gearcargo:gearcargo /run/gearcargo 2>/dev/null || true

# The whole tree, not only its top folder: files written by an image whose service user had
# another ID are otherwise unreadable. 1.10.0 shipped postgres as 997 instead of 101 and could
# not open databases created by earlier versions.
if [ "$EMBEDDED_DB" = "true" ]; then
    mkdir -p "$PGDATA"
    give_to postgres "$PGDATA"
    chmod 700 "$PGDATA" 2>/dev/null || true
fi

if [ "$EMBEDDED_REDIS" = "true" ]; then
    mkdir -p /data
    give_to redis /data
fi

echo "[init-perms] Done."
