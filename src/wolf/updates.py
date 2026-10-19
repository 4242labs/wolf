"""Pending-updates check and report of updates installed since last run.

Wolf never installs updates itself (Decisions: Alghul uses unattended-upgrades;
Darkseid installs nothing automatically). This module only observes and reports.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass


@dataclass
class UpdatesStatus:
    pending_count: int
    pending_summary: str
    installed_since_log: str = ""


def _linux_pending_updates() -> UpdatesStatus:
    try:
        out = subprocess.run(
            ["apt", "list", "--upgradable"], capture_output=True, text=True, check=False
        ).stdout
    except FileNotFoundError:
        return UpdatesStatus(pending_count=0, pending_summary="apt not available")

    lines = [ln for ln in out.splitlines() if ln and not ln.startswith("Listing...")]
    return UpdatesStatus(
        pending_count=len(lines),
        pending_summary="; ".join(lines[:20]) if lines else "none pending",
    )


def _darwin_pending_updates() -> UpdatesStatus:
    try:
        out = subprocess.run(
            ["softwareupdate", "-l"], capture_output=True, text=True, check=False
        ).stdout
    except FileNotFoundError:
        return UpdatesStatus(pending_count=0, pending_summary="softwareupdate not available")

    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("*")]
    return UpdatesStatus(
        pending_count=len(lines),
        pending_summary="; ".join(lines) if lines else "none pending",
    )


def pending_updates() -> UpdatesStatus:
    if platform.system() == "Darwin":
        return _darwin_pending_updates()
    return _linux_pending_updates()


def unattended_upgrades_log_tail(lines: int = 20) -> str:
    """Report what unattended-upgrades installed since the last run (Linux only)."""
    log_path = "/var/log/unattended-upgrades/unattended-upgrades.log"
    try:
        with open(log_path) as f:
            content = f.readlines()
        return "".join(content[-lines:])
    except OSError:
        return ""
