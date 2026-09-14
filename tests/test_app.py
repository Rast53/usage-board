"""Smoke tests for usage-board (no provider keys required)."""

import base64
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module


def test_health_no_auth() -> None:
    client = TestClient(app_module.app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "updated_at" in body


def test_get_enabled_providers_all_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PROVIDERS", raising=False)
    assert app_module.get_enabled_providers() == list(app_module.KNOWN_PROVIDERS)


def test_get_enabled_providers_subset(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDERS", "deepseek,openrouter,unknown")
    assert app_module.get_enabled_providers() == ["deepseek", "openrouter"]


def test_basic_auth_valid() -> None:
    with (
        patch.object(app_module, "_BASIC_AUTH_USER", "alice"),
        patch.object(app_module, "_BASIC_AUTH_PASSWORD", "secret"),
    ):
        creds = base64.b64encode(b"alice:secret").decode()
        assert app_module._basic_auth_valid(f"Basic {creds}")
        assert not app_module._basic_auth_valid("Basic wrong")
        assert not app_module._basic_auth_valid("Bearer token")


def test_summary_enabled_providers(monkeypatch) -> None:
    monkeypatch.delenv("PROVIDERS", raising=False)
    client = TestClient(app_module.app)
    response = client.get("/api/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled_providers"] == list(app_module.KNOWN_PROVIDERS)
