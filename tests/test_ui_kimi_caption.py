"""Static checks for the Kimi card caption and monthly detail labels."""

from pathlib import Path

import app as app_module


def _dashboard_html() -> str:
    return (
        Path(app_module.__file__).resolve().parent / "static" / "index.html"
    ).read_text(encoding="utf-8")


def test_kimi_hero_uses_available_windows_in_order() -> None:
    html = _dashboard_html()
    start = html.index("if (p === 'kimi') {")
    end = html.index("if (p === 'opencode-go') {", start)
    block = html[start:end]

    assert "w.session" in block
    assert "w.monthly_total" in block
    assert "w.monthly_code" in block
    assert "session.remaining_percent" in block
    assert "week.remaining_percent" in block
    assert "month.used_percent" in block
    assert "'5 ч'" in block
    assert "'из недельной квоты'" in block
    assert "'из месячной квоты'" in block
    # The old unconditional weekly caption is gone.
    assert "caption: 'из недельной квоты',\n      plan: w.plan_label" not in block


def test_kimi_monthly_meters_have_detail_rows() -> None:
    html = _dashboard_html()
    assert "месяц (всего)" in html
    assert "месяц (code)" in html
    assert "card.monthly_total" in html
    assert "card.monthly_code" in html
