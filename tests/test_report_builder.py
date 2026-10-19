import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wolf.colour import Colour
from wolf.report.builder import (
    build_machine_entry,
    build_subject,
    is_weekly_day,
    missed_run_colour,
    should_send_daily,
)


def _write_result(path: Path, colour: str, finished_at: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"colour": colour, "finished_at": finished_at}))


def test_missed_run_colour_thresholds():
    now = datetime(2026, 1, 10, tzinfo=UTC)
    recent = (now - timedelta(hours=1)).isoformat()
    yellow = (now - timedelta(days=4)).isoformat()
    red = (now - timedelta(days=6)).isoformat()

    assert missed_run_colour(recent, 3, 5, now) == Colour.GREEN
    assert missed_run_colour(yellow, 3, 5, now) == Colour.YELLOW
    assert missed_run_colour(red, 3, 5, now) == Colour.RED
    assert missed_run_colour(None, 3, 5, now) == Colour.RED


def test_build_machine_entry_reads_result(tmp_path):
    now = datetime.now(UTC)
    _write_result(tmp_path / "darkseid-latest.json", "GREEN", now.isoformat())
    entry = build_machine_entry("darkseid", tmp_path, yellow_days=3, red_days=5, now=now)
    assert entry.colour == Colour.GREEN
    assert entry.machine == "darkseid"


def test_build_machine_entry_missing_result_is_red(tmp_path):
    entry = build_machine_entry("ghost", tmp_path, yellow_days=3, red_days=5)
    assert entry.colour == Colour.RED
    assert "no run result found" in entry.summary_lines


def test_should_send_daily_only_when_not_all_green():
    from wolf.report.builder import MachineReportEntry

    all_green = [MachineReportEntry("a", Colour.GREEN, None, Colour.GREEN, [])]
    one_red = [
        MachineReportEntry("a", Colour.GREEN, None, Colour.GREEN, []),
        MachineReportEntry("b", Colour.RED, None, Colour.RED, []),
    ]
    assert should_send_daily(all_green) is False
    assert should_send_daily(one_red) is True


def test_is_weekly_day_monday_only():
    monday = datetime(2026, 10, 19, tzinfo=UTC)  # a Monday
    tuesday = datetime(2026, 10, 20, tzinfo=UTC)
    assert is_weekly_day(monday) is True
    assert is_weekly_day(tuesday) is False


def test_build_subject_names_worst_colour():
    from wolf.report.builder import MachineReportEntry

    entries = [
        MachineReportEntry("a", Colour.GREEN, None, Colour.GREEN, []),
        MachineReportEntry("b", Colour.RED, None, Colour.RED, []),
    ]
    subject = build_subject(entries, weekly=False)
    assert "Daily" in subject
    assert Colour.RED.emoji in subject
