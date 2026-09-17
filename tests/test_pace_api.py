"""Tests for the quota-pace payload (``/api/pace``) — with a Cursor focus.

Cursor has no 5h/weekly windows: its dashboard exposes two meters that burn
down over the same billing cycle (Cursor-model % and other-model %). The pace
payload must surface both as labelled ``monthly`` lanes for the ``cursor-main``
account, while every other provider's lanes stay byte-identical and
deepseek/openrouter stay in ``no_window``.

No network access: the payload is built from a static ``quota_cache`` fixture.
"""

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app as app_module

CURSOR_RESET = "2026-09-25T12:27:11Z"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _window(
    used_percent: float,
    reset_at: str = CURSOR_RESET,
    cap: float = 100.0,
) -> dict:
    return {
        "kind": "test-window",
        "used_percent": used_percent,
        "remaining_percent": round(100.0 - used_percent, 2),
        "cap": cap,
        "next_reset_at": reset_at,
        "summary": f"{used_percent}% used",
    }


def _quota_cache() -> dict:
    """All seven providers, with Cursor carrying its two monthly meters."""
    return {
        "updated_at": "2026-09-17T11:53:00Z",
        "accounts": {
            "zai-main": {
                "probed_at": "2026-09-17T11:59:00Z",
                "session": _window(10.0, "2026-09-17T15:00:00Z"),
                "weekly": _window(20.0),
                "mcp": {"used": 3, "limit": 100},
            },
            "commandcode-main": {
                "probed_at": "2026-09-17T11:58:00Z",
                "session": _window(30.0, "2026-09-17T16:00:00Z"),
                "weekly": _window(40.0),
                "monthly": _window(50.0),
            },
            "kimi-main": {
                "probed_at": "2026-09-17T11:57:00Z",
                "session": _window(15.0, "2026-09-17T16:00:00Z"),
                "weekly": _window(25.0),
            },
            "opencode-go-main": {
                "probed_at": "2026-09-17T11:56:00Z",
                "session": _window(5.0, "2026-09-17T16:00:00Z"),
                "weekly": _window(35.0),
                "monthly": _window(45.0),
            },
            "deepseek-main": {
                "probed_at": "2026-09-17T11:55:00Z",
                "balance": [{"currency": "USD", "total_balance": 5.0}],
            },
            "openrouter-main": {
                "probed_at": "2026-09-17T11:54:00Z",
                "total_credits": 10.0,
                "total_usage": 2.0,
            },
            "cursor-main": {
                "provider": "cursor",
                "email": "cursor-main",
                "probed_at": "2026-09-17T11:53:00Z",
                "ok": True,
                "status": "active",
                "total": _window(85.56),
                "cursor_models": _window(86.7),
                "other_models": _window(74.18),
            },
        },
    }


# Lanes captured from the payload *before* the Cursor change. The Cursor work
# must not move any of these numbers or introduce a "label" on them.
BASELINE_LANES = {
    "zai-main": [
        {
            "window": "5h",
            "window_minutes": 300,
            "used_percent": 10,
            "norm_percent": 40,
            "delta_pp": -30,
            "pace": "ok",
            "cooldown_minutes": 0,
            "reset_at": "2026-09-17T15:00:00Z",
            "data_age_seconds": 60,
        },
        {
            "window": "weekly",
            "window_minutes": 10080,
            "used_percent": 20,
            "norm_percent": 0,
            "delta_pp": 20,
            "pace": "warn",
            "cooldown_minutes": 2016,
            "reset_at": "2026-09-25T12:27:11Z",
            "data_age_seconds": 60,
        },
    ],
    "commandcode-main": [
        {
            "window": "5h",
            "window_minutes": 300,
            "used_percent": 30,
            "norm_percent": 20,
            "delta_pp": 10,
            "pace": "warn",
            "cooldown_minutes": 30,
            "reset_at": "2026-09-17T16:00:00Z",
            "data_age_seconds": 120,
        },
        {
            "window": "weekly",
            "window_minutes": 10080,
            "used_percent": 40,
            "norm_percent": 0,
            "delta_pp": 40,
            "pace": "danger",
            "cooldown_minutes": 4032,
            "reset_at": "2026-09-25T12:27:11Z",
            "data_age_seconds": 120,
        },
        {
            "window": "monthly",
            "window_minutes": 44640,
            "used_percent": 50,
            "norm_percent": 74.1327,
            "delta_pp": -24.1327,
            "pace": "ok",
            "cooldown_minutes": 0,
            "reset_at": "2026-09-25T12:27:11Z",
            "data_age_seconds": 120,
        },
    ],
    "kimi-main": [
        {
            "window": "5h",
            "window_minutes": 300,
            "used_percent": 15,
            "norm_percent": 20,
            "delta_pp": -5,
            "pace": "ok",
            "cooldown_minutes": 0,
            "reset_at": "2026-09-17T16:00:00Z",
            "data_age_seconds": 180,
        },
        {
            "window": "weekly",
            "window_minutes": 10080,
            "used_percent": 25,
            "norm_percent": 0,
            "delta_pp": 25,
            "pace": "danger",
            "cooldown_minutes": 2520,
            "reset_at": "2026-09-25T12:27:11Z",
            "data_age_seconds": 180,
        },
    ],
    "opencode-go-main": [
        {
            "window": "5h",
            "window_minutes": 300,
            "used_percent": 5,
            "norm_percent": 20,
            "delta_pp": -15,
            "pace": "ok",
            "cooldown_minutes": 0,
            "reset_at": "2026-09-17T16:00:00Z",
            "data_age_seconds": 240,
        },
        {
            "window": "weekly",
            "window_minutes": 10080,
            "used_percent": 35,
            "norm_percent": 0,
            "delta_pp": 35,
            "pace": "danger",
            "cooldown_minutes": 3528,
            "reset_at": "2026-09-25T12:27:11Z",
            "data_age_seconds": 240,
        },
        {
            "window": "monthly",
            "window_minutes": 44640,
            "used_percent": 45,
            "norm_percent": 74.1327,
            "delta_pp": -29.1327,
            "pace": "ok",
            "cooldown_minutes": 0,
            "reset_at": "2026-09-25T12:27:11Z",
            "data_age_seconds": 240,
        },
    ],
}


def _account(payload: dict, provider: str) -> dict | None:
    for account in payload["accounts"]:
        if account.get("provider") == provider:
            return account
    return None


# --- Cursor: two labelled monthly lanes -------------------------------------


def test_cursor_gets_two_monthly_lanes_with_labels() -> None:
    payload = app_module.build_pace_payload(_quota_cache(), now=NOW)

    cursor = _account(payload, "cursor-main")
    assert cursor is not None, "cursor-main must be in accounts"
    assert "cursor-main" not in payload["no_window"]

    lanes = cursor["lanes"]
    assert len(lanes) == 2
    assert {lane["window"] for lane in lanes} == {"monthly"}

    by_label = {lane["label"]: lane for lane in lanes}
    assert set(by_label) == {"Cursor-модели", "другие модели"}

    cursor_models = by_label["Cursor-модели"]
    other_models = by_label["другие модели"]
    assert cursor_models["used_percent"] == 86.7
    assert other_models["used_percent"] == 74.18
    assert cursor_models["reset_at"] == CURSOR_RESET
    assert other_models["reset_at"] == CURSOR_RESET
    assert cursor_models["window_minutes"] == other_models["window_minutes"] == 44640
    # The plan "total" meter is a third dataset and must not become a lane.
    assert all(
        lane["used_percent"] != 85.56 for lane in lanes
    )


def test_cursor_lanes_do_not_leak_the_generic_window_sweep() -> None:
    """No 5h/weekly lanes and no label on anything but the two Cursor meters."""
    payload = app_module.build_pace_payload(_quota_cache(), now=NOW)
    cursor = _account(payload, "cursor-main")
    assert cursor is not None
    assert [lane["window"] for lane in cursor["lanes"]] == ["monthly", "monthly"]
    assert "5h" not in {lane["window"] for lane in cursor["lanes"]}


def test_cursor_simplified_fixture_uses_account_level_reset() -> None:
    """A hand-built cache may store bare percents plus one account reset."""
    cache = {
        "accounts": {
            "cursor-main": {
                "probed_at": "2026-09-17T11:53:00Z",
                "total": 85.56,
                "cursor_models": 86.7,
                "other_models": 74.18,
                "next_reset_at": CURSOR_RESET,
            }
        }
    }
    payload = app_module.build_pace_payload(cache, now=NOW)

    cursor = _account(payload, "cursor-main")
    assert cursor is not None
    assert "cursor-main" not in payload["no_window"]
    by_label = {lane["label"]: lane for lane in cursor["lanes"]}
    assert set(by_label) == {"Cursor-модели", "другие модели"}
    assert by_label["Cursor-модели"]["used_percent"] == 86.7
    assert by_label["другие модели"]["used_percent"] == 74.18
    assert all(lane["reset_at"] == CURSOR_RESET for lane in cursor["lanes"])


def test_cursor_without_meters_falls_back_to_no_window() -> None:
    cache = _quota_cache()
    cache["accounts"]["cursor-main"] = {
        "probed_at": "2026-09-17T11:53:00Z",
        "total": _window(85.56),
    }
    payload = app_module.build_pace_payload(cache, now=NOW)
    assert _account(payload, "cursor-main") is None
    assert "cursor-main" in payload["no_window"]


# --- Negative: every other provider is untouched ----------------------------


def test_non_cursor_lanes_match_pre_change_baseline() -> None:
    payload = app_module.build_pace_payload(_quota_cache(), now=NOW)

    for provider, expected in BASELINE_LANES.items():
        account = _account(payload, provider)
        assert account is not None, provider
        assert account["lanes"] == expected, provider
        for lane in account["lanes"]:
            assert "label" not in lane, provider

    assert payload["no_window"] == ["deepseek-main", "openrouter-main"]


def test_pace_payload_on_empty_cache() -> None:
    payload = app_module.build_pace_payload(None, now=NOW)
    assert payload["accounts"] == []
    assert payload["no_window"] == []


# --- Static: the rendered "месяц" column shows two Cursor dots --------------

MOCK_PACE = {
    "accounts": [
        {
            "provider": "cursor-main",
            "lanes": [
                {
                    "window": "monthly",
                    "window_minutes": 44640,
                    "used_percent": 86.7,
                    "norm_percent": 74.13,
                    "delta_pp": 12.57,
                    "pace": "warn",
                    "cooldown_minutes": 5610.06,
                    "reset_at": "2026-09-25T12:27:11Z",
                    "data_age_seconds": 60,
                    "label": "Cursor-модели",
                },
                {
                    "window": "monthly",
                    "window_minutes": 44640,
                    "used_percent": 74.18,
                    "norm_percent": 74.13,
                    "delta_pp": 0.05,
                    "pace": "ok",
                    "cooldown_minutes": 0,
                    "reset_at": "2026-09-25T12:27:11Z",
                    "data_age_seconds": 60,
                    "label": "другие модели",
                },
            ],
        }
    ],
    "no_window": [],
    "server_now": "2026-09-17T12:00:00Z",
}


def _extract_dashboard_script() -> str:
    html = (
        Path(app_module.__file__).resolve().parent / "static" / "index.html"
    ).read_text(encoding="utf-8")
    return html.split("<script>", 1)[1].split("</script>", 1)[0]


def test_monthly_column_renders_two_distinct_cursor_dots() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")

    script = _extract_dashboard_script()
    prelude = (
        "globalThis.document = {"
        " getElementById: function(){ return { innerHTML: '', textContent: '',"
        " style: {}, setAttribute: function(){}, getAttribute: function(){ return null; },"
        " querySelector: function(){ return null; }, querySelectorAll: function(){ return []; } }; },"
        " querySelector: function(){ return null; },"
        " querySelectorAll: function(){ return []; }"
        "};\n"
        "globalThis.fetch = function(){ return Promise.reject(new Error('offline')); };\n"
        "globalThis.setInterval = function(){ return 0; };\n"
        "globalThis.window = globalThis;\n"
    )
    harness = (
        ";(function(){\n"
        "  var data = " + json.dumps(MOCK_PACE, ensure_ascii=False) + ";\n"
        "  process.stdout.write(renderPacePanel(data));\n"
        "})();\n"
    )

    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prelude + script + harness)
        proc = subprocess.run(
            [node, path], capture_output=True, text=True, timeout=30
        )
    finally:
        os.unlink(path)

    assert proc.returncode == 0, proc.stderr
    html = proc.stdout

    # Only the monthly column has lanes, so exactly two dots are drawn and both
    # live after the "месяц" title.
    assert html.count("<circle") == 2
    assert html.index(">месяц<") < html.index("<circle")
    assert "Cursor-модели" in html
    assert "другие модели" in html
    # Two distinct, non-default fills keep the dots visually apart.
    assert "#22d3ee" in html
    assert "#f59e0b" in html
