# TASK-usage-board-cursor-pace — progress

## Status

usage-board: Cursor in «Темп квот» — two monthly bars (Cursor-модели / другие
модели). `build_pace_payload` now emits the two Cursor meters as labelled
`monthly` lanes; the pace panel renders two distinguishable dots in the
«месяц» column. Tests, docs and a desktop screenshot; no deploy.

PR: (opened from `dsh/TASK-usage-board-cursor-pace`).

## Done (this branch)

- `app.py`: Cursor pace lanes.
  - New `PACE_CURSOR_WINDOW_SPECS = (("cursor_models", "Cursor-модели"),
    ("other_models", "другие модели"))`.
  - `build_pace_payload`: the `cursor-main` account no longer runs the generic
    session/weekly/monthly sweep. It emits exactly the two Cursor meters as
    `window == "monthly"` lanes, each carrying a `label`; the plan `total`
    meter stays out of the panel. Every other provider keeps the old code path,
    so its lane dicts are byte-identical (no `label` key).
  - `_cursor_pace_window()` normalizes a meter to a pace window and falls back
    to an account-level `next_reset_at` / `billing_cycle_end` when a meter has
    no reset of its own — so a bare-percent fixture yields the same lanes as
    the live `quota_cache` shape.
- `static/index.html`: `paceLaneLabel()` / `paceLaneColor()` prefer the lane
  label and `PACE_LANE_COLORS` (`Cursor-модели` → `#22d3ee`,
  `другие модели` → `#f59e0b`); the SVG dots, tooltips, reset lines and legend
  all use them and fall back to the provider name/colour for other lanes.
- `tests/test_pace_api.py`: +7 tests (suite 60 → 67).
- `docs/tasks/TASK-usage-board-cursor-pace/cursor-pace-desktop.png`: desktop
  screenshot of the pace panel rendered from a mocked `/api/pace`.

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | `build_pace_payload` on a `quota_cache` with `cursor-main` (total 85.56 / cursor_models 86.7 / other_models 74.18, `next_reset_at=2026-09-25T12:27:11Z`) puts `cursor-main` in `accounts` with two `window=="monthly"` lanes: 86.7 «Cursor-модели», 74.18 «другие модели»; not in `no_window` | `test_cursor_gets_two_monthly_lanes_with_labels`, `test_cursor_lanes_do_not_leak_the_generic_window_sweep`, `test_cursor_simplified_fixture_uses_account_level_reset` |
| 2 | zai/commandcode/kimi/opencode-go lanes unchanged vs the pre-change baseline; deepseek/openrouter stay in `no_window` | `test_non_cursor_lanes_match_pre_change_baseline` (exact lane dicts captured before the change, and `"label" not in lane`) |
| 3 | `node --check` green; page rendered with mocked `/api/pace` shows two Cursor dots with distinct labels/colours in the «месяц» column; desktop screenshot in the PR | `test_monthly_column_renders_two_distinct_cursor_dots` (Node harness: 2 `<circle>`, labels present, `#22d3ee` + `#f59e0b`); `test_static_inline_script_passes_node_check`; `cursor-pace-desktop.png` (`2480x1326`, 2× DPR) |
| 4 | Cursor `/api/limits` unchanged | `tests/test_limits_api.py` + `tests/test_cursor_provider.py` (incl. `test_limits_keep_cursor_limits_on_export_failure`) still green |

Full suite: `67 passed`. No network calls in tests (static fixture + Node
harness with stubbed `fetch`). No deploy performed.

## Notes / deviations

- The plan `total` meter (85.56 in the acceptance fixture) intentionally does
  **not** become a third lane: the objective asks for two bars, and `total`
  already exists as the Cursor card's plan meter.
- Lane `label` is only added to the two Cursor lanes, which keeps the
  "no other provider changed" guarantee exact.

## Sources used

- No `AGENTMAP.md` in the repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools are not exposed in this session, so the
  code pointer could not be used (same as the prior Cursor tasks).
- Direct reads (read tool): `app.py` (`PACE_WINDOW_SPECS`, `build_pace_payload`,
  `compute_pace_lane`, `compute_monthly_window_minutes`, `probe_cursor_usage`,
  `_cursor_percent_window`, `_PROVIDER_LIMIT_WINDOWS`), `static/index.html`
  (Quota-pace block: `PACE_COLORS`, `renderPaceColumn`, `renderPaceSvg`),
  `tests/test_cursor_provider.py`, `tests/test_limits_api.py`,
  `tests/test_app.py`, `README.md`, and
  `docs/tasks/TASK-usage-board-cursor-models/progress.md`.
- Shell discovery: `git log/status/remote`, `grep` for cursor/pace wiring,
  `node --check` on the extracted inline dashboard script.
- Baseline capture: ran the current `build_pace_payload` on a seven-provider
  fixture **before** the change and pinned the resulting zai/commandcode/kimi/
  opencode-go lanes in `tests/test_pace_api.py` (`BASELINE_LANES`).
- Screenshot: Playwright (chromium-1140) + a local static server with mock
  `/api/summary` and `/api/pace` responses; the harness also asserts the two
  Cursor dot fills from the live DOM.
