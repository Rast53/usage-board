#!/usr/bin/env bash
# usage-board — gate: the `app` service must repull the published image on every
# deploy, so a plain `docker compose up -d` moves the host to the newest merge.
#
# Usage: deploy/check-pull-policy.sh [compose-file ...]
# Defaults to compose.app-only.yml (the fornex-usa app-only stack). The default
# docker-compose.yml needs a host .env (or .env.example) for interpolation.
#
# Exit 0 when every file has services.app.pull_policy == always, 1 otherwise.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

files=("$@")
if [ "${#files[@]}" -eq 0 ]; then
    files=(compose.app-only.yml)
fi

rc=0
for f in "${files[@]}"; do
    policy="$(docker compose -f "${f}" config --format json \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["app"].get("pull_policy", ""))')"
    if [ "${policy}" != "always" ]; then
        echo "FAIL: ${f} services.app.pull_policy=${policy:-<unset>} (want always)" >&2
        rc=1
    else
        echo "OK: ${f} services.app.pull_policy=always"
    fi
done
exit "${rc}"
