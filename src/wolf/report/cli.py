"""CLI entry point for the SysAdmin Daily/Weekly Report, invoked by Dagu.

Per-machine identity (which machines exist, their yellow/red missed-run
thresholds) comes from a small report-config YAML, kept outside the repo
like Wolf's own per-machine settings — see report-settings.example.yaml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from wolf.report.builder import (
    append_history,
    build_html_body,
    build_machine_entry,
    build_plaintext_body,
    build_subject,
    build_weekly_rollup,
    is_weekly_day,
    should_send_daily,
)
from wolf.report.mailer import send_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wolf-report")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Build but don't send")
    args = parser.parse_args(argv)

    raw = yaml.safe_load(args.config.read_text())
    incoming_dir = Path(raw["incoming_dir"]).expanduser()

    entries = [
        build_machine_entry(
            machine=m["name"],
            incoming_dir=incoming_dir,
            yellow_days=m.get("missed_run_yellow_days", 3),
            red_days=m.get("missed_run_red_days", 5),
        )
        for m in raw["machines"]
    ]

    weekly = is_weekly_day()
    send_it = weekly or should_send_daily(entries)

    # Append every run to history regardless of send/skip, so the weekly
    # rollup accumulates real days starting today — not gated on sends.
    for e in entries:
        if not args.dry_run:
            append_history(incoming_dir, e)

    if not send_it:
        print("wolf-report: all green, not Monday — nothing to send")
        return 0

    rollups = build_weekly_rollup(incoming_dir, entries) if weekly else None
    subject = build_subject(entries, weekly)
    body = build_plaintext_body(entries, weekly, rollups)
    html_body = build_html_body(entries, weekly, rollups)

    if args.dry_run:
        print(f"Subject: {subject}\n\n{body}")
        return 0

    send_report(subject, body, html_body)
    print(f"wolf-report: sent '{subject}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
