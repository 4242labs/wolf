"""Consolidated SysAdmin Daily/Weekly Report.

Reads each machine's latest Wolf run result (delivered to this host, e.g.
Alghul, via Wolf's SSH-push delivery) and builds one consolidated email,
per the rules in 42L-2204's Decisions -> Report:

- One email for all machines.
- Daily: sent only when something is not green.
- Monday: weekly summary always sent, a 7-day worst-state-per-day rollup.
- Missed-run colours per machine (yellow/red thresholds from its config).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wolf.colour import Colour, worst


@dataclass
class MachineReportEntry:
    machine: str
    colour: Colour
    last_run_at: str | None
    missed_run_colour: Colour
    summary_lines: list[str]


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def missed_run_colour(
    last_run_at: str | None,
    yellow_days: float,
    red_days: float,
    now: datetime | None = None,
) -> Colour:
    now = now or datetime.now(UTC)
    if last_run_at is None:
        return Colour.RED
    last = _parse_iso(last_run_at)
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    age_days = (now - last).total_seconds() / 86400.0
    if age_days >= red_days:
        return Colour.RED
    if age_days >= yellow_days:
        return Colour.YELLOW
    return Colour.GREEN


def load_latest_result(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def build_machine_entry(
    machine: str,
    incoming_dir: Path,
    yellow_days: float,
    red_days: float,
    now: datetime | None = None,
) -> MachineReportEntry:
    """incoming_dir holds files named '<machine>-latest.json' (Wolf's SSH-push
    delivery target) for remote machines, or 'latest.json' for the local one.
    """
    candidates = [incoming_dir / f"{machine}-latest.json", incoming_dir / "latest.json"]
    data = None
    for c in candidates:
        data = load_latest_result(c)
        if data:
            break

    if data is None:
        return MachineReportEntry(
            machine=machine,
            colour=Colour.RED,
            last_run_at=None,
            missed_run_colour=Colour.RED,
            summary_lines=["no run result found"],
        )

    run_colour = Colour[data.get("colour", "RED")]
    last_run_at = data.get("finished_at") or data.get("started_at")
    missed = missed_run_colour(last_run_at, yellow_days, red_days, now)

    lines = []
    freed = data.get("cache_freed_bytes", 0)
    if freed:
        lines.append(f"cache: freed {freed / (1000**3):.2f} GB")
    reaped = data.get("processes_reaped", [])
    if reaped:
        lines.append(f"processes reaped: {len(reaped)}")
    docker_freed = data.get("docker_freed_bytes", 0)
    if docker_freed:
        lines.append(f"docker: freed {docker_freed / (1000**3):.2f} GB")
    reboot = data.get("reboot", {})
    if reboot:
        lines.append(f"reboot: {reboot.get('reason', 'n/a')}")
    updates_pending = data.get("updates_pending", 0)
    if updates_pending:
        lines.append(f"updates pending: {updates_pending}")
    for svc in data.get("services", []):
        if not svc.get("ok"):
            lines.append(f"service down: {svc.get('name')} ({svc.get('detail')})")

    return MachineReportEntry(
        machine=machine,
        colour=worst([run_colour, missed]),
        last_run_at=last_run_at,
        missed_run_colour=missed,
        summary_lines=lines or ["all green, nothing to report"],
    )


def should_send_daily(entries: list[MachineReportEntry]) -> bool:
    """Daily report sends only when something is not green."""
    return any(e.colour != Colour.GREEN for e in entries)


def is_weekly_day(now: datetime | None = None) -> bool:
    """Monday, per Decisions."""
    now = now or datetime.now(UTC)
    return now.weekday() == 0  # Monday == 0


def build_subject(entries: list[MachineReportEntry], weekly: bool) -> str:
    overall = worst([e.colour for e in entries])
    kind = "Weekly" if weekly else "Daily"
    return f"{overall.emoji} SysAdmin {kind} Report"


def build_plaintext_body(entries: list[MachineReportEntry], weekly: bool) -> str:
    now = datetime.now(UTC)
    kind = "Weekly" if weekly else "Daily"
    lines = [f"SysAdmin {kind} Report — {now.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    for e in entries:
        lines.append(f"{e.colour.emoji} {e.machine} — last run: {e.last_run_at or 'never'}")
        for s in e.summary_lines:
            lines.append(f"    - {s}")
        lines.append("")
    return "\n".join(lines)
