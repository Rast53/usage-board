"""The provider-windows matrix lists every slug the board knows."""

from pathlib import Path

import app as app_module


def _table_slugs(text: str) -> list[str]:
    slugs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0].strip("`").strip()
        if not first or first == "Провайдер" or set(first) <= {"-", ":"}:
            continue
        slugs.append(first)
    return slugs


def test_provider_windows_matrix_lists_known_providers() -> None:
    path = (
        Path(app_module.__file__).resolve().parent
        / "docs"
        / "provider-windows-matrix.md"
    )
    text = path.read_text(encoding="utf-8")
    slugs = _table_slugs(text)
    assert slugs == list(app_module.KNOWN_PROVIDERS)
    assert "нет данных" in text
    assert "деньги, не окно" in text
