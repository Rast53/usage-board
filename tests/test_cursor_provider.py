"""Tests for the Cursor provider card (plan usage by session token).

No network access: the DashboardUsage fixture is parsed directly and the probe
is exercised with a mocked ``http_request``. Covers the three card metrics
(total %, Cursor-model %, other-model %), the missing-token negative and the
expired-session (401) negative — the board must keep serving other cards.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app as app_module

# Live-shaped Connect-RPC response for
# POST api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage.
# Percentages are already percent units; money fields are USD cents.
DASHBOARD_USAGE = {
    "billingCycleStart": "1776672371000",
    "billingCycleEnd": "1779264371000",
    "planUsage": {
        "totalSpend": 1529,
        "includedSpend": 1529,
        "bonusSpend": 0,
        "remaining": 471,
        "limit": 2000,
        "autoPercentUsed": 13.20952380952381,
        "apiPercentUsed": 3.155555555555556,
        "totalPercentUsed": 10.193333333333333,
    },
    "spendLimitUsage": {
        "totalSpend": 0,
        "pooledLimit": 50000,
        "individualLimit": 10000,
        "limitType": "user",
    },
    "displayThreshold": 200,
    "enabled": True,
    "displayMessage": "You've used 46% of your usage limit",
}

# GET cursor.com/api/usage-summary (cookie auth) — Enterprise / REST shape.
USAGE_SUMMARY = {
    "billingCycleStart": "2024-05-01T00:00:00.000Z",
    "billingCycleEnd": "2024-06-01T00:00:00.000Z",
    "membershipType": "pro",
    "limitType": "user",
    "individualUsage": {
        "plan": {
            "enabled": True,
            "used": 1529,
            "limit": 2000,
            "remaining": 471,
            "totalPercentUsed": 10.1933,
            "autoPercentUsed": 13.2095,
            "apiPercentUsed": 3.1555,
        }
    },
}


# Deliberately low-entropy placeholders: a real session token is a secret and
# only ever comes from the environment (never from source or fixtures).
FAKE_SESSION_TOKEN = "user-123::unit-test-token"
FAKE_COOKIE_HEADER = "WorkosCursorSessionToken=" + FAKE_SESSION_TOKEN + "; other=1"


# Cursor dashboard "Export" CSV (strategy=tokens): one token row per request.
# Header names mirror the live export; the parser resolves them by name because
# Cursor adds columns over time.
EXPORT_CSV = (
    "Date,Model,Input (w/o Cache Write),Input (w/ Cache Write),Cache Read,Output Tokens,Total Tokens,Cost\n"
    "2026-05-01T10:00:00.000Z,composer-2.5-fast,1000,500,200,300,2000,0.50\n"
    "2026-05-01T11:00:00.000Z,composer-2.5-fast,500,100,100,200,900,0.20\n"
    "2026-05-01T12:00:00.000Z,claude-4.6-sonnet,2000,0,400,600,3000,1.00\n"
    "2026-05-01T13:00:00.000Z,gpt-5.3-codex,700,0,50,50,800,0.10\n"
)

# A broken cell and an outright garbage line must not sink the whole export.
EXPORT_CSV_NOISY = (
    "Date,Model,Total Tokens,Output Tokens\n"
    "2026-05-01T10:00:00.000Z,composer-2.5-fast,2000,300\n"
    "this is a garbage row\n"
    "2026-05-01T11:00:00.000Z,claude-4.6-sonnet,,600\n"
    ",,not-a-number,\n"
    "2026-05-01T13:00:00.000Z,composer-2.5-fast,1000,oops\n"
)


def _client() -> TestClient:
    return TestClient(app_module.app)


def _wallet_from_probe() -> dict:
    parsed = app_module.parse_cursor_dashboard_usage(DASHBOARD_USAGE)
    reset = parsed["billing_cycle_end"]
    from_probe = {
        "provider": "cursor",
        "ok": True,
        "status": "active",
        "plan_label": "Pro",
        "total": app_module._cursor_percent_window(
            "total", "план", parsed["total_percent"], reset
        ),
        "cursor_models": app_module._cursor_percent_window(
            "cursor_models", "Cursor-модели", parsed["cursor_models_percent"], reset
        ),
        "other_models": app_module._cursor_percent_window(
            "other_models", "другие модели", parsed["other_models_percent"], reset
        ),
        "billing_cycle_start": parsed["billing_cycle_start"],
        "billing_cycle_end": reset,
        "remaining_summary": "Pro",
        "error": None,
        "probed_at": "2026-04-20T08:06:11Z",
        "source": "cursor-connect",
    }
    return app_module.build_cursor_wallet(from_probe)


# --- Registry / parser ------------------------------------------------------


def test_cursor_registered_aligned_with_registry() -> None:
    assert "cursor" in app_module.KNOWN_PROVIDERS
    assert dict(app_module._PROVIDER_KEY_GETTERS)["cursor"] is (
        app_module.get_cursor_session_token
    )
    assert [spec[0] for spec in app_module._PROVIDER_PROBE_SPECS] == list(
        app_module.KNOWN_PROVIDERS
    )
    assert "cursor" in app_module._wallet_builders()


def test_parse_dashboard_usage_metrics() -> None:
    parsed = app_module.parse_cursor_dashboard_usage(DASHBOARD_USAGE)
    assert parsed["enabled"] is True
    assert parsed["total_percent"] == 10.19
    assert parsed["cursor_models_percent"] == 13.21
    assert parsed["other_models_percent"] == 3.16
    assert parsed["limit_cents"] == 2000
    assert parsed["total_spend_cents"] == 1529
    assert parsed["remaining_cents"] == 471
    assert parsed["billing_cycle_end"] == "2026-05-20T08:06:11Z"


def test_parse_total_percent_falls_back_to_cents() -> None:
    parsed = app_module.parse_cursor_dashboard_usage(
        {"planUsage": {"limit": 2000, "totalSpend": 1000, "autoPercentUsed": 5.0}}
    )
    assert parsed["total_percent"] == 50.0
    assert parsed["cursor_models_percent"] == 5.0
    assert parsed["other_models_percent"] is None


def test_parse_total_percent_from_remaining() -> None:
    parsed = app_module.parse_cursor_dashboard_usage(
        {"planUsage": {"limit": 2000, "remaining": 1500}}
    )
    assert parsed["total_percent"] == 25.0


def test_parse_rest_usage_summary_shape() -> None:
    parsed = app_module.parse_cursor_dashboard_usage(USAGE_SUMMARY)
    assert parsed["total_percent"] == 10.19
    assert parsed["cursor_models_percent"] == 13.21
    assert parsed["other_models_percent"] == 3.16
    assert parsed["total_spend_cents"] == 1529
    assert parsed["plan_label"] == "pro"
    assert parsed["billing_cycle_start"] == "2024-05-01T00:00:00Z"


def test_parse_accepts_wrapped_usage_envelope() -> None:
    parsed = app_module.parse_cursor_dashboard_usage({"usage": DASHBOARD_USAGE})
    assert parsed["total_percent"] == 10.19
    assert parsed["cursor_models_percent"] == 13.21


def test_parse_disabled_account() -> None:
    parsed = app_module.parse_cursor_dashboard_usage({"enabled": False})
    assert parsed["enabled"] is False
    assert parsed["total_percent"] is None


# --- Probe (mocked HTTP) ----------------------------------------------------


def test_probe_ok_maps_three_metrics(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", "user_123::eyJhbGciOi.test.jwt")
    with patch.object(
        app_module,
        "http_request",
        return_value=(200, {}, json.dumps(DASHBOARD_USAGE).encode(), None),
    ):
        probe = app_module.probe_cursor_usage()

    assert probe["ok"] is True
    assert probe["status"] == "active"
    assert probe["total"]["used_percent"] == 10.19
    assert probe["total"]["remaining_percent"] == 89.81
    assert probe["cursor_models"]["used_percent"] == 13.21
    assert probe["other_models"]["used_percent"] == 3.16
    assert "Cursor" in probe["remaining_summary"]

    wallet = app_module.build_cursor_wallet(probe)
    assert wallet["provider"] == "cursor"
    assert wallet["kind"] == "cursor-usage"
    assert wallet["total"]["used_percent"] == 10.19
    assert wallet["cursor_models"]["used_percent"] == 13.21
    assert wallet["other_models"]["used_percent"] == 3.16


def test_probe_missing_token_is_manual(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    probe = app_module.probe_cursor_usage()
    assert probe["ok"] is False
    assert probe["status"] == "manual"
    assert "CURSOR_SESSION_TOKEN" in probe["error"]


def test_probe_401_marks_token_expired(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", "user_123::expired.jwt")
    with patch.object(
        app_module,
        "http_request",
        return_value=(401, {}, b'{"error":"unauthorized"}', "401"),
    ):
        probe = app_module.probe_cursor_usage()

    assert probe["ok"] is False
    assert probe["status"] == "expired"
    assert "истёк" in probe["error"]
    assert "(HTTP 401)" in probe["error"]

    wallet = app_module.build_cursor_wallet(probe)
    assert wallet["ok"] is False
    assert wallet["status"] == "expired"
    assert "истёк" in wallet["error"]


def test_cursor_token_alias(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("CURSOR_TOKEN", FAKE_SESSION_TOKEN)
    assert app_module.get_cursor_session_token() == FAKE_SESSION_TOKEN


def test_cursor_auth_accepts_full_cookie_header() -> None:
    headers = app_module._cursor_auth_headers(FAKE_COOKIE_HEADER, json_body=False)
    assert headers["Cookie"] == FAKE_COOKIE_HEADER
    # Bearer carries only the token half, never the whole cookie header.
    assert headers["Authorization"] == "Bearer unit-test-token"
    assert headers["Origin"] == "https://cursor.com"


def test_probe_accepts_full_cookie_header(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_COOKIE_HEADER)
    with patch.object(
        app_module,
        "http_request",
        return_value=(200, {}, json.dumps(DASHBOARD_USAGE).encode(), None),
    ) as req:
        probe = app_module.probe_cursor_usage()

    assert probe["ok"] is True
    sent = req.call_args.kwargs["headers"]
    assert sent["Cookie"] == FAKE_COOKIE_HEADER
    assert sent["Authorization"] == "Bearer unit-test-token"


def test_probe_401_survives_second_endpoint_transport_error(monkeypatch) -> None:
    """A 401 on the Connect RPC must not be masked by a REST fallback outage."""
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_SESSION_TOKEN)
    responses = [
        (401, {}, b'{"error":"unauthorized"}', "401"),
        (None, {}, b"", "connection refused"),
    ]
    with patch.object(app_module, "http_request", side_effect=responses):
        probe = app_module.probe_cursor_usage()

    assert probe["ok"] is False
    assert probe["status"] == "expired"
    assert "истёк" in probe["error"]


# --- API: positive / negative ----------------------------------------------


def test_cursor_visible_with_token_in_usage_and_limits(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", "user_123::eyJhbGciOi.test.jwt")
    monkeypatch.delenv("PROVIDERS", raising=False)
    wallet = _wallet_from_probe()
    state = {
        "updated_at": "2026-04-20T08:06:11Z",
        "providers": {},
        "accounts": [],
        "wallets": {"cursor": wallet},
        "errors": [],
    }
    with patch.object(app_module, "_state", state):
        usage = _client().get("/api/usage")
        limits = _client().get("/api/limits")

    assert usage.status_code == 200
    body = usage.json()
    assert "cursor" in body["wallets"]
    assert body["wallets"]["cursor"]["total"]["used_percent"] == 10.19

    assert limits.status_code == 200
    entry = limits.json()["providers"]["cursor"]
    assert entry["configured"] is True
    assert entry["ok"] is True
    assert entry["kind"] == "cursor-usage"
    assert {limit["id"] for limit in entry["limits"]} == {
        "total",
        "cursor_models",
        "other_models",
    }
    total = next(limit for limit in entry["limits"] if limit["id"] == "total")
    assert total["unit"] == "percent"
    assert total["limit"] == 100.0
    assert total["used_percent"] == 10.19


def test_cursor_hidden_without_token(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("PROVIDERS", raising=False)
    with patch.object(app_module, "_state", {
        "updated_at": None,
        "providers": {
            "wallets": {
                "label": "Wallets",
                "kind": "wallets",
                "keys": [],
                "quota_probe_updated_at": None,
            }
        },
        "accounts": [],
        "wallets": {},
        "errors": [],
    }):
        body = _client().get("/api/usage").json()
        limits = _client().get("/api/limits").json()

    # No cursor card/block at all...
    assert "cursor" not in body["wallets"]
    assert body["providers"]["wallets"]["keys"] == []
    # ...but the provider stays in the stable id list as disabled.
    assert "cursor" in body["enabled_providers"]
    assert limits["providers"]["cursor"]["configured"] is False
    assert limits["providers"]["cursor"]["status"] == "disabled"
    assert limits["providers"]["cursor"]["limits"] == []


def test_cursor_absent_without_token_other_wallets_unchanged(monkeypatch) -> None:
    """Negative: a stale cursor wallet is filtered out; others are untouched."""
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test-key")
    other_wallet = {
        "provider": "deepseek",
        "kind": "wallet-balance",
        "status": "active",
        "ok": True,
        "balance": [{"currency": "CNY", "total_balance": 42.0}],
        "remaining_summary": "¥42",
    }
    state = {
        "updated_at": "2026-04-20T08:06:11Z",
        "providers": {},
        "accounts": [],
        "wallets": {"cursor": _wallet_from_probe(), "deepseek": other_wallet},
        "errors": [],
    }
    with patch.object(app_module, "_state", state):
        body = _client().get("/api/usage").json()

    assert "cursor" not in body["wallets"]
    assert body["wallets"] == {"deepseek": other_wallet}


def test_collect_state_with_mocked_cursor_probe(monkeypatch) -> None:
    """Full pipeline: probe -> wallet -> /api/usage shows the cursor block."""
    monkeypatch.setenv("PROVIDERS", "cursor")
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", "user_123::eyJhbGciOi.test.jwt")
    monkeypatch.setattr(app_module, "_quota_cache", {"updated_at": None, "accounts": {}})
    monkeypatch.setattr(app_module, "save_json", lambda *a, **k: None)
    monkeypatch.setattr(
        app_module, "maybe_export_openrouter_key_models", lambda *a, **k: None
    )
    with patch.object(
        app_module,
        "http_request",
        return_value=(200, {}, json.dumps(DASHBOARD_USAGE).encode(), None),
    ):
        state = app_module.collect_state(force_quota=True)

    assert state["wallets"]["cursor"]["ok"] is True
    assert state["wallets"]["cursor"]["total"]["used_percent"] == 10.19

    with patch.object(app_module, "_state", state):
        body = _client().get("/api/usage").json()
    assert "cursor" in body["wallets"]
    assert body["wallets"]["cursor"]["cursor_models"]["used_percent"] == 13.21


def test_cursor_401_does_not_break_board(monkeypatch) -> None:
    """Negative: with an expired Cursor token the board still serves everything."""
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", "user_123::expired.jwt")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test-key")
    with patch.object(
        app_module,
        "http_request",
        return_value=(401, {}, b"", "401"),
    ):
        probe = app_module.probe_cursor_usage()
    wallet = app_module.build_cursor_wallet(probe)
    other_wallet = {
        "provider": "deepseek",
        "kind": "wallet-balance",
        "status": "active",
        "ok": True,
        "balance": [{"currency": "CNY", "total_balance": 42.0}],
        "remaining_summary": "¥42",
    }
    state = {
        "updated_at": "2026-04-20T08:06:11Z",
        "providers": {},
        "accounts": [],
        "wallets": {"cursor": wallet, "deepseek": other_wallet},
        "errors": [],
    }
    with patch.object(app_module, "_state", state):
        usage = _client().get("/api/usage")
        limits = _client().get("/api/limits")

    assert usage.status_code == 200
    body = usage.json()
    assert body["wallets"]["cursor"]["status"] == "expired"
    assert body["wallets"]["deepseek"] == other_wallet

    assert limits.status_code == 200
    entry = limits.json()["providers"]["cursor"]
    assert entry["status"] == "expired"
    assert entry["ok"] is False
    assert "истёк" in entry["error"]
    assert any("истёк" in err for err in limits.json()["errors"])


# --- Per-model breakdown: CSV aggregator ------------------------------------


def test_aggregate_cursor_csv_sums_total_tokens_and_sorts_desc() -> None:
    models = app_module.aggregate_cursor_csv_models(EXPORT_CSV)
    assert models["available"] is True
    assert models["source"] == "cursor-export-csv"
    items = models["items"]
    assert [it["model"] for it in items] == [
        "claude-4.6-sonnet",
        "composer-2.5-fast",
        "gpt-5.3-codex",
    ]
    assert [it["total_tokens"] for it in items] == [3000, 2900, 800]
    assert models["totals"]["total_tokens"] == 6700
    # The component columns ride along for the UI / agents.
    composer = next(it for it in items if it["model"] == "composer-2.5-fast")
    assert composer["input_tokens"] == 1500
    assert composer["cache_write_tokens"] == 600
    assert composer["cache_read_tokens"] == 300
    assert composer["output_tokens"] == 500


def test_aggregate_cursor_csv_tolerates_empty_and_broken_cells() -> None:
    models = app_module.aggregate_cursor_csv_models(EXPORT_CSV_NOISY)
    assert models["available"] is True
    by_model = {it["model"]: it["total_tokens"] for it in models["items"]}
    # composer keeps both numeric rows; the sonnet row's broken Total Tokens
    # falls back to its Output Tokens cell; the garbage rows are discarded.
    assert by_model == {"composer-2.5-fast": 3000, "claude-4.6-sonnet": 600}


def test_aggregate_cursor_csv_accepts_snake_case_headers() -> None:
    models = app_module.aggregate_cursor_csv_models(
        "model,total_tokens\ncomposer-2.5-fast,42\n"
    )
    assert models["available"] is True
    assert models["items"] == [
        {
            "model": "composer-2.5-fast",
            "total_tokens": 42,
            "input_tokens": 0,
            "cache_write_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
        }
    ]


def test_aggregate_cursor_csv_empty_or_unknown_is_unavailable() -> None:
    assert app_module.aggregate_cursor_csv_models("")["available"] is False
    assert app_module.aggregate_cursor_csv_models("nope\n1,2\n")["available"] is False


# --- Per-model breakdown: export URL / window -------------------------------


def test_cursor_export_url_uses_window_and_tokens_strategy() -> None:
    url = app_module.cursor_export_url(1_776_672_371_000, 1_779_264_371_000)
    parsed = urlparse(url)
    assert parsed.path == "/api/dashboard/export-usage-events-csv"
    query = parse_qs(parsed.query)
    assert query["startDate"] == ["1776672371000"]
    assert query["endDate"] == ["1779264371000"]
    assert query["strategy"] == ["tokens"]


def test_probe_export_uses_windowed_url_not_full_export(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_SESSION_TOKEN)
    responses = [
        (200, {}, json.dumps(DASHBOARD_USAGE).encode(), None),
        (200, {}, EXPORT_CSV.encode(), None),
    ]
    with patch.object(app_module, "http_request", side_effect=responses) as req:
        probe = app_module.probe_cursor_usage()

    assert probe["ok"] is True
    assert req.call_count == 2
    export_url = req.call_args_list[-1].args[0]
    query = parse_qs(urlparse(export_url).query)
    assert query["startDate"] == ["1776672371000"]
    assert query["endDate"] == ["1779264371000"]
    assert query["strategy"] == ["tokens"]
    assert probe["models"]["available"] is True
    assert probe["models"]["source"] == "cursor-export-csv"
    assert probe["models"]["items"][0]["model"] == "claude-4.6-sonnet"


def test_probe_without_cycle_window_skips_export(monkeypatch) -> None:
    """No billing window -> no export request (and never a full-history one)."""
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_SESSION_TOKEN)
    no_window = {
        key: value
        for key, value in DASHBOARD_USAGE.items()
        if key not in ("billingCycleStart", "billingCycleEnd")
    }
    with patch.object(
        app_module,
        "http_request",
        return_value=(200, {}, json.dumps(no_window).encode(), None),
    ) as req:
        probe = app_module.probe_cursor_usage()

    assert probe["ok"] is True
    assert req.call_count == 1  # plan usage only
    assert probe["models"]["available"] is False
    assert probe["models"]["reason"]


# --- Per-model breakdown: wallet success / failure --------------------------


def test_wallet_export_success_exposes_models(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_SESSION_TOKEN)
    responses = [
        (200, {}, json.dumps(DASHBOARD_USAGE).encode(), None),
        (200, {}, EXPORT_CSV.encode(), None),
    ]
    with patch.object(app_module, "http_request", side_effect=responses):
        wallet = app_module.build_cursor_wallet(app_module.probe_cursor_usage())

    assert wallet["models"]["available"] is True
    assert wallet["models"]["source"] == "cursor-export-csv"
    assert len(wallet["models"]["items"]) >= 1
    assert wallet["total"]["used_percent"] == 10.19


def test_wallet_export_failure_keeps_other_fields(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_SESSION_TOKEN)
    monkeypatch.setattr(app_module, "now_iso", lambda: "2026-09-17T00:00:00Z")
    plan = (200, {}, json.dumps(DASHBOARD_USAGE).encode(), None)
    with patch.object(
        app_module, "http_request", side_effect=[plan, (200, {}, EXPORT_CSV.encode(), None)]
    ):
        good = app_module.build_cursor_wallet(app_module.probe_cursor_usage())
    with patch.object(
        app_module, "http_request", side_effect=[plan, (None, {}, b"", "timed out")]
    ):
        bad = app_module.build_cursor_wallet(app_module.probe_cursor_usage())

    assert good["models"]["available"] is True
    assert bad["models"]["available"] is False
    assert bad["models"]["reason"]
    # Export failure must only change ``models`` — the rest is byte-identical.
    for key, value in good.items():
        if key == "models":
            continue
        assert bad[key] == value, key


def test_limits_keep_cursor_limits_on_export_failure(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_SESSION_TOKEN", FAKE_SESSION_TOKEN)
    monkeypatch.delenv("PROVIDERS", raising=False)
    plan = (200, {}, json.dumps(DASHBOARD_USAGE).encode(), None)
    with patch.object(
        app_module, "http_request", side_effect=[plan, (None, {}, b"", "timeout")]
    ):
        wallet = app_module.build_cursor_wallet(app_module.probe_cursor_usage())

    assert wallet["models"]["available"] is False
    state = {
        "updated_at": "2026-04-20T08:06:11Z",
        "providers": {},
        "accounts": [],
        "wallets": {"cursor": wallet},
        "errors": [],
    }
    with patch.object(app_module, "_state", state):
        limits = _client().get("/api/limits")

    assert limits.status_code == 200
    entry = limits.json()["providers"]["cursor"]
    assert entry["ok"] is True
    assert entry["kind"] == "cursor-usage"
    assert {limit["id"] for limit in entry["limits"]} == {
        "total",
        "cursor_models",
        "other_models",
    }


# --- Negative: no token -> no CSV request -----------------------------------


def test_probe_without_token_makes_no_http_calls(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("CURSOR_TOKEN", raising=False)
    with patch.object(app_module, "http_request") as req:
        probe = app_module.probe_cursor_usage()

    assert req.call_count == 0
    assert probe["status"] == "manual"
    assert "models" not in probe  # card stays exactly as before the task


# --- Static: the inline dashboard script parses under node ------------------


def test_static_inline_script_passes_node_check() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    html = (
        Path(app_module.__file__).resolve().parent / "static" / "index.html"
    ).read_text(encoding="utf-8")
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(script)
        proc = subprocess.run(
            [node, "--check", path], capture_output=True, text=True
        )
    finally:
        os.unlink(path)
    assert proc.returncode == 0, proc.stderr
