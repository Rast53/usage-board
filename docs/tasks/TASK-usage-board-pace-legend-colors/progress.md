# TASK-usage-board-pace-legend-colors — progress

## Status

`/api/pace` now owns the legend. Each window (`5h`, `weekly`, `monthly`)
carries `resets[]` grouped to one row per provider. Multi-meter lanes are
labelled `kimi · всего`, `kimi · code`, `cursor · модели`, `cursor · другие`.
Single windows stay unlabeled; the client prints the provider name. Every lane
has a server `color` from `PACE_COLORS` / `pace_shade`. A z.ai 5h lane with a
known `used_percent` and no `reset_at` is drawn as `pace: "n/a"` and is omitted
from `resets[]` and from the norm-axis SVG. Kimi monthly meters render in the
card body (precise percent) as well as in the details rows. The collection
matrix is `docs/provider-windows-matrix.md`.

No deploy.

## Done

- `app.py`: `PACE_COLORS` for all seven `KNOWN_PROVIDERS`, `pace_shade`,
  `windows.<key>.resets`, meter labels, n/a lane when reset is missing.
- `static/index.html`: client reads `lane.color` and `windows.*.resets`;
  `PACE_LANE_COLORS` and the client palette are gone; null `norm_percent`
  draws no circle; pill text «сброс не сообщается»; Kimi `afterBars` shows
  «месяц (всего)» / «месяц (code)» with the unrounded percent before
  `.details-body`.
- Tests: `test_pace_resets_grouped_by_provider`,
  `test_pace_lane_labels_carry_provider`, `test_pace_unknown_reset_lane`,
  `tests/test_pace_colors.py`, `tests/test_ui_kimi_caption.py`,
  `tests/test_docs_matrix.py`.
- `docs/provider-windows-matrix.md` and a README link.

## `tests/test_pace_api.py` edits (baseline only, plus the new cases)

- `BASELINE_LANES`: added `color` on every lane (`#38bdf8` z.ai, `#fb923c`
  commandcode, `#f472b6` kimi, `#c084fc` opencode-go). Numeric fields unchanged.
- Single-window lanes still assert `"label" not in lane`.
- Cursor label expectations: `Cursor-модели` / `другие модели` →
  `cursor · модели` / `cursor · другие`.
- Kimi monthly label expectations: `месяц (всего)` / `месяц (code)` →
  `kimi · всего` / `kimi · code`.
- `MOCK_PACE`: those labels plus server `color` (base and `pace_shade`); the
  node render no longer expects `#f59e0b` or `PACE_LANE_COLORS`.
- Empty payload expects `windows.{5h,weekly,monthly}.resets == []`.
- New tests named in the task: `test_pace_resets_grouped_by_provider`,
  `test_pace_lane_labels_carry_provider`, `test_pace_unknown_reset_lane`.

`/api/limits` expectations were not edited. `pytest -q`: 94 passed, 2 skipped
(docker not available in this environment).

## Sources used

- No `AGENTMAP.md` at the repo root and no `.gbrain-source`.
- `code_def(KNOWN_PROVIDERS)`, `code_def(build_pace)`, `code_def(PACE_LANE_COLORS)`
  and `code_callers(build_pace_payload)` (source `raclaw-task-mcp`) all returned
  `permission_denied` (gbrain remote code reads suspended, garrytan/gbrain#5052).
  The pointer could not answer, so the symbols were read in the checkout:
  `app.py` `KNOWN_PROVIDERS`, `build_pace_payload`, `compute_pace_lane`,
  `PACE_CURSOR_WINDOW_SPECS`, `PACE_KIMI_MONTHLY_WINDOW_SPECS`;
  `static/index.html` `PACE_LANE_COLORS`, `renderPaceColumn`, `renderPaceSvg`,
  `renderKimiCard`.
