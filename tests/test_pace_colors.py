"""Server-owned pace palette: one base color per provider, shades for extra meters."""

from datetime import datetime, timezone
from pathlib import Path

import app as app_module

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _window(used_percent: float, reset_at: str) -> dict:
    return {
        "used_percent": used_percent,
        "remaining_percent": round(100.0 - used_percent, 2),
        "next_reset_at": reset_at,
    }


def test_pace_colors_are_stable_shades_and_client_does_not_own_them() -> None:
    assert set(app_module.PACE_COLORS) == set(app_module.KNOWN_PROVIDERS)
    assert len(app_module.PACE_COLORS) == 7

    cache = {
        "accounts": {
            "kimi-main": {
                "probed_at": "2026-09-17T11:57:00Z",
                "session": _window(15.0, "2026-09-17T16:00:00Z"),
                "weekly": _window(25.0, "2026-09-24T00:00:00Z"),
                "monthly_total": _window(0.09, "2026-11-29T00:00:00Z"),
                "monthly_code": _window(0.11, "2026-11-29T00:00:00Z"),
            },
            "cursor-main": {
                "probed_at": "2026-09-17T11:53:00Z",
                "cursor_models": _window(86.7, "2026-11-25T12:27:11Z"),
                "other_models": _window(74.18, "2026-11-25T12:27:11Z"),
            },
            "zai-main": {
                "probed_at": "2026-09-17T11:59:00Z",
                "session": _window(10.0, "2026-09-17T15:00:00Z"),
            },
        }
    }
    payload = app_module.build_pace_payload(cache, now=NOW)
    by_provider = {account["provider"]: account for account in payload["accounts"]}

    kimi = by_provider["kimi-main"]["lanes"]
    five_h = next(lane for lane in kimi if lane["window"] == "5h")
    weekly = next(lane for lane in kimi if lane["window"] == "weekly")
    monthly = [lane for lane in kimi if lane["window"] == "monthly"]
    assert len(monthly) == 2

    base = app_module.PACE_COLORS["kimi"]
    assert five_h["color"] == weekly["color"] == monthly[0]["color"]
    assert five_h["color"] == app_module.pace_shade(base, 0)
    assert monthly[1]["color"] == app_module.pace_shade(base, 1)
    assert monthly[0]["color"] != monthly[1]["color"]
    # Both meter colors are shades of the provider base, including step 0.
    assert monthly[0]["color"] == app_module.pace_shade(base, 0)
    assert monthly[1]["color"] == app_module.pace_shade(base, 1)

    cursor = by_provider["cursor-main"]["lanes"]
    cursor_base = app_module.PACE_COLORS["cursor"]
    assert cursor[0]["color"] == app_module.pace_shade(cursor_base, 0)
    assert cursor[1]["color"] == app_module.pace_shade(cursor_base, 1)
    assert cursor[0]["color"] != cursor[1]["color"]

    for account in payload["accounts"]:
        for lane in account["lanes"]:
            assert isinstance(lane["color"], str)
            assert lane["color"].startswith("#")
            assert len(lane["color"]) == 7

    html = (
        Path(app_module.__file__).resolve().parent / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert "PACE_LANE_COLORS" not in html
    assert "PACE_COLORS" not in html
    assert "pace_shade" not in html
