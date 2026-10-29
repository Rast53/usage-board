"""Static checks for the Kimi card caption and monthly detail labels."""

import json
import os
import shutil
import subprocess
import tempfile
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


def test_kimi_monthly_meters_visible_in_card_body() -> None:
    """Monthly meters are in the card body, before the collapsed details block."""
    html = _dashboard_html()
    start = html.index("function renderKimiCard")
    end = html.index("function renderOpencodeGoCard", start)
    block = html[start:end]
    details_at = block.index("details:")
    body = block[:details_at]
    details = block[details_at:]
    assert "месяц (всего)" in body
    assert "месяц (code)" in body
    assert "monthly_total" in body
    assert "monthly_code" in body
    # The collapsed rows stay where they were.
    assert "месяц (всего)" in details
    assert "месяц (code)" in details
    assert "monthRow('месяц (всего)'" in details
    assert "monthRow('месяц (code)'" in details

    card_start = html.index("function renderProviderCard")
    card_end = html.index("function renderZaiCard", card_start)
    renderer = html[card_start:card_end]
    assert renderer.index("afterBars") < renderer.index('class="details-body"')

    node = shutil.which("node")
    if not node:
        return
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    wallet = {
        "provider": "kimi",
        "ok": True,
        "plan_label": "Kimi",
        "session": {"remaining_percent": 98, "used_percent": 2},
        "monthly_total": {"used_percent": 0.09, "next_reset_at": "2026-11-29T00:00:00Z"},
        "monthly_code": {"used_percent": 0.09, "next_reset_at": "2026-11-29T00:00:00Z"},
    }
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
        "  var card = " + json.dumps(wallet, ensure_ascii=False) + ";\n"
        "  process.stdout.write(renderKimiCard(card));\n"
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
    rendered = proc.stdout
    details_at = rendered.index('class="details-body"')
    body_html = rendered[:details_at]
    details_html = rendered[details_at:]
    assert "месяц (всего)" in body_html
    assert "месяц (code)" in body_html
    assert "0.09%" in body_html
    assert "5 ч" in body_html
    assert "месяц (всего)" in details_html
    assert "месяц (code)" in details_html
