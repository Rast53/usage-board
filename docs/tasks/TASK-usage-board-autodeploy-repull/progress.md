# TASK-usage-board-autodeploy-repull — progress

## Status

Autodeploy with an explicit image **repull** for `Rast53/usage-board` on
`fornex-usa`: the `app` service now has `pull_policy: always`, and a bundled
systemd timer + `deploy/autodeploy.sh` move the host to the image of the newest
`main` merge with no manual action, verifying the
`org.opencontainers.image.revision` label. No deploy is performed from this
branch (per task rules).

## Done (this branch)

- `compose.app-only.yml` / `docker-compose.yml`: `app` service gains
  `pull_policy: always` — an ordinary `docker compose up -d` repulls
  `ghcr.io/rast53/usage-board:latest` before recreating. No other service,
  env key or volume was touched.
- `deploy/autodeploy.sh` (new, executable): idempotent one-shot that
  1. records the local image ID, 2. `docker compose pull app`,
  3. logs whether the digest changed, 4. `docker compose up -d --no-deps app`,
  5. waits for `healthy`, 6. prints
  `{{index .Config.Labels "org.opencontainers.image.revision"}}`, and
  7. fails hard when `EXPECT_REVISION` is set and the label differs. It never
  reads, writes or logs `.env`/secrets — stack env delivery is unchanged.
- `deploy/usage-board-autodeploy.service` + `.timer` (new): `Type=oneshot` unit
  running the script every 5 minutes (`OnBootSec=2min`), `WantedBy=timers.target`.
- `.github/workflows/build.yml`: new `Assert app repulls the image on deploy`
  step; renders `docker compose -f compose.app-only.yml config --format json`
  (and the default compose) and fails unless `services.app.pull_policy ==
  "always"`. This is the PR grep-gate on the rendered config.
- `tests/test_deploy_config.py` (new, 9 tests): app-only + default compose carry
  `pull_policy: always`; app-only env-key contract is byte-frozen (negative
  gate); script executable, repulls, recreates only app, checks the revision
  label, supports `EXPECT_REVISION`, and does not redirect into `.env`; systemd
  service/timer are wired; CI gate present.
- `README.md` + `deploy/README.md`: install/verify instructions for the host
  timer and the exact `docker inspect … revision` command.

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | `docker inspect usage-board-app-1 --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'` matches HEAD `main` after the nearest merge without manual action | rail delivered: `pull_policy: always` + 5-min systemd timer repull and print the label; the script exits non-zero if `EXPECT_REVISION` (== `git rev-parse origin/main`) does not match. **Live host value is an operator/CI step — no deploy from this branch** |
| 2 | `docker compose -f compose.app-only.yml config` contains `pull_policy: always` for app (grep-gate in PR) | rendered locally: `services.app.pull_policy=always`; CI step asserts it via `config --format json`; `tests/test_deploy_config.py::test_app_only_compose_repulls_image` green |
| 3 | Negative: `.env`/creds unchanged (diff outside the compose app service section is empty) | `.env`/`.env.example` untouched; the only compose edits are one `pull_policy` line inside `services.app`; `test_app_only_env_contract_unchanged` freezes the app-only env keys; `test_autodeploy_does_not_touch_env_or_secrets` green |

Full suite: `42 passed` (33 pre-existing + 9 new).

## Notes / deviations

- No `docs/tasks/TASK-usage-board-autodeploy-repull/spec.md` in the repo; worked
  from the packet in the task prompt.
- The live revision fact (acceptance #1) cannot be produced from this sandbox:
  the task forbids deploying and the `fornex-usa` host is not reachable here.
  The branch makes it automatic and verifiable: install
  `deploy/usage-board-autodeploy.{service,timer}` once on the host
  (`deploy/README.md`), after which each `main` merge is picked up within 5
  minutes.
- The autodeploy script defaults to the app-only stack
  (`COMPOSE_FILES="-f compose.app-only.yml"`); the unit comment/README cover the
  bundled Caddy/TLS mode (`-f docker-compose.yml`).

## Sources used

- No `AGENTMAP.md` in the repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools are not exposed in this session, so the code
  pointer could not be used (same as prior tasks in this repo).
- Direct reads (`read` tool): `compose.app-only.yml`, `docker-compose.yml`,
  `docker-compose.app-only.yml`, `Dockerfile`, `.github/workflows/build.yml`,
  `README.md`, `pytest.ini`, `enable-tls.sh`, `docs/tasks/TASK-usage-board-*/progress.md`,
  `tests/` listing.
- `code_def(<symbol>)` / `code_callers(<symbol>)`: unavailable; app-side symbols
  (`KNOWN_PROVIDERS`, `collect_state`, `/api/limits`) were located by direct
  `grep`/reads instead, and are untouched by this change.
- Local verification: `docker compose -f compose.app-only.yml config` /
  `--format json` (`services.app.pull_policy == always`), `bash -n
  deploy/autodeploy.sh`, `pytest -q` → 42 passed (venv
  `/opt/hermes/verify-workspace/uba-venv`).
