"""Service health + restart checks, ported from Night Watch's check set:
SSH, Tailscale, Docker, Headroom, agent CLIs, Playwright, Vault.

Each check returns (name, ok, detail). Wolf's caller decides colour mapping;
a missing optional tool (e.g. Headroom on a machine that doesn't run it) is
reported but does not force a failing colour on its own — that's left to the
settings file via which checks are enabled per machine.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str


def _service_active(unit: str, user_scope: bool = False) -> bool:
    cmd = ["systemctl"]
    if user_scope:
        cmd.append("--user")
    cmd += ["is-active", "--quiet", unit]
    try:
        return subprocess.run(cmd, capture_output=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def check_service(label: str, unit: str, user_scope: bool = False) -> HealthCheck:
    if shutil.which("systemctl") is None:
        return HealthCheck(label, False, "systemctl not available (non-systemd host)")
    ok = _service_active(unit, user_scope)
    return HealthCheck(label, ok, "active" if ok else "inactive")


def check_command(label: str, command: str) -> HealthCheck:
    path = shutil.which(command)
    return HealthCheck(label, path is not None, path or "missing")


def check_http(label: str, url: str, timeout: float = 3.0) -> HealthCheck:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:
            ok = 200 <= resp.status < 300
            return HealthCheck(label, ok, f"HTTP {resp.status}")
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        return HealthCheck(label, False, str(exc))


def run_night_watch_equivalent_checks() -> list[HealthCheck]:
    """The fixed check set ported from Alghul's night-watch script. A machine's
    settings decide which of these are relevant (e.g. Darkseid has no systemd).
    """
    checks = [
        check_service("SSH", "ssh"),
        check_service("Tailscale", "tailscaled"),
        check_service("Docker", "docker"),
        check_service("Headroom", "headroom.service", user_scope=True),
        check_http("Headroom proxy", "http://127.0.0.1:8788/readyz"),
        check_command("GitHub CLI", "gh"),
        check_command("Claude Code", "claude"),
        check_command("Codex", "codex"),
        check_command("Hermes", "hermes"),
        check_command("AGY", "agy"),
        check_command("Pi", "pi"),
        check_command("Playwright", "playwright"),
        check_command("Vault CLI", "vault"),
    ]
    return checks
