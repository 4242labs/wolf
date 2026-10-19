"""Reboot gating logic.

Rules (42L-2204 Decisions -> Reboots):
- Reboot required by updates -> RED.
- Otherwise, days since last reboot: yellow at 3, red at 5.
- An active agent chat alone never makes the report yellow (uptime-only
  status is computed independently of the idle-chat gate; see
  reboot_status()).
- At the run, Wolf reboots a due machine (updates-required OR days-up over
  threshold) IF no agent chat was active in the configured idle window.
  Red only if a reboot is still needed after that attempt.
- A machine with reboot.allowed = False (Darkseid) never reboots itself,
  report-only.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from wolf.colour import Colour
from wolf.config import RebootConfig
from wolf.idle_chat import is_active


@dataclass
class RebootStatus:
    colour: Colour
    reboot_required_by_updates: bool
    days_since_last_reboot: float
    reboot_attempted: bool
    reboot_performed: bool
    reason: str


def days_since_boot() -> float:
    """macOS + Linux: seconds since boot, derived without external deps where
    possible. Falls back to parsing `uptime -s` (Linux) or `sysctl` (macOS).
    """
    import platform

    system = platform.system()
    if system == "Darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, check=True
            ).stdout
            # Format: '{ sec = 1729000000, usec = 123456 } Fri Oct 17 ...'
            sec_str = out.split("sec = ")[1].split(",")[0].strip()
            boot_time = float(sec_str)
        except (subprocess.SubprocessError, FileNotFoundError, IndexError, ValueError):
            return 0.0
    else:
        try:
            with open("/proc/uptime") as f:
                uptime_seconds = float(f.read().split()[0])
            return uptime_seconds / 86400.0
        except (OSError, ValueError, IndexError):
            return 0.0

    import time

    return (time.time() - boot_time) / 86400.0


def reboot_required_by_updates() -> bool:
    """True if the OS has flagged a pending reboot from installed updates."""
    import platform
    from pathlib import Path

    if platform.system() == "Darwin":
        # macOS has no single canonical flag file; Wolf's updates module
        # reports pending updates separately. No install happens on Darkseid,
        # so this is always False there by design (Decisions: Darkseid never
        # auto-installs).
        return False
    return Path("/var/run/reboot-required").exists()


def reboot_status(config: RebootConfig) -> RebootStatus:
    required_by_updates = reboot_required_by_updates()
    days_up = days_since_boot()

    if required_by_updates or days_up >= config.red_days:
        due = True
    else:
        due = False

    colour = Colour.GREEN
    if required_by_updates or days_up >= config.red_days:
        colour = Colour.RED
    elif days_up >= config.yellow_days:
        colour = Colour.YELLOW

    reboot_attempted = False
    reboot_performed = False
    reason = "not due"

    if due and config.allowed:
        if is_active(config.idle_chat_hours):
            reason = "due but agent chat active within idle window; reboot deferred"
        else:
            reboot_attempted = True
            reason = perform_reboot()
            reboot_performed = reason == "rebooted"
            if not reboot_performed:
                colour = Colour.RED
    elif due and not config.allowed:
        reason = "due but reboot not allowed on this machine (report-only)"

    return RebootStatus(
        colour=colour,
        reboot_required_by_updates=required_by_updates,
        days_since_last_reboot=days_up,
        reboot_attempted=reboot_attempted,
        reboot_performed=reboot_performed,
        reason=reason,
    )


def perform_reboot() -> str:
    """Issue the platform reboot command. Returns 'rebooted' on success (though
    the process will usually not survive to observe that), or an error string.
    """
    import platform

    try:
        if platform.system() == "Darwin":
            subprocess.run(["sudo", "shutdown", "-r", "now"], check=True)
        else:
            subprocess.run(["sudo", "systemctl", "reboot"], check=True)
        return "rebooted"
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        return f"reboot command failed: {exc}"
