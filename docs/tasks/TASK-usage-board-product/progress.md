# TASK-usage-board-product — progress

## Status

Productization pass on `Rast53/usage-board`: scrub infra traces, machine-checkable TLS compose rail, test suite, PR.

## Done (this branch)

- `enable-tls.sh`: parameterized `DOMAIN` / `UPSTREAM` (no host-specific defaults).
- `app.py`: default data/static paths → `/opt/usage-board/…`.
- `docker-compose.yml`: Caddy service tagged `profiles: ["tls"]` (still auto-starts via `app` `depends_on`).
- CI: `pytest` job + `docker compose --profile tls config` in compose-check.
- `tests/test_app.py`: health, providers allowlist, basic-auth helper, summary shape.

## Not done here (ops / dogfood — per task rules: no deploy from agent)

- Dogfood on the test VPS (app-only + host nginx + LE) — manual/ops.
- `docker pull ghcr.io/rast53/usage-board:latest` on the test host.
- Negative prod regression checks and legacy private repo visibility — manual/ops.

## Acceptance self-check (agent)

| # | Check | Result |
|---|--------|--------|
| 1 | `grep` infra patterns in `*.py,*.yml,*.md,*.html` | clean after scrub |
| 2 | CI green + GHCR image | CI on PR; image on main pushes |
| 3 | Dogfood on test VPS | out of scope (no deploy) |
| 4 | `docker compose --profile tls config` | CI compose-check |
| 5–6 | Prod negative / old repo | out of scope (no deploy) |

## Sources used

- Task packet (no `docs/tasks/TASK-usage-board-product/spec.md` in repo).
- No `AGENTMAP.md` in repo root.
- gbrain `code_def` / `code_callers`: unavailable (`permission_denied` for agent callers); used gbrain `search` for deployment context only.
- Direct file reads: `README.md`, `docker-compose.yml`, `docker-compose.app-only.yml`, `.env.example`, `.github/workflows/build.yml`, `enable-tls.sh`, `app.py`.
