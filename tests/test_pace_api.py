"""Tests for the quota-pace payload (``/api/pace``) — with a Cursor focus.

Cursor has no 5h/weekly windows: its dashboard exposes two meters that burn
down over the same billing cycle (Cursor-model % and other-model %). The pace
payload must surface both as labelled ``monthly`` lanes for the ``cursor-main``
account. Numeric pace fields of the other providers stay on the captured
baseline; each lane also carries a server ``color``. deepseek/openrouter stay
in ``no_window``.

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
            "color": "#38bdf8",
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
            "color": "#38bdf8",
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
            "color": "#fb923c",
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
            "color": "#fb923c",
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
            "color": "#fb923c",
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
            "color": "#f472b6",
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
            "color": "#f472b6",
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
            "color": "#c084fc",
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
            "color": "#c084fc",
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
            "color": "#c084fc",
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
    assert set(by_label) == {"cursor · модели", "cursor · другие"}

    cursor_models = by_label["cursor · модели"]
    other_models = by_label["cursor · другие"]
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
    assert set(by_label) == {"cursor · модели", "cursor · другие"}
    assert by_label["cursor · модели"]["used_percent"] == 86.7
    assert by_label["cursor · другие"]["used_percent"] == 74.18
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


# --- Kimi: monthly meters are additive to its 5h/weekly lanes ---------------


def test_kimi_monthly_meters_add_lanes_without_moving_baseline() -> None:
    cache = _quota_cache()
    cache["accounts"]["kimi-main"]["monthly_total"] = _window(
        0.09, "2026-11-29T00:00:00Z"
    )
    cache["accounts"]["kimi-main"]["monthly_code"] = _window(
        0.09, "2026-11-29T00:00:00Z"
    )
    payload = app_module.build_pace_payload(cache, now=NOW)

    kimi = _account(payload, "kimi-main")
    assert kimi is not None
    lanes = kimi["lanes"]
    # Existing generic sweep is preserved, then the monthly meters are added.
    assert lanes[:2] == BASELINE_LANES["kimi-main"]
    assert [lane["window"] for lane in lanes] == [
        "5h",
        "weekly",
        "monthly",
        "monthly",
    ]
    monthly = {lane["label"]: lane for lane in lanes[2:]}
    assert set(monthly) == {"kimi · всего", "kimi · code"}
    assert all(lane["used_percent"] == 0.09 for lane in monthly.values())
    assert all(lane["window_minutes"] == 44640 for lane in monthly.values())


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
    assert payload["windows"] == {
        "5h": {"resets": []},
        "weekly": {"resets": []},
        "monthly": {"resets": []},
    }


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
                    "label": "cursor · модели",
                    "color": "#22d3ee",
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
                    "label": "cursor · другие",
                    "color": app_module.pace_shade(app_module.PACE_COLORS["cursor"], 1),
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
    assert "cursor · модели" in html
    assert "cursor · другие" in html
    # Two distinct fills come from the lane color the server already chose.
    cursor_base = app_module.PACE_COLORS["cursor"]
    cursor_shade = app_module.pace_shade(cursor_base, 1)
    assert cursor_base in html
    assert cursor_shade in html
    assert cursor_base != cursor_shade


KIMI_MONTHLY_RESET = "2026-11-29T00:00:00Z"
CURSOR_MONTHLY_RESET = "2026-11-25T12:27:11Z"


def _render_dashboard(body: str) -> str:
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
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prelude + script + body)
        proc = subprocess.run(
            [node, path], capture_output=True, text=True, timeout=30
        )
    finally:
        os.unlink(path)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _kimi_cursor_monthly_cache(*, include_opencode: bool) -> dict:
    """Dedicated fixture: monthly lanes are only kimi and cursor (plus Go)."""
    accounts: dict = {
        "kimi-main": {
            "probed_at": "2026-09-17T11:57:00Z",
            "session": _window(15.0, "2026-09-17T16:00:00Z"),
            "weekly": _window(25.0, "2026-09-24T00:00:00Z"),
            "monthly_total": _window(0.09, KIMI_MONTHLY_RESET),
            "monthly_code": _window(0.09, KIMI_MONTHLY_RESET),
        },
        "cursor-main": {
            "probed_at": "2026-09-17T11:53:00Z",
            "cursor_models": _window(86.7, CURSOR_MONTHLY_RESET),
            "other_models": _window(74.18, CURSOR_MONTHLY_RESET),
        },
    }
    if include_opencode:
        accounts["opencode-go-main"] = {
            "probed_at": "2026-09-17T11:56:00Z",
            "session": _window(5.0, "2026-09-17T16:00:00Z"),
            "weekly": _window(35.0, "2026-09-24T00:00:00Z"),
            "monthly": _window(45.0, "2026-10-17T00:00:00Z"),
        }
    return {"accounts": accounts}


def test_pace_resets_grouped_by_provider() -> None:
    payload = app_module.build_pace_payload(
        _kimi_cursor_monthly_cache(include_opencode=False), now=NOW
    )
    monthly = payload["windows"]["monthly"]["resets"]
    assert [(row["provider"], row["label"], row["reset_at"]) for row in monthly] == [
        ("kimi", "kimi", KIMI_MONTHLY_RESET),
        ("cursor", "cursor", CURSOR_MONTHLY_RESET),
    ]
    assert len(monthly) == 2

    with_go = app_module.build_pace_payload(
        _kimi_cursor_monthly_cache(include_opencode=True), now=NOW
    )
    go_monthly = with_go["windows"]["monthly"]["resets"]
    assert [row["provider"] for row in go_monthly] == ["kimi", "opencode-go", "cursor"]
    assert len(go_monthly) == 3
    assert len({row["reset_at"] for row in go_monthly}) == 3


def test_pace_lane_labels_carry_provider() -> None:
    cache = _quota_cache()
    cache["accounts"]["kimi-main"]["monthly_total"] = _window(0.09, KIMI_MONTHLY_RESET)
    cache["accounts"]["kimi-main"]["monthly_code"] = _window(0.09, KIMI_MONTHLY_RESET)
    payload = app_module.build_pace_payload(cache, now=NOW)

    kimi = _account(payload, "kimi-main")
    assert kimi is not None
    assert [lane["label"] for lane in kimi["lanes"] if lane["window"] == "monthly"] == [
        "kimi · всего",
        "kimi · code",
    ]
    assert all("label" not in lane for lane in kimi["lanes"] if lane["window"] != "monthly")

    cursor = _account(payload, "cursor-main")
    assert cursor is not None
    assert [lane["label"] for lane in cursor["lanes"]] == [
        "cursor · модели",
        "cursor · другие",
    ]

    for provider in ("zai-main", "commandcode-main", "opencode-go-main"):
        account = _account(payload, provider)
        assert account is not None, provider
        for lane in account["lanes"]:
            assert "label" not in lane, (provider, lane["window"])

    go = _account(payload, "opencode-go-main")
    assert go is not None
    go_monthly = [lane for lane in go["lanes"] if lane["window"] == "monthly"]
    assert len(go_monthly) == 1
    assert "label" not in go_monthly[0]

    # A single window is captioned with the provider name, not a meter suffix.
    if not shutil.which("node"):
        return
    panel = {
        "accounts": [
            {
                "provider": "opencode-go-main",
                "lanes": [
                    {
                        "window": "monthly",
                        "used_percent": 45,
                        "norm_percent": 10,
                        "pace": "ok",
                        "cooldown_minutes": 0,
                        "reset_at": "2026-10-17T00:00:00Z",
                        "color": "#c084fc",
                    }
                ],
            }
        ],
        "windows": {
            "5h": {"resets": []},
            "weekly": {"resets": []},
            "monthly": {
                "resets": [
                    {
                        "provider": "opencode-go",
                        "label": "opencode-go",
                        "reset_at": "2026-10-17T00:00:00Z",
                    }
                ]
            },
        },
        "no_window": [],
    }
    html = _render_dashboard(
        ";(function(){\n"
        "  var data = " + json.dumps(panel, ensure_ascii=False) + ";\n"
        "  process.stdout.write(renderPacePanel(data));\n"
        "})();\n"
    )
    assert "opencode-go" in html
    assert "opencode-go ·" not in html


def test_pace_unknown_reset_lane() -> None:
    cache = {
        "accounts": {
            "zai-main": {
                "probed_at": "2026-09-17T11:59:00Z",
                "session": {
                    "kind": "test-window",
                    "used_percent": 12.5,
                    "remaining_percent": 87.5,
                    "next_reset_at": None,
                    "summary": "12.5% used",
                },
            }
        }
    }
    payload = app_module.build_pace_payload(cache, now=NOW)
    zai = _account(payload, "zai-main")
    assert zai is not None
    assert [lane["window"] for lane in zai["lanes"]] == ["5h"]
    lane = zai["lanes"][0]
    assert lane == {
        "window": "5h",
        "window_minutes": 300,
        "used_percent": 12.5,
        "norm_percent": None,
        "delta_pp": None,
        "pace": "n/a",
        "cooldown_minutes": None,
        "reset_at": None,
        "data_age_seconds": 60,
        "color": app_module.PACE_COLORS["zai"],
    }
    assert "label" not in lane
    assert payload["windows"]["5h"]["resets"] == []
    assert all(
        row["reset_at"]
        for window in payload["windows"].values()
        for row in window["resets"]
    )

    if not shutil.which("node"):
        return
    panel = {
        "accounts": [
            {
                "provider": "zai-main",
                "lanes": [
                    {
                        "window": "5h",
                        "window_minutes": 300,
                        "used_percent": 12.5,
                        "norm_percent": None,
                        "delta_pp": None,
                        "pace": "n/a",
                        "cooldown_minutes": None,
                        "reset_at": None,
                        "data_age_seconds": 60,
                        "color": "#38bdf8",
                    }
                ],
            }
        ],
        "windows": {
            "5h": {"resets": []},
            "weekly": {"resets": []},
            "monthly": {"resets": []},
        },
        "no_window": [],
    }
    html = _render_dashboard(
        ";(function(){\n"
        "  var data = " + json.dumps(panel) + ";\n"
        "  process.stdout.write(renderPacePanel(data));\n"
        "})();\n"
    )
    assert "<circle" not in html
    assert "сброс не сообщается" in html
    assert "5-часовое окно" in html
