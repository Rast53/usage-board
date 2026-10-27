# TASK-usage-board-spend-daily — progress

## Status

Daily spend history is now exposed by a read-only endpoint on
`Rast53/usage-board`: `GET /api/spend-daily?days=N`. It reads only the compact
`spend.jsonl` series, returns per-provider calendar-day points, and reports
missing data as an explicit `gap` instead of inventing zeroes. No deploy.

PR: https://github.com/Rast53/usage-board/pull/9

Sources used: `AGENTMAP.md` is absent at the repo root; `.gbrain-source` is also
absent, so there was no gbrain source id for `code_def` / `code_callers`.
Orientation came from `app.py` (existing `_spend_path`,
`_compact_snapshot_row`, provider extractors, `/api/limits` envelope) and the
existing tests under `tests/`.

## Done (this branch)

- `app.py`: `GET /api/spend-daily?days=N`.
  - `days` defaults to 30, accepts only 1..90; a non-integer or out-of-range
    value is an explicit `400`.
  - Envelope: `schema_version: "spend-daily.v1"`, `days`, `generated_at`,
    `providers`, plus a skipped-line counter.
  - Per provider: `unit`, `measured`, `gap` (when no points), `points[]` with
    `date`, `spent`, `partial`.
  - Source is `spend.jsonl` only. For each observed day the last snapshot is
    used; `spent` is the delta against the last snapshot before that day's
    start (`used_usd`, `total_usage`, remaining credits, etc. per provider).
    The first observed day in the window is `partial: true` with `spent: null`.
  - Providers without a usable spend metric are explicit gaps:
    `zai` → `no-metric`, `cursor` → `no-history`, both with empty `points` and
    `measured: false`; no zero is fabricated.
  - Broken JSONL lines are skipped and counted (`skipped_lines`, with
    `skipped` / `broken_lines` aliases); the route stays 200.
  - No network I/O, no state writes, no cache mutation.
- `tests/test_spend_daily_api.py`: 10 tests covering the two-day delta,
  partial first point, explicit cursor/zai gaps, malformed line survival,
  `days` validation, and the full 13-delta window.
- `README.md`: endpoint + envelope documentation.

## Acceptance self-check (agent)

| # | Check | Result |
|---|--------|--------|
| 1 | `python3 -m pytest tests/ -q` | `77 passed` (venv: fastapi/pytest/httpx/PySocks) |
| 2 | two-day fixture → two `opencode-go` points, second is `used_usd` delta | `test_spend_daily_delta` |
| 3 | first point `partial: true`, no invented spend | `test_spend_daily_first_point_partial` |
| 4 | `cursor`/`zai` have `gap`, empty `points`, not `measured: true` | `test_spend_daily_gaps_are_explicit` |
| 5 | broken JSONL line does not fail route, lands in skip counter | `test_spend_daily_survives_broken_line` |
| 6 | `days` outside 1..90 → `400` with explicit error | `test_spend_daily_days_validation` |
| 7 | full window → 13 deltas, no invented gap-provider points | `test_spend_daily_full_window` |
