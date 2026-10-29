# TASK-usage-board-kimi-monthly — progress

## Status

Kimi Coding card now shows the windows the provider actually returns: the
rolling 5h window plus the two monthly meters (`limit_month_total` /
`limit_month_code`). A weekly window is emitted only when `limit_7d` exists;
otherwise `weekly` stays `None` and no null `weekly` record is exposed.

PR: https://github.com/Rast53/usage-board/pull/11

## Done (this branch)

- `app.py`:
  - `parse_kimi_usages()` reads `payload["usages"]` as a window map:
    `limit_5h` (fallback only when `limits[]` is empty), optional `limit_7d`,
    and both monthly meters.
  - `_parse_kimi_quota()` accepts either absolute `limit`/`used`/`remaining`
    numbers (`limits[].detail`, still the 5h priority) or `used_ratio`
    (multiplied by 100 for `used_percent`).
  - `probe_kimi_usage()` / `build_kimi_wallet()` carry `monthly_total` and
    `monthly_code` as flat keys; `weekly` is `None` when absent.
  - `_PROVIDER_LIMIT_WINDOWS["kimi"]` exposes `monthly_total` and
    `monthly_code`, so `/api/limits` returns them and omits missing `weekly`.
  - `build_pace_payload()` appends the two monthly lanes for `kimi-main`
    (`PACE_KIMI_MONTHLY_WINDOW_SPECS`) after the unchanged generic 5h/weekly
    sweep.
  - Removed `KIMI_WEEKLY_PLANS` and the stale “5h cap is 200” comment; the live
    payload's `limit` is used instead of inferring a plan from a weekly cap.
- `static/index.html`: the `p === 'kimi'` hero picks the first available
  window (5h → weekly → monthly_total); captions are «5 ч», «из недельной
  квоты», «из месячной квоты». Monthly meters render as separate detail rows
  «месяц (всего)» and «месяц (code)» with `used_percent` and reset date.
- `tests/fixtures/kimi_usages_2026-10-28.json` (live response) and
  `tests/fixtures/kimi_usages_with_7d.json` (synthetic weekly window).
- New tests: `tests/test_kimi_quota.py`, `tests/test_ui_kimi_caption.py`;
  additions to `tests/test_limits_api.py` and `tests/test_pace_api.py`.
- `README.md` / `.env.example`: Kimi capability comment updated.

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | Window-map literals and `used_ratio`→percent conversion in `app.py`; import succeeds | `parse_kimi_usages` + `_parse_kimi_quota`; `.venv/bin/python -c "import app"` → `import ok` |
| 2 | Live fixture: session 2.0 %, monthly_total/monthly_code 0.09 %, weekly `None` | `test_live_payload_parses_session_and_monthly_meters`, `test_probe_reads_usages_map_and_keeps_missing_weekly_none` |
| 3 | Synthetic `limit_7d` fixture → weekly 42.0 % + reset time | `test_synthetic_7d_window_is_parsed_when_present` |
| 4 | `/api/limits` has monthly meters at ≈0.09 and no null weekly | `test_limits_kimi_exposes_monthly_meters_without_null_weekly` |
| 5 | `/api/pace` adds Kimi monthly lanes, baseline 5h/weekly unchanged | `test_kimi_monthly_meters_add_lanes_without_moving_baseline`; `test_non_cursor_lanes_match_pre_change_baseline` still green |
| 6 | UI uses `w.session` / `w.monthly_total` / `w.monthly_code`, has both monthly labels, no unconditional weekly caption | `tests/test_ui_kimi_caption.py`; Node render of the live-shaped wallet shows 98 % / «5 ч» plus both month rows |
| 7 | Full suite green | `90 passed` |

No deploy performed. No network calls in tests (static fixtures + patched
`http_json`).

## Sources used

- No `AGENTMAP.md` at the repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools were not exposed in this session, so the
  pointer could not be used.
- Direct reads: `app.py` (`KIMI_WEEKLY_PLANS`, `_parse_kimi_quota`,
  `probe_kimi_usage`, `build_kimi_wallet`, `_PROVIDER_LIMIT_WINDOWS`,
  `_limit_window_entry`, `build_pace_payload`, `PACE_CURSOR_WINDOW_SPECS`),
  `static/index.html` (`heroFor` Kimi branch, `renderKimiCard`),
  `tests/test_limits_api.py`, `tests/test_pace_api.py`, `README.md`,
  `.env.example`.
- Shell discovery: `git status/log/remote`, `grep` for Kimi wiring, `pytest`
  for the baseline and the full suite, a Node harness to render the Kimi card.
