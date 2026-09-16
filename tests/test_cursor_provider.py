"""Tests for the Cursor provider card (plan usage by session token).

No network access: the DashboardUsage fixture is parsed directly and the probe
is exercised with a mocked ``http_request``. Covers the three card metrics
(total %, Cursor-model %, other-model %), the missing-token negative and the
expired-session (401) negative — the board must keep serving other cards.
"""

import json
from unittest.mock import patch

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
