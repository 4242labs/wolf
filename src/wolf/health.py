"""Service health + restart checks, ported from Night Watch's check set:
SSH, Tailscale, Docker, Headroom, agent CLIs, Playwright, Vault.

Each check returns (name, ok, detail). Wolf's caller decides colour mapping;
a missing optional tool (e.g. Headroom on a machine that doesn't run it) is
reported but does not force a failing colour on its own — that's left to the
settings file via which checks are enabled per machine.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from dataclasses import dataclass


@dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str


def _systemd_service_active(unit: str, user_scope: bool = False) -> bool:
    cmd = ["systemctl"]
    if user_scope:
        cmd.append("--user")
    cmd += ["is-active", "--quiet", unit]
    try:
        return subprocess.run(cmd, capture_output=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def _tcp_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _command_exits_zero(command: list[str]) -> bool:
    try:
        return subprocess.run(command, capture_output=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def check_service(label: str, unit: str, user_scope: bool = False) -> HealthCheck:
    """Service-active check. Prefers systemd where present (Alghul); on a
    non-systemd host (Darkseid, macOS) falls back to a tool-native signal
    instead of reporting "not available" for every service.
    """
    if shutil.which("systemctl") is not None:
        ok = _systemd_service_active(unit, user_scope)
        return HealthCheck(label, ok, "active" if ok else "inactive")

    # macOS fallbacks, one per service this check set actually names.
    if label == "SSH":
        ok = _tcp_port_open("127.0.0.1", 22)
        return HealthCheck(label, ok, "active" if ok else "not listening on :22")
    if label == "Tailscale":
        ok = _tailscale_interface_up()
        return HealthCheck(label, ok, "active" if ok else "no tailscale utun interface found")
    if label == "Docker":
        ok = _command_exits_zero(["docker", "info"])
        return HealthCheck(label, ok, "active" if ok else "docker info failed")
    if label == "Headroom":
        ok = _command_exits_zero(["pgrep", "-f", "headroom.cli proxy"])
        return HealthCheck(label, ok, "active" if ok else "no headroom process found")
    return HealthCheck(label, False, "no non-systemd fallback defined for this service")


def _tailscale_interface_up() -> bool:
    """Tailscale's own CLI can crash on a broken bundle-identifier registry
    (seen in practice) without that meaning the daemon or tunnel is down.
    A `utun` interface carrying a Tailscale CGNAT address (100.64.0.0/10) is
    the ground truth signal instead.
    """
    try:
        proc = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False
    if proc.returncode != 0:
        return False
    return bool(re.search(r"inet 100\.(6[4-9]|[7-9]\d|1[0-1]\d|12[0-7])\.", proc.stdout))


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
