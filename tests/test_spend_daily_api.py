"""Tests for the read-only daily spend API (/api/spend-daily).

The endpoint derives a calendar-day series from spend.jsonl only: it never
performs network I/O or invents zeroes for providers without a spend metric.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module


def _row(ts: str, used_usd: float | None = None) -> dict:
    wallets: dict = {}
    if used_usd is not None:
        wallets["opencode-go"] = {"monthly": {"used_usd": used_usd}}
    return {"ts": ts, "wallets": wallets}


def _write_spend(
    monkeypatch,
    tmp_path: Path,
    rows: list[dict | str],
) -> Path:
    monkeypatch.setattr(app_module, "SNAPSHOT_PATH", tmp_path / "snapshots.jsonl")
    path = tmp_path / "spend.jsonl"
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _day_ts(day, hour: int = 12) -> str:
    return f"{day.isoformat()}T{hour:02d}:00:00Z"


def _client() -> TestClient:
    return TestClient(app_module.app)


def test_spend_daily_delta(monkeypatch, tmp_path) -> None:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    _write_spend(
        monkeypatch,
        tmp_path,
        [
            _row(_day_ts(yesterday), 1.0),
            _row(_day_ts(today), 2.5),
        ],
    )

    response = _client().get("/api/spend-daily?days=30")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "spend-daily.v1"
    assert body["days"] == 30

    points = body["providers"]["opencode-go"]["points"]
    assert [point["date"] for point in points] == [
        yesterday.isoformat(),
        today.isoformat(),
    ]
    assert points[0]["spent"] is None
    assert points[1]["spent"] == pytest.approx(1.5)


def test_spend_daily_first_point_partial(monkeypatch, tmp_path) -> None:
    today = datetime.now(timezone.utc).date()
    _write_spend(
        monkeypatch,
        tmp_path,
        [
            _row(_day_ts(today - timedelta(days=2)), 3.0),
            _row(_day_ts(today - timedelta(days=1)), 4.0),
            _row(_day_ts(today), 6.0),
        ],
    )

    first = _client().get("/api/spend-daily?days=30").json()["providers"][
        "opencode-go"
    ]["points"][0]
    assert first["partial"] is True
    assert first["spent"] is None


def test_spend_daily_gaps_are_explicit(monkeypatch, tmp_path) -> None:
    today = datetime.now(timezone.utc).date()
    _write_spend(
        monkeypatch,
        tmp_path,
        [_row(_day_ts(today - timedelta(days=1)), 1.0)],
    )

    providers = _client().get("/api/spend-daily?days=30").json()["providers"]
    for name, expected_gap in (("cursor", "no-history"), ("zai", "no-metric")):
        provider = providers[name]
        assert provider["points"] == []
        assert provider["gap"] == expected_gap
        assert provider.get("measured") is not True


def test_spend_daily_survives_broken_line(monkeypatch, tmp_path) -> None:
    today = datetime.now(timezone.utc).date()
    _write_spend(
        monkeypatch,
        tmp_path,
        [
            _row(_day_ts(today - timedelta(days=1)), 1.0),
            "{this is not json",
            _row(_day_ts(today), 2.0),
        ],
    )

    response = _client().get("/api/spend-daily?days=30")
    assert response.status_code == 200
    body = response.json()
    assert body["providers"]["opencode-go"]["points"][-1]["spent"] == pytest.approx(1.0)
    assert body["skipped_lines"] == 1


@pytest.mark.parametrize("days", ["0", "91", "-1", "abc", "1.5"])
def test_spend_daily_days_validation(monkeypatch, tmp_path, days: str) -> None:
    _write_spend(monkeypatch, tmp_path, [])
    response = _client().get(f"/api/spend-daily?days={days}")
    assert response.status_code == 400
    assert "days" in response.json()["detail"]


def test_spend_daily_full_window(monkeypatch, tmp_path) -> None:
    today = datetime.now(timezone.utc).date()
    rows: list[dict | str] = []
    # History 13.10–27.10 with the current (incomplete) day left out: 14
    # observed days -> first day partial plus 13 real deltas.
    for offset in range(14, 0, -1):
        day = today - timedelta(days=offset)
        rows.append(_row(_day_ts(day), float(100 - offset)))
    _write_spend(monkeypatch, tmp_path, rows)

    body = _client().get("/api/spend-daily?days=30").json()
    points = body["providers"]["opencode-go"]["points"]
    deltas = [point for point in points if point.get("spent") is not None]
    assert len(points) == 14
    assert len(deltas) == 13
    assert points[0]["partial"] is True
    assert all(point["spent"] == pytest.approx(1.0) for point in deltas)

    for name in ("cursor", "zai"):
        provider = body["providers"][name]
        assert provider["points"] == []
        assert provider["gap"]
