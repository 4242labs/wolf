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
    # One row per individual check, each carrying its own colour — matches
    # Night Watch's per-check add_row() table instead of one row per machine.
    summary_rows: list[tuple[Colour, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.summary_rows is None:
            self.summary_rows = [(self.colour, line) for line in self.summary_lines]


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
            summary_rows=[(Colour.RED, "no run result found")],
        )

    run_colour = Colour[data.get("colour", "RED")]
    last_run_at = data.get("finished_at") or data.get("started_at")
    missed = missed_run_colour(last_run_at, yellow_days, red_days, now)

    rows: list[tuple[Colour, str]] = [(missed, f"last run: {last_run_at or 'never'}")]
    freed = data.get("cache_freed_bytes", 0)
    if freed:
        rows.append((Colour.GREEN, f"cache: freed {freed / (1000**3):.2f} GB"))
    reaped = data.get("processes_reaped", [])
    if reaped:
        rows.append((Colour.GREEN, f"processes reaped: {len(reaped)}"))
    docker_freed = data.get("docker_freed_bytes", 0)
    if docker_freed:
        rows.append((Colour.GREEN, f"docker: freed {docker_freed / (1000**3):.2f} GB"))
    reboot = data.get("reboot", {})
    if reboot:
        reboot_colour = Colour.RED if reboot.get("done") else Colour.YELLOW
        rows.append((reboot_colour, f"reboot: {reboot.get('reason', 'n/a')}"))
    updates_pending = data.get("updates_pending", 0)
    if updates_pending:
        updates_colour = Colour.YELLOW if updates_pending < 20 else Colour.RED
        rows.append((updates_colour, f"updates pending: {updates_pending}"))
    for svc in data.get("services", []):
        if not svc.get("ok"):
            rows.append(
                (Colour.RED, f"service down: {svc.get('name')} ({svc.get('detail')})")
            )

    if not rows[1:]:
        rows.append((Colour.GREEN, "all green, nothing to report"))

    return MachineReportEntry(
        machine=machine,
        colour=worst([run_colour, missed]),
        last_run_at=last_run_at,
        missed_run_colour=missed,
        summary_lines=[line for _, line in rows],
        summary_rows=rows,
    )


def history_path(incoming_dir: Path, machine: str) -> Path:
    return incoming_dir / "history" / f"{machine}.jsonl"


def append_history(incoming_dir: Path, entry: MachineReportEntry, now: datetime | None = None) -> None:
    """Append today's result for one machine to its history log, one line per
    day. Called on every run (daily and weekly) so the weekly rollup has real
    accumulated days to look back over, starting from the first run — no
    artificial warm-up period. Keeps the last 7 entries per machine.
    """
    now = now or datetime.now(UTC)
    path = history_path(incoming_dir, entry.machine)
    path.parent.mkdir(parents=True, exist_ok=True)

    day = now.strftime("%Y-%m-%d")
    record = {
        "date": day,
        "colour": entry.colour.name,
        "rows": [[c.name, d] for c, d in entry.summary_rows],
    }

    lines: list[dict] = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                lines.append(json.loads(line))
    # Replace today's entry if this is a re-run on the same day, else append.
    lines = [rec for rec in lines if rec.get("date") != day]
    lines.append(record)
    lines = lines[-7:]

    path.write_text("\n".join(json.dumps(rec) for rec in lines) + "\n")


def load_history(incoming_dir: Path, machine: str) -> list[dict]:
    path = history_path(incoming_dir, machine)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


@dataclass
class WeeklyMachineRollup:
    machine: str
    colour: Colour
    days: list[tuple[str, Colour, list[tuple[Colour, str]]]]  # (date, day-colour, rows)


def build_weekly_rollup(incoming_dir: Path, entries: list[MachineReportEntry]) -> list[WeeklyMachineRollup]:
    """Worst-state-per-day rollup over whatever history has accumulated so
    far (1 to 7 days) — live from day one, not gated on a full week passing.
    """
    rollups = []
    for e in entries:
        history = load_history(incoming_dir, e.machine)
        days = []
        for rec in history:
            day_colour = Colour[rec["colour"]]
            rows = [(Colour[c], d) for c, d in rec["rows"]]
            days.append((rec["date"], day_colour, rows))
        overall = worst([d[1] for d in days]) if days else e.colour
        rollups.append(WeeklyMachineRollup(machine=e.machine, colour=overall, days=days))
    return rollups


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


def build_plaintext_body(
    entries: list[MachineReportEntry],
    weekly: bool,
    rollups: list[WeeklyMachineRollup] | None = None,
) -> str:
    now = datetime.now(UTC)
    kind = "Weekly" if weekly else "Daily"
    lines = [f"SysAdmin {kind} Report — {now.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    if weekly and rollups:
        for r in rollups:
            lines.append(f"{r.colour.emoji} {r.machine} — worst state over last {len(r.days)} day(s)")
            for day, day_colour, rows in r.days:
                lines.append(f"  {day} [{day_colour.name}]")
                for row_colour, detail in rows:
                    lines.append(f"    {row_colour.name}: {detail}")
            lines.append("")
        return "\n".join(lines)
    for e in entries:
        lines.append(f"{e.colour.emoji} {e.machine}")
        for row_colour, detail in e.summary_rows:
            lines.append(f"    {row_colour.name}: {detail}")
        lines.append("")
    return "\n".join(lines)


_PILL_COLOUR = {Colour.RED: "#c0392b", Colour.YELLOW: "#f1c40f", Colour.GREEN: "#2ecc71"}
_STATE_LABEL = {Colour.RED: "RED", Colour.YELLOW: "WARN", Colour.GREEN: "OK"}


def build_html_body(
    entries: list[MachineReportEntry],
    weekly: bool,
    rollups: list[WeeklyMachineRollup] | None = None,
) -> str:
    """Multipart HTML body matching the existing Night Watch email's visual
    language exactly: coloured header bar, one pill-table row PER CHECK
    (not per machine) — see ~/.local/bin/night-watch::send_report on Alghul.
    A machine sub-header row separates each machine's block of checks.

    Weekly mode renders a day sub-header per accumulated day (1-7, whatever
    history exists so far) under each machine, worst-state-per-day.
    """
    now = datetime.now(UTC)
    kind = "Weekly" if weekly else "Daily"

    if weekly and rollups:
        overall = worst([r.colour for r in rollups])
        bar_colour = _PILL_COLOUR[overall]
        rows = []
        for r in rollups:
            rows.append(
                '<tr><td colspan="2" style="padding:10px 10px 4px;font-weight:700;'
                f'font-size:13px">{r.machine}</td></tr>'
            )
            for day, day_colour, day_rows in r.days:
                rows.append(
                    '<tr><td colspan="2" style="padding:4px 10px 2px 20px;'
                    f'font-weight:600;font-size:12px;color:#555">{day}</td></tr>'
                )
                for row_colour, detail in day_rows:
                    pill = _PILL_COLOUR[row_colour]
                    state = _STATE_LABEL[row_colour]
                    rows.append(
                        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #ddd;'
                        f'text-align:center"><span style="background:{pill};color:#000;'
                        f'padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px">'
                        f"{state}</span></td>"
                        f'<td style="padding:6px 10px;border-bottom:1px solid #ddd;'
                        f'font-family:monospace;font-size:12px">{detail}</td></tr>'
                    )
        return (
            '<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;'
            'color:#222;max-width:720px">\n'
            f'<div style="background:{bar_colour};color:#fff;padding:10px 14px;'
            f'border-radius:6px;font-weight:700">SysAdmin — {kind} Report — '
            f"{_STATE_LABEL[overall]}</div>\n"
            f'<p style="color:#666;font-size:13px">ALL MACHINES · '
            f'{now.strftime("%Y-%m-%d %H:%M")} UTC</p>\n'
            '<table style="border-collapse:collapse;width:100%;font-size:13px">'
            '<tr style="background:#f4f4f4"><th style="padding:6px 10px;width:110px">'
            'Status</th><th style="text-align:left;padding:6px 10px">Check</th></tr>'
            + "".join(rows)
            + '</table><p style="color:#999;font-size:11px;margin-top:14px">'
            "SysAdmin fleet report · Wolf · 09:00 UTC · daily only when not green, "
            "weekly every Monday</p></body></html>"
        )

    overall = worst([e.colour for e in entries])
    bar_colour = _PILL_COLOUR[overall]

    rows = []
    for e in entries:
        rows.append(
            '<tr><td colspan="2" style="padding:10px 10px 4px;font-weight:700;'
            f'font-size:13px">{e.machine}</td></tr>'
        )
        for row_colour, detail in e.summary_rows:
            pill = _PILL_COLOUR[row_colour]
            state = _STATE_LABEL[row_colour]
            rows.append(
                f'<tr><td style="padding:6px 10px;border-bottom:1px solid #ddd;'
                f'text-align:center"><span style="background:{pill};color:#000;'
                f'padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px">'
                f"{state}</span></td>"
                f'<td style="padding:6px 10px;border-bottom:1px solid #ddd;'
                f'font-family:monospace;font-size:12px">{detail}</td></tr>'
            )

    return (
        '<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;'
        'color:#222;max-width:720px">\n'
        f'<div style="background:{bar_colour};color:#fff;padding:10px 14px;'
        f'border-radius:6px;font-weight:700">SysAdmin — {kind} Report — '
        f"{_STATE_LABEL[overall]}</div>\n"
        f'<p style="color:#666;font-size:13px">ALL MACHINES · '
        f'{now.strftime("%Y-%m-%d %H:%M")} UTC</p>\n'
        '<table style="border-collapse:collapse;width:100%;font-size:13px">'
        '<tr style="background:#f4f4f4"><th style="padding:6px 10px;width:110px">'
        'Status</th><th style="text-align:left;padding:6px 10px">Check</th></tr>'
        + "".join(rows)
        + '</table><p style="color:#999;font-size:11px;margin-top:14px">'
        "SysAdmin fleet report · Wolf · 09:00 UTC · daily only when not green, "
        "weekly every Monday</p></body></html>"
    )
