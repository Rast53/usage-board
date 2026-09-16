# TASK-usage-board-cursor-card — progress

## Status

Add a **Cursor** card to `Rast53/usage-board` driven by the dashboard usage
session token (`CURSOR_SESSION_TOKEN`), with three metrics — plan total %,
Cursor-model % and other-model % — plus tests, docs and a PR. No deploy.

## Done (this branch)

- `app.py`: new `cursor` provider.
  - `get_cursor_session_token()` reads `CURSOR_SESSION_TOKEN` (alias
    `CURSOR_TOKEN`): a `WorkosCursorSessionToken` = `<userId>::<accessToken>`
    cookie value, a bare access token, or a full `Cookie:` header.
    `CURSOR_PROXY` / `CURSOR_BASE_URL` optional.
  - `_cursor_auth_headers()` passes a full `Cookie:` header through verbatim
    (and still derives the Bearer JWT from its `WorkosCursorSessionToken`
    value); a bare token is wrapped in the cookie as before.
  - `parse_cursor_dashboard_usage()` normalizes the undocumented Cursor
    DashboardUsage payload: `planUsage.totalPercentUsed` (total),
    `autoPercentUsed` (Cursor models) and `apiPercentUsed` (other models),
    with an `used/limit` fallback and support for the REST
    `individualUsage.plan` shape. Percentages already arrive in percent units;
    money stays in cents.
  - `probe_cursor_usage()` calls the Connect RPC
    `POST api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage`
    (Bearer + session cookie) and falls back to
    `GET cursor.com/api/usage-summary` (cookie). A 401/403 sets
    `status: "expired"` and the Russian error `«токен истёк»`; the probe never
    raises, so the poller/board keep serving other providers.
  - `build_cursor_wallet()` exposes `total` / `cursor_models` / `other_models`
    percent windows (100 % cap, reset from the billing cycle) and marks model
    breakdown/USD history unavailable.
  - Registered in `KNOWN_PROVIDERS`, `_PROVIDER_PROBE_SPECS`,
    `_PROVIDER_KEY_GETTERS`, `_PROVIDER_NOTES`, `_wallet_builders`,
    `_PROVIDER_LABELS` and `_PROVIDER_LIMIT_WINDOWS` (so `/api/limits` reports
    the three percent limits).
- `static/index.html`: `.pcard.prov-cursor` style, `classify`, `heroFor`,
  `renderCursorCard` (three percent bars + cycle/usage details), labels and
  card order/renderer wiring.
- `tests/test_cursor_provider.py`: 19 tests — registry invariants, DashboardUsage
  parsing (+ cents fallback, REST shape, wrapper envelope, disabled account),
  mocked 200 probe, mocked 401 → expired, `401` surviving a fallback endpoint
  transport error, missing token → manual, the `CURSOR_TOKEN` alias,
  full-`Cookie:`-header pass-through (headers + probe path), `/api/usage`
  positive with `CURSOR_SESSION_TOKEN`, negative without token (no cursor block,
  other wallets byte-identical), expired-token board survival, and the full
  `collect_state` pipeline.
- `.env.example` / `README.md`: `CURSOR_SESSION_TOKEN`, `CURSOR_PROXY`,
  `CURSOR_BASE_URL`, provider row and the `/api/limits` stable-id list.

## Acceptance self-check (agent)

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_cursor_provider.py` green: fixture → total % / cursor models % / other models % | 19 passed (fixture 10.19 / 13.21 / 3.16) |
| 2 | With `CURSOR_SESSION_TOKEN` the card is visible and `/api/usage` has a `cursor` block with non-zero metrics | covered by mocked-200 probe + `collect_state` pipeline test; live curl is the post-merge operator step |
| 3 | Without `CURSOR_SESSION_TOKEN` no `cursor` block; other wallets unchanged | `test_cursor_hidden_without_token`, `test_cursor_absent_without_token_other_wallets_unchanged` |
| 4 | 401 from Cursor → «токен истёк», board does not fall over | `test_probe_401_marks_token_expired`, `test_probe_401_survives_second_endpoint_transport_error`, `test_cursor_401_does_not_break_board` (usage + limits both 200) |

Full suite: `33 passed` (14 pre-existing + 19 new). No deploy performed.

## Notes / deviations

- The Cursor API is **undocumented** and may change; treat the card as
  best-effort. The probe sends both Bearer and cookie auth so either token form
  works, and tries the Connect RPC before the REST summary fallback.
- `autoPercentUsed` / `apiPercentUsed` are independent meters, not disjoint
  shares of the total — the UI shows all three without summing them.
- No network call was made in tests; a valid live token is only exercised by the
  operator after merge (rules forbid deploy/secret handling here).

## Sources used

- No `AGENTMAP.md` in the repo root and no `.gbrain-source`; the gbrain MCP
  `code_def` / `code_callers` tools are not exposed in this session, so the code
  pointer could not be used.
- Direct reads (read tool): `app.py` (provider registry, probe/wallet builders,
  `collect_state`, `_provider_limits`, `build_limits_payload`), `tests/test_app.py`,
  `tests/test_limits_api.py`, `README.md`, `.env.example`, `static/index.html`,
  `docs/tasks/TASK-usage-board-*/progress.md`.
- Shell discovery: `git log/status/remote`, `grep` for provider wiring.
- Cursor API contract (web, reverse-engineered/undocumented): OpenUsage
  `docs/providers/cursor.md` and `CursorUsageMapper.swift`
  (https://github.com/robinebers/openusage), ClearMeasureLabs Cursor-Usage-Status
  `usageClient.ts` (https://github.com/ClearMeasureLabs/Cursor-Usage-Status),
  agent-walker `docs/cursor.md`
  (https://github.com/miiiiiiich/agent-walker).
- Follow-up run additionally cross-checked the `usage-summary` shape against
  siropkin/budi's
  [ADR-0090](https://github.com/siropkin/budi/wiki/Cursor-Usage-API-Contract),
  ai-usagebar's
  [`cursor/types.rs`](https://docs.rs/ai-usagebar/1.10.0/src/ai_usagebar/cursor/types.rs.html),
  and steipete/CodexBar's
  [`docs/cursor.md`](https://github.com/steipete/CodexBar/blob/9e6557cc/docs/cursor.md)
  (cookie name / endpoint / server-side expectations).

## Provenance note

`git ls-remote origin` showed the same-named branch
`dsh/TASK-usage-board-cursor-card` (and PR #3) already on the remote for this
exact task. It was fetched, reviewed line by line (read-only provider, no
secrets, no new dependencies) and used as the authoritative interface so the
card layout and `parse_cursor_dashboard_usage` / `probe_cursor_usage` /
`build_cursor_wallet` signatures stay stable; the applied diff was then
re-validated locally (`pytest` 29 passed) before committing on a fresh set of
logical commits.

**2026-04-20 follow-up run.** The remote branch/PR #3 above was re-fetched and
re-validated (29 passed) rather than re-implemented in parallel. Matching the
canonical code surfaced two real gaps:

1. A token pasted as a full `Cookie:` header (as DevTools copies it) was blindly
   wrapped into a second `WorkosCursorSessionToken=` and the Bearer half was
   taken from the whole header. Fixed with `_cursor_cookie_parts()`
   pass-through, plus the `CURSOR_TOKEN` alias.
2. `_cursor_fetch_usage()` returned the *last* endpoint's result, so a `401`
   from the Connect RPC was masked by a transport error on the hardcoded REST
   fallback, and the card showed a generic error instead of «токен истёк». It
   now remembers a definitive 401/403 across candidates.

Four tests were added (`test_cursor_token_alias`,
`test_cursor_auth_accepts_full_cookie_header`,
`test_probe_accepts_full_cookie_header`,
`test_probe_401_survives_second_endpoint_transport_error`); the full suite is
now `33 passed`.
