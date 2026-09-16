"""Tests for the agent-facing machine-readable limits API (/api/limits).

No provider keys or network access required: the envelope is built from cached
state, and provider failures must surface in "errors" rather than a 500.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module


def _client() -> TestClient:
    return TestClient(app_module.app)


def test_limits_envelope_lists_all_enabled_providers(monkeypatch) -> None:
    monkeypatch.delenv("PROVIDERS", raising=False)
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)
    response = _client().get("/api/limits")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == app_module.LIMITS_SCHEMA_VERSION
    assert "updated_at" in body
    assert "generated_at" in body
    assert isinstance(body["errors"], list)

    providers = body["providers"]
    # Stable ids: exactly the enabled (default: all known) providers.
    assert set(providers.keys()) == set(app_module.KNOWN_PROVIDERS)
    assert len(providers) >= 6
    for stable_id, entry in providers.items():
        assert entry["id"] == stable_id
        assert set(entry.keys()) >= {
            "id",
            "label",
            "status",
            "ok",
            "error",
            "limits",
        }
        assert isinstance(entry["limits"], list)


def test_limits_respects_enabled_providers_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDERS", "deepseek,opencode-go")
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)
    body = _client().get("/api/limits").json()
    assert set(body["providers"].keys()) == {"deepseek", "opencode-go"}


def test_limits_normalizes_quota_windows(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDERS", "commandcode")
    wallet = {
        "provider": "commandcode",
        "kind": "commandcode-credits",
        "status": "active",
        "ok": True,
        "probed_at": "2026-01-01T00:00:00Z",
        "remaining_summary": "Go",
        "session": {
            "kind": "session",
            "used": 1.0,
            "cap": 3.0,
            "remaining_usd": 2.0,
            "used_percent": 33.33,
            "remaining_percent": 66.67,
            "next_reset_at": "2026-01-01T05:00:00Z",
            "summary": "67% left (5h)",
        },
        "weekly": {
            "kind": "weekly",
            "used": 2.0,
            "cap": 6.0,
            "remaining_usd": 4.0,
            "used_percent": 33.33,
            "remaining_percent": 66.67,
            "next_reset_at": None,
            "summary": "67% left (week)",
        },
        "monthly": {
            "kind": "monthly",
            "used": 3.0,
            "cap": 10.0,
            "remaining_usd": 7.0,
            "used_percent": 30.0,
            "remaining_percent": 70.0,
            "next_reset_at": None,
            "summary": "70% left (month)",
        },
    }
    state = {
        "updated_at": None,
        "providers": {},
        "accounts": [],
        "wallets": {"commandcode": wallet},
        "errors": [],
    }
    with patch.object(app_module, "_state", state):
        body = _client().get("/api/limits").json()

    limits = body["providers"]["commandcode"]["limits"]
    assert {limit["id"] for limit in limits} == {"session", "weekly", "monthly"}
    session = next(limit for limit in limits if limit["id"] == "session")
    assert session["limit"] == 3.0
    assert session["used"] == 1.0
    assert session["remaining"] == 2.0
    assert session["reset_at"] == "2026-01-01T05:00:00Z"


def test_limits_provider_error_goes_to_errors_not_500(monkeypatch) -> None:
    monkeypatch.delenv("PROVIDERS", raising=False)
    bad_wallet = {
        "provider": "zai",
        "kind": "coding-quota",
        "status": "error",
        "ok": False,
        "error": "quota/limit API: 503 upstream down",
        "probed_at": "2026-01-01T00:00:00Z",
        "remaining_summary": "",
        "session": None,
        "weekly": None,
        "mcp": None,
    }
    state = {
        "updated_at": "2026-01-01T00:00:00Z",
        "providers": {},
        "accounts": [],
        "wallets": {"zai": bad_wallet},
        "errors": [],
    }
    with patch.object(app_module, "_state", state):
        response = _client().get("/api/limits")

    assert response.status_code == 200
    body = response.json()
    assert "zai" in body["providers"]
    assert body["providers"]["zai"]["status"] == "error"
    assert any("zai" in err and "upstream down" in err for err in body["errors"])


def test_limits_provider_normalizer_exception_is_caught(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDERS", "deepseek,openrouter")
    wallet = {
        "provider": "deepseek",
        "kind": "wallet-balance",
        "status": "active",
        "ok": True,
        "probed_at": None,
        "remaining_summary": "",
        "balance": [],
    }
    state = {
        "updated_at": None,
        "providers": {},
        "accounts": [],
        "wallets": {"deepseek": wallet},
        "errors": [],
    }
    with (
        patch.object(app_module, "_state", state),
        patch.object(
            app_module,
            "_provider_limits",
            side_effect=RuntimeError("normalize boom"),
        ),
    ):
        response = _client().get("/api/limits")

    assert response.status_code == 200
    body = response.json()
    assert set(body["providers"].keys()) == {"deepseek", "openrouter"}
    assert any("normalize boom" in err for err in body["errors"])


def test_limits_never_500_when_builder_fails(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)
    with patch.object(
        app_module,
        "build_limits_payload",
        side_effect=RuntimeError("payload boom"),
    ):
        response = _client().get("/api/limits")

    assert response.status_code == 200
    body = response.json()
    assert body["providers"] == {}
    assert any("payload boom" in err for err in body["errors"])


def test_legacy_usage_route_and_format_unchanged(monkeypatch) -> None:
    monkeypatch.delenv("PROVIDERS", raising=False)
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)
    client = _client()

    summary_body = client.get("/api/summary").json()
    usage_response = client.get("/api/usage")
    assert usage_response.status_code == 200
    usage_body = usage_response.json()

    # Old envelope contract: same keys/shape as /api/summary, no new "limits" leak.
    assert set(usage_body.keys()) == set(summary_body.keys())
    assert isinstance(usage_body["wallets"], dict)
    assert isinstance(usage_body["errors"], list)
    assert set(app_module.KNOWN_PROVIDERS) >= set(usage_body["enabled_providers"])
    assert "limits" not in usage_body


def test_limits_requires_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_API_TOKEN", "s3cret-token")
    monkeypatch.delenv("PROVIDERS", raising=False)
    client = _client()

    assert client.get("/api/limits").status_code == 401
    assert (
        client.get(
            "/api/limits", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )

    ok = client.get("/api/limits", headers={"Authorization": "Bearer s3cret-token"})
    assert ok.status_code == 200
    assert set(ok.json()["providers"].keys()) == set(app_module.KNOWN_PROVIDERS)

    alt = client.get("/api/limits", headers={"X-Agent-Token": "s3cret-token"})
    assert alt.status_code == 200


def test_token_only_guards_limits_route(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_API_TOKEN", "s3cret-token")
    client = _client()
    for path in ("/api/health", "/api/summary", "/api/usage", "/api/providers"):
        assert client.get(path).status_code == 200, path
