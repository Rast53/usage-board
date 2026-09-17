"""Deployment contract tests for the autodeploy / repull rail.

These are the "unit/script check" from the task acceptance: the app service must
repull the published image on every deploy, and the host autodeploy rail must be
wired to the exact revision-label verification command.

No third-party imports (the CI test job installs only fastapi/uvicorn/httpx/
pytest/PySocks), so a tiny indentation reader stands in for a YAML parser.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

APP_ONLY = ROOT / "compose.app-only.yml"
APP_ONLY_OVERLAY = ROOT / "docker-compose.app-only.yml"
MAIN_COMPOSE = ROOT / "docker-compose.yml"
AUTODEPLOY = ROOT / "deploy" / "autodeploy.sh"
CHECK_PULL_POLICY = ROOT / "deploy" / "check-pull-policy.sh"
SYSTEMD_DIR = ROOT / "deploy"

# The `environment:` keys of the app-only app service. Kept here as a contract so
# the autodeploy change can never silently add/drop/rename an env var (and thus
# never touch .env semantics). The negative acceptance check relies on this.
APP_ONLY_ENV_KEYS = {
    "DOMAIN",
    "BASIC_AUTH_USER",
    "BASIC_AUTH_PASSWORD",
    "USAGE_POLL_SECONDS",
    "SITE_TITLE",
    "DISPLAY_TZ",
    "DEEPSEEK_API_KEY",
    "COMMANDCODE_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MANAGEMENT_KEY",
    "OPENCODE_GO_API_KEY",
    "KIMI_API_KEY",
    "ZAI_API_KEY",
    "USAGE_PORT",
    "USAGE_DATA_DIR",
    "USAGE_STATIC_DIR",
}


def _service_block(text: str, name: str) -> str:
    """Return the raw lines of a top-level `services:` entry.

    Service names sit at two-space indent; their keys at four. This is exactly
    the shape of the compose files in this repo.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("  ") and not line.startswith("    ") and line.strip() == f"{name}:":
            start = i + 1
            break
    assert start is not None, f"service {name!r} not found"
    block: list[str] = []
    for line in lines[start:]:
        if line.strip() == "":
            block.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent < 4:
            break
        block.append(line)
    return "\n".join(block)


def _env_keys(block: str) -> set[str]:
    keys: set[str] = set()
    in_env = False
    for line in block.splitlines():
        if re.match(r"\s{4}environment:\s*$", line):
            in_env = True
            continue
        if in_env:
            if line.strip() == "":
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent < 6:
                in_env = False
                continue
            m = re.match(r"\s{6}([A-Z0-9_]+):", line)
            if m:
                keys.add(m.group(1))
    return keys


# --- compose repull rail -----------------------------------------------------


def test_app_only_compose_repulls_image():
    block = _service_block(APP_ONLY.read_text(), "app")
    assert "pull_policy: always" in block


def test_default_compose_repulls_image():
    block = _service_block(MAIN_COMPOSE.read_text(), "app")
    assert "pull_policy: always" in block


def test_app_only_env_contract_unchanged():
    """Negative gate: the autodeploy change must not alter app env/creds."""
    assert _env_keys(_service_block(APP_ONLY.read_text(), "app")) == APP_ONLY_ENV_KEYS


# --- published port contract (loopback only) ---------------------------------
# TASK-usage-board-close-plain-port: the app-only stack must never publish the
# bare app port on 0.0.0.0. The host reverse proxy is the only way in, so the
# bind IP is pinned to 127.0.0.1 while APP_PORT stays configurable.

LOOPBACK_PUBLISH = '"127.0.0.1:${APP_PORT:-8080}:3210"'


def _published_lines(text: str) -> list[str]:
    """Port-publish entries that interpolate APP_PORT and target 3210."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("-")
        and "3210" in line
        and "APP_PORT" in line
    ]


def test_app_only_compose_publishes_loopback_only():
    block = _service_block(APP_ONLY.read_text(), "app")
    assert LOOPBACK_PUBLISH in block


def test_app_only_overlay_publishes_loopback_only():
    block = _service_block(APP_ONLY_OVERLAY.read_text(), "app")
    assert LOOPBACK_PUBLISH in block


def test_no_compose_publishes_app_port_on_all_interfaces():
    """Negative gate: no bare `APP_PORT:3210` publish (implicit 0.0.0.0)."""
    for path in (APP_ONLY, APP_ONLY_OVERLAY):
        publish_lines = _published_lines(path.read_text())
        assert publish_lines, f"{path}: no APP_PORT publish line found"
        for line in publish_lines:
            assert "127.0.0.1:" in line, f"{path}: non-loopback publish {line!r}"


def test_default_compose_does_not_publish_app_port():
    """The Caddy/TLS stack keeps the app internal (expose only, no ports)."""
    block = _service_block(MAIN_COMPOSE.read_text(), "app")
    assert "ports:" not in block
    assert "3210" in block  # still reachable from the compose network via expose:


def test_rendered_app_only_port_is_loopback():
    """Acceptance #1: rendered compose yields 127.0.0.1:8090 -> 3210."""
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    env = {**os.environ, "APP_PORT": "8090"}
    proc = subprocess.run(
        ["docker", "compose", "-f", "compose.app-only.yml", "config", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ports = json.loads(proc.stdout)["services"]["app"]["ports"]
    assert ports == [
        {
            "mode": "ingress",
            "host_ip": "127.0.0.1",
            "target": 3210,
            "published": "8090",
            "protocol": "tcp",
        }
    ], ports


# --- host autodeploy rail ----------------------------------------------------


def test_autodeploy_script_is_present_and_executable():
    assert AUTODEPLOY.is_file()
    mode = AUTODEPLOY.stat().st_mode
    assert mode & stat.S_IXUSR, "autodeploy.sh must be executable"
    assert AUTODEPLOY.read_text().startswith("#!/usr/bin/env bash")


def test_autodeploy_repulls_and_verifies_revision_label():
    script = AUTODEPLOY.read_text()
    assert "set -euo pipefail" in script
    assert re.search(r"compose\s+pull\s+", script), "must repull the image"
    assert "up -d --no-deps" in script, "must recreate only the app service"
    assert 'org.opencontainers.image.revision' in script
    assert "EXPECT_REVISION" in script, "must be able to hard-gate the revision"


def test_autodeploy_does_not_touch_env_or_secrets():
    script = AUTODEPLOY.read_text()
    # No redirect into a dotenv file, no reading/echoing secrets.
    assert not re.search(r"(^|\s)>>?\s*[^\n]*\.env", script)
    assert "cat .env" not in script
    assert "EnvironmentFile" not in script


def test_systemd_service_runs_the_script():
    unit = (SYSTEMD_DIR / "usage-board-autodeploy.service").read_text()
    assert "ExecStart=" in unit
    assert "deploy/autodeploy.sh" in unit
    assert "WorkingDirectory=" in unit
    assert "Type=oneshot" in unit


def test_systemd_timer_periodically_triggers_the_service():
    timer = (SYSTEMD_DIR / "usage-board-autodeploy.timer").read_text()
    assert "Unit=usage-board-autodeploy.service" in timer
    assert "OnUnitActiveSec=" in timer
    assert "WantedBy=timers.target" in timer


# --- CI gate -----------------------------------------------------------------
# NOTE: the PAT used to push this branch has no `workflow` scope, so
# .github/workflows/build.yml cannot be changed from here. The gate therefore
# rides the existing `test` CI job (`pytest -q`) and this standalone script.


def test_check_pull_policy_script_present_and_executable():
    assert CHECK_PULL_POLICY.is_file()
    assert CHECK_PULL_POLICY.stat().st_mode & stat.S_IXUSR


def test_check_pull_policy_script_enforces_app_repull():
    """Real `docker compose config` gate; skipped where docker is unavailable."""
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    proc = subprocess.run(
        [str(CHECK_PULL_POLICY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "services.app.pull_policy=always" in proc.stdout
