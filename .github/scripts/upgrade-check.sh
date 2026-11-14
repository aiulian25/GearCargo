#!/usr/bin/env bash
# Installs the previous release the documented way, then starts the candidate image on the
# same data and requires it to come up ready with that data intact.
#
# The publish workflow runs this before it pushes anything. 1.10.0 passed every test that
# starts from an empty database and still could not open an existing one.
#
# Usage: .github/scripts/upgrade-check.sh <previous image> <candidate image>
set -euo pipefail

previous_image="$1"
candidate_image="$2"

readonly CONTAINER_NAME=gearcargo-upgrade-check
readonly CHECK_PORT=5899
readonly HEALTH_TIMEOUT_SECONDS=300
readonly HEALTH_POLL_SECONDS=4
readonly FAILURE_LOG_LINES=60
readonly MARKER_TABLE=upgrade_check_marker

work_folder="$(mktemp -d)"

cleanup() {
    (cd "$work_folder" && docker compose down --remove-orphans) >/dev/null 2>&1 || true
    # The data folders belong to the container's service users, so a container removes them.
    docker run --rm --entrypoint rm -v "$work_folder":/work "$candidate_image" -rf /work/volumes >/dev/null 2>&1 || true
    rm -rf "$work_folder"
}
trap cleanup EXIT

fail() {
    echo "upgrade-check: $1" >&2
    docker logs --tail "$FAILURE_LOG_LINES" "$CONTAINER_NAME" >&2 || true
    exit 1
}

use_image() {
    cat > "$work_folder/docker-compose.override.yml" <<YAML
services:
  gearcargo:
    image: $1
    container_name: $CONTAINER_NAME
YAML
}

wait_until_healthy() {
    local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
    until [ "$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null)" = healthy ]; do
        [ "$SECONDS" -lt "$deadline" ] || fail "$1 did not become healthy"
        sleep "$HEALTH_POLL_SECONDS"
    done
}

database() {
    docker exec "$CONTAINER_NAME" sh -c 'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -Atc "$1"' sh "$1"
}

cd "$work_folder"
docker run --rm "$previous_image" install > gearcargo-install.sh
sh gearcargo-install.sh >/dev/null
use_image "$previous_image"
# Answers to the installer: address, port, and "a reverse proxy runs here" (binds to loopback).
printf 'http://localhost:%s\n%s\ny\n' "$CHECK_PORT" "$CHECK_PORT" | ./setup.sh >/dev/null
wait_until_healthy "The previous release ($previous_image)"
database "CREATE TABLE $MARKER_TABLE AS SELECT 1 AS present" >/dev/null

use_image "$candidate_image"
docker compose up -d
wait_until_healthy "The candidate ($candidate_image), started on data from $previous_image,"
docker exec "$CONTAINER_NAME" curl -fsS http://localhost:5000/health/ready >/dev/null \
    || fail "The candidate is running but not ready"
[ "$(database "SELECT present FROM $MARKER_TABLE")" = 1 ] \
    || fail "The candidate started without the data written by $previous_image"
echo "upgrade-check: $candidate_image starts on data written by $previous_image"
