#!/usr/bin/env bash
# usage-board — autodeploy with an explicit image repull.
#
# Runs on the deployment host (fornex-usa) from a systemd timer. It:
#   1. repulls the published image (compose `pull_policy: always` + explicit pull);
#   2. recreates the app container only when the image digest actually changed;
#   3. waits for the container to become healthy;
#   4. prints the running `org.opencontainers.image.revision` label so a merge on
#      main can be verified without manual action.
#
# It never reads, writes or logs secrets: stack env is delivered to compose the
# same way as a manual `docker compose up -d` (host `.env` / environment).
#
# Optional environment:
#   COMPOSE_FILES   compose args, default "-f compose.app-only.yml"
#   APP_SERVICE     app service name, default "app"
#   APP_IMAGE       image ref, default "ghcr.io/rast53/usage-board:latest"
#   WAIT_TIMEOUT    seconds to wait for health, default 60
#   EXPECT_REVISION if set, fail unless the running container revision matches
set -euo pipefail

log() { printf '%s usage-board-autodeploy: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

COMPOSE_FILES="${COMPOSE_FILES:--f compose.app-only.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
APP_IMAGE="${APP_IMAGE:-ghcr.io/rast53/usage-board:latest}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-60}"

cd "${REPO_DIR}"

# shellcheck disable=SC2086  # COMPOSE_FILES is intentionally word-split.
compose() { docker compose ${COMPOSE_FILES} "$@"; }

image_id() { docker image inspect --format '{{.Id}}' "${APP_IMAGE}" 2>/dev/null || true; }

before="$(image_id)"
log "repull ${APP_IMAGE} (current image: ${before:-absent})"
compose pull "${APP_SERVICE}"
after="$(image_id)"
[ -n "${after}" ] || die "image ${APP_IMAGE} unavailable after pull"

if [ "${before}" != "${after}" ]; then
    log "image changed: ${before:-absent} -> ${after}"
else
    log "image unchanged: ${after}; recreate happens only if the container is stale"
fi

compose up -d --no-deps "${APP_SERVICE}"

cid="$(compose ps -q "${APP_SERVICE}")"
[ -n "${cid}" ] || die "no container for service ${APP_SERVICE}"

deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
while :; do
    state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${cid}")"
    case "${state}" in
        healthy|running) break ;;
    esac
    if [ "$(date +%s)" -ge "${deadline}" ]; then
        die "container ${cid} not healthy after ${WAIT_TIMEOUT}s (state=${state})"
    fi
    sleep 3
done

revision="$(docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${cid}")"
log "running ${cid} state=${state} revision=${revision:-<none>}"

if [ -n "${EXPECT_REVISION:-}" ] && [ "${revision}" != "${EXPECT_REVISION}" ]; then
    die "revision ${revision:-<none>} != EXPECT_REVISION ${EXPECT_REVISION}"
fi
