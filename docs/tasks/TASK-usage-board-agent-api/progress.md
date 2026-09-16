# TASK-usage-board-agent-api — progress

## Status

Add a machine-readable JSON limits API for agents (`GET /api/limits`) on
`Rast53/usage-board`, without touching the existing UI/API surface, plus tests,
docs and a PR.

## Done (this branch)

- `app.py`: new `GET /api/limits` agent envelope.
  - Lists **every enabled provider** (`PROVIDERS` allowlist; default = all 6)
    under its stable id from `KNOWN_PROVIDERS`: `deepseek`, `openrouter`,
    `zai`, `commandcode`, `kimi`, `opencode-go`.
  - Per provider: `id`, `label`, `kind`, `configured`, `status`, `ok`,
    `probed_at`, `remaining_summary`, `error`, normalized `limits[]`
    (`id`, `label`, `unit`, `used`, `limit`, `remaining`, `used_percent`,
    `remaining_percent`, `reset_at`, `status`, `exceeded`, `summary`).
  - Provider errors surface per entry **and** in top-level `errors`; the route
    never returns 500. No network I/O — built from cached poller state.
  - Optional `AGENT_API_TOKEN` gate on `/api/limits` only
    (`Authorization: Bearer`, `X-Agent-Token`, `X-Api-Token`); all other routes
    stay public. Unset token = public route.
- `app.py`: `GET /api/usage` alias of `/api/summary` so the legacy usage
  envelope/format is explicitly preserved; `/api/summary` itself is unchanged.
- `tests/test_limits_api.py`: 9 tests — envelope ids, allowlist, window
  normalization, provider error → `errors` (not 500), normalizer exception,
  total failure fallback, legacy `/api/usage` + `/api/summary` format, token
  gate (401/200) and "other routes public".
- `README.md` / `.env.example`: document `/api/limits`, the token and the
  stable-id contract.

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_limits_api.py` green; envelope has all enabled providers + stable ids; provider error → `errors`, not 500 | 9 passed |
| 2 | `curl -s <board>/api/limits \| jq '.providers \| keys'` ⊇ 6 stable ids on a local instance | `["commandcode","deepseek","kimi","opencode-go","openrouter","zai"]` |
| 3 | `/api/usage` route + response format unchanged (test-double on old format green) | `test_legacy_usage_route_and_format_unchanged` green; `/api/summary` untouched |
| 4 | With `AGENT_API_TOKEN`, no token → 401 on `/api/limits`; other routes public | 401/401/200 verified over HTTP; test green |

Full suite: `14 passed` (5 pre-existing + 9 new).

## Notes / deviations

- The packet names `GET /api/usage`, but this repo snapshot has **no**
  `/api/usage` route and no `docs/tasks/TASK-usage-board-agent-api/spec.md`.
  The closest existing legacy usage envelope is `GET /api/summary`. It is left
  untouched; `/api/usage` was added as a thin alias returning that same
  envelope so the "old format" contract is explicit and testable.
- No deploy performed (per task rules). Local dev instance used for the curl
  check only.
- Could not run `pip`/`ensurepip` in this sandbox; tests were run with an
  available FastAPI/httpx/pytest virtualenv on the host.

## Sources used

- No `AGENTMAP.md` in this repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools are not exposed in this session, so the
  pointer could not be used.
- Direct reads (read tool): `app.py` (routes, `KNOWN_PROVIDERS`,
  `get_enabled_providers`, `get_visible_providers`, `collect_state`, wallet
  builders/normalizers), `tests/test_app.py`, `README.md`, `.env.example`,
  `static/index.html` (route usage), `docs/tasks/TASK-usage-board-product/progress.md`.
- Shell discovery only: `git log`, `find docs tests -type f`, `grep` for
  `api/usage` / `api/limits` / `AGENT_API_TOKEN` (all absent before this change).
