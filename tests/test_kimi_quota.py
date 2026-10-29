"""Kimi Coding usage windows: 5h, optional weekly, monthly total/code.

Fixtures are the live 2026-10-28 response (no weekly window at all) plus a
synthetic variant that adds ``limit_7d``. No network access.
"""

import json
from pathlib import Path
from unittest.mock import patch

import app as app_module

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_live_payload_parses_session_and_monthly_meters() -> None:
    windows = app_module.parse_kimi_usages(_fixture("kimi_usages_2026-10-28.json"))

    session = windows["session"]
    assert session is not None
    # limits[] absolute counts win over the ratio-only limit_5h fallback.
    assert session["used"] == 2.0
    assert session["cap"] == 100.0
    assert session["remaining"] == 98.0
    assert session["used_percent"] == 2.0
    assert session["remaining_percent"] == 98.0
    assert session["next_reset_at"] == "2026-10-28T17:02:02Z"

    assert windows["weekly"] is None

    for key in ("monthly_total", "monthly_code"):
        month = windows[key]
        assert month is not None
        assert month["used_percent"] == 0.09
        assert month["next_reset_at"] == "2026-11-29T00:00:00Z"


def test_probe_reads_usages_map_and_keeps_missing_weekly_none() -> None:
    payload = _fixture("kimi_usages_2026-10-28.json")
    with (
        patch.object(app_module, "get_kimi_api_key", return_value="fake-kimi-key-123"),
        patch.object(app_module, "get_kimi_proxy", return_value=None),
        patch.object(
            app_module,
            "http_json",
            return_value=(200, {}, payload, None),
        ),
    ):
        probe = app_module.probe_kimi_usage()

    assert probe["ok"] is True
    assert probe["session"]["used_percent"] == 2.0
    assert probe["weekly"] is None
    assert probe["monthly_total"]["used_percent"] == 0.09
    assert probe["monthly_code"]["used_percent"] == 0.09


def test_wallet_keeps_flat_monthly_keys_and_no_empty_weekly() -> None:
    windows = app_module.parse_kimi_usages(_fixture("kimi_usages_2026-10-28.json"))
    probe = {
        "provider": "kimi",
        "ok": True,
        "status": "active",
        "probed_at": "2026-10-28T14:24:00Z",
        "source": "kimi-coding-v1-usages",
        **windows,
    }
    wallet = app_module.build_kimi_wallet(probe)

    assert wallet is not None
    assert wallet["weekly"] is None
    assert wallet["monthly_total"]["used_percent"] == 0.09
    assert wallet["monthly_code"]["used_percent"] == 0.09
    assert "total" not in wallet["monthly_total"]
    assert "code" not in wallet["monthly_code"]


def test_synthetic_7d_window_is_parsed_when_present() -> None:
    windows = app_module.parse_kimi_usages(_fixture("kimi_usages_with_7d.json"))

    weekly = windows["weekly"]
    assert weekly is not None
    assert weekly["used_percent"] == 42.0
    assert weekly["next_reset_at"] == "2026-11-04T00:00:00Z"


def test_limit_5h_is_only_a_fallback_when_limits_are_empty() -> None:
    payload = _fixture("kimi_usages_2026-10-28.json")
    payload["limits"] = []
    windows = app_module.parse_kimi_usages(payload)

    assert windows["session"] is not None
    assert windows["session"]["used_percent"] == 1.7
    assert windows["session"]["next_reset_at"] == "2026-10-28T17:02:02Z"
