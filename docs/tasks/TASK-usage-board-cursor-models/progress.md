# TASK-usage-board-cursor-models — progress

## Status

usage-board: Cursor — per-model breakdown for the billing cycle (tokens, as in
the Cursor UI). Extends the existing Cursor card (`CURSOR_SESSION_TOKEN`) with a
per-model **Total Tokens** table sourced from Cursor's read-only dashboard CSV
export. Tests, docs and a PR; no deploy.

PR: https://github.com/Rast53/usage-board/pull/7

## Done (this branch)

- `app.py`: new per-model export pipeline.
  - Constants `CURSOR_EXPORT_URL` (`cursor.com/api/dashboard/export-usage-events-csv`),
    `CURSOR_EXPORT_STRATEGY = "tokens"` and `CURSOR_MODELS_SOURCE =
    "cursor-export-csv"`.
  - `aggregate_cursor_csv_models(csv_text)` — roll the export CSV into per-model
    token totals: items are `{model, total_tokens, input_tokens,
    cache_write_tokens, cache_read_tokens, output_tokens}`, sorted by
    `total_tokens` descending; header names are resolved by name (Cursor adds
    columns over time); a row with no model or no numeric token cell is
    discarded, an empty/broken `Total Tokens` cell falls back to the component
    columns so a garbage row never sinks the parse. Aliases
    `aggregate_cursor_models_csv` / `parse_cursor_export_csv`.
  - `cursor_export_url(start_ms, end_ms)` — always carries explicit
    `startDate` / `endDate` (epoch ms) and `strategy=tokens`; there is no
    parameter-less (full history) form.
  - `_cursor_export_window()` derives the epoch-ms window from the plan probe's
    billing cycle; `_cursor_export_models()` fetches + parses with a
    never-raising error path (`models_unavailable(reason=…)`).
  - `probe_cursor_usage()` attaches `result["models"]` after a successful plan
    probe; `build_cursor_wallet()` passes the models block through (fallback:
    `models_unavailable`). Export failure never alters the other wallet fields,
    so `/api/limits` keeps serving the three cursor percent limits.
- `static/index.html`: `cursorModelsTable()` renders the per-model token table
  inside the Cursor card details (model + tokens), with an unavailable note and
  the `cursor-export-csv` source line.
- `tests/test_cursor_provider.py`: +12 tests (60 total, was 48).
- `README.md` / `.env.example`: document the read-only per-model export and that
  it is windowed (never a full export).

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | CSV aggregator: live-shaped fixture, several models → items with summed `total_tokens`, desc; empty/broken cells tolerated (garbage row dropped, rest counted) | `test_aggregate_cursor_csv_sums_total_tokens_and_sorts_desc` (3000/2900/800, total 6700), `test_aggregate_cursor_csv_tolerates_empty_and_broken_cells` (broken Total Tokens → Output Tokens fallback; garbage rows dropped), snake_case + empty/unknown-format tests |
| 2 | Wallet on export success → `models.available=true`, `items>=1`, `source=cursor-export-csv`; on mock error/timeout → `available=false` with reason, other fields identical, `/api/limits` still cursor limits | `test_wallet_export_success_exposes_models`, `test_wallet_export_failure_keeps_other_fields`, `test_limits_keep_cursor_limits_on_export_failure` |
| 3 | Export URL has `startDate`/`endDate` (ms) + `strategy=tokens`; no param-less full export | `test_cursor_export_url_uses_window_and_tokens_strategy`, `test_probe_export_uses_windowed_url_not_full_export`, `test_probe_without_cycle_window_skips_export` |
| 4 | Without `CURSOR_SESSION_TOKEN`: zero CSV/network calls; card state unchanged (manual, no `models` on the probe) | `test_probe_without_token_makes_no_http_calls` (call_count 0, status manual) |
| 5 | Static: `node --check` green; Cursor card renders the model table with a mock wallet (desktop screenshot in PR) | `test_static_inline_script_passes_node_check`; PR screenshot (`docs/tasks/TASK-usage-board-cursor-models/cursor-models-desktop.png`) |

Full suite: `60 passed` (48 pre-existing + 12 new). No network calls in tests
(CSV fixtures + mocked `http_request`). No deploy performed.

## Notes / deviations

- The export endpoint and its CSV columns are **undocumented**; the parser
  resolves columns by header name and degrades to `models_unavailable(reason)`
  instead of failing the card. The window comes from the plan probe's billing
  cycle; if it is missing the export is **not** requested (avoids a full export),
  matching the no-params guard.
- `autoPercentUsed` / `apiPercentUsed` remain independent meters; the per-model
  table is the cycle token accounting and is shown separately.
- Tests make no live call; a real token is only exercised by the operator after
  merge (rules forbid deploy/secret handling here).

## Sources used

- No `AGENTMAP.md` in the repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools are not exposed in this session, so the
  code pointer could not be used.
- Direct reads (read tool): `app.py` (Cursor provider: constants, `_cursor_auth_headers`,
  `parse_cursor_dashboard_usage`, `probe_cursor_usage`, `build_cursor_wallet`,
  `models_unavailable`, `http_request`), `tests/test_cursor_provider.py`,
  `tests/test_app.py`, `static/index.html`, `README.md`, `.env.example`, and the
  prior `docs/tasks/TASK-usage-board-cursor-card/progress.md`.
- Shell discovery: `git log/status/remote`, `grep` for Cursor wiring, `node --check`
  on the extracted inline dashboard script.
- Cursor export contract (web, undocumented): agent-walker
  [`docs/cursor.md`](https://github.com/miiiiiiich/agent-walker/blob/HEAD/docs/cursor.md)
  (`GET cursor.com/api/dashboard/export-usage-events-csv?strategy=tokens`, CSV
  columns `Model`, `Input (w/o Cache Write)`, `Input (w/ Cache Write)`,
  `Cache Read`, `Output Tokens`, `Total Tokens`).
