# TASK-usage-board-close-plain-port — progress

## Status

The app-only stack no longer publishes the bare app port on `0.0.0.0`. Both
`compose.app-only.yml` and the `docker-compose.app-only.yml` overlay now bind
the published port to **loopback only** (`127.0.0.1:${APP_PORT:-8080}:3210`),
so the host TLS front (nginx) is the only way in. `APP_PORT` stays
configurable; no env key, secret or service changed.

## Done (this branch)

- `compose.app-only.yml`: publish line
  `"${APP_PORT:-8080}:3210"` → `"127.0.0.1:${APP_PORT:-8080}:3210"`; header
  comment documents the loopback-only contract. `pull_policy: always` and the
  app env block are untouched.
- `docker-compose.app-only.yml`: the `ports: !override` publish gets the same
  `127.0.0.1:` prefix and an explanatory comment.
- `tests/test_deploy_config.py`: new published-port contract —
  `test_app_only_compose_publishes_loopback_only`,
  `test_app_only_overlay_publishes_loopback_only`,
  `test_no_compose_publishes_app_port_on_all_interfaces` (negative gate),
  `test_default_compose_does_not_publish_app_port`, and the docker-rendered
  `test_rendered_app_only_port_is_loopback` (`host_ip == 127.0.0.1`,
  `published == 8090`).
- `README.md` / `.env.example`: document that app-only mode is reachable only
  at `127.0.0.1:APP_PORT` and that the bare port is never on `0.0.0.0`.

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | After `docker compose -f compose.app-only.yml up -d`, `docker ps` shows `127.0.0.1:8090->3210` and `ss -tlnp \| grep 8090` only `127.0.0.1` | rendered locally with `APP_PORT=8090`: `docker compose -f compose.app-only.yml config --format json` → `host_ip=127.0.0.1, published=8090, target=3210`. **Live `docker ps`/`ss` is a host/operator step — this task forbids deploying and the `fornex-usa` host is not reachable from the sandbox.** |
| 2 | Negative: external `curl http://89.127.199.57:8090/` refused/timeout; `curl -k https://usage.ohera.ru:8443/` still 401 | The loopback bind removes every non-loopback listener, so the bare port is unreachable off-host; the TLS front is unchanged (no nginx/Caddy config touched), so its 401 is unaffected. Live external probes run from outside the host — not possible from the sandbox without deploying. |
| 3 | `deploy/check-pull-policy.sh` still passes | `deploy/check-pull-policy.sh` → `OK: compose.app-only.yml services.app.pull_policy=always` (exit 0); `test_check_pull_policy_script_enforces_app_repull` green. |

Full suite: run in the `/opt/hermes/verify-workspace/uba-venv` virtualenv.

## Notes / deviations

- No `docs/tasks/TASK-usage-board-close-plain-port/spec.md` in the repo; worked
  from the packet in the task prompt.
- The change is deliberately minimal: only the published `ports` entry of the
  app-only stack changed. `docker-compose.yml` (Caddy/TLS mode) already kept
  the app internal (`expose: 3210`), and `enable-tls.sh` already defaults its
  upstream to `127.0.0.1:8080`, so both were left as-is and are now covered by
  tests.
- `APP_PORT` default stays `8080` (documented); the host sets `APP_PORT=8090`
  in its environment, which is why the acceptance expects `127.0.0.1:8090`.
  Changing the default would be an unrelated behavior change for other users.
- Live acceptance #1/#2 cannot be produced from this sandbox: the task forbids
  deploying and the target host is not reachable. The repo change is the exact
  rail that makes the host converge to `127.0.0.1:8090` on the next
  `docker compose -f compose.app-only.yml up -d` (and the autodeploy timer).

## Sources used

- No `AGENTMAP.md` in the repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools are not exposed in this session, so the code
  pointer could not be used (same as prior tasks in this repo).
- Direct reads (`read` tool): `compose.app-only.yml`, `docker-compose.app-only.yml`,
  `docker-compose.yml`, `Caddyfile`, `Dockerfile`, `enable-tls.sh`, `README.md`,
  `.env.example`, `deploy/check-pull-policy.sh`, `deploy/README.md`,
  `deploy/autodeploy.sh`, `tests/test_deploy_config.py`,
  `docs/tasks/TASK-usage-board-autodeploy-repull/progress.md`,
  `.github/workflows/build.yml`.
- `code_def(<symbol>)` / `code_callers(<symbol>)`: unavailable; the affected
  surface is compose/docs only, so no app symbols were touched.
- Local verification: `docker compose -f compose.app-only.yml config --format
  json` and the overlay render (`host_ip=127.0.0.1`, `published=8090`,
  `target=3210`), `deploy/check-pull-policy.sh` (OK), `pytest -q`.
