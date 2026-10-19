import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wolf.colour import Colour
from wolf.report.builder import (
    MachineReportEntry,
    append_history,
    build_html_body,
    build_machine_entry,
    build_plaintext_body,
    build_subject,
    build_weekly_rollup,
    is_weekly_day,
    load_history,
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


def test_append_and_load_history_round_trips(tmp_path):
    entry = MachineReportEntry("darkseid", Colour.GREEN, "2026-10-19T06:00:00+00:00", Colour.GREEN, ["ok"])
    append_history(tmp_path, entry, now=datetime(2026, 10, 19, 7, tzinfo=UTC))
    history = load_history(tmp_path, "darkseid")
    assert len(history) == 1
    assert history[0]["date"] == "2026-10-19"
    assert history[0]["colour"] == "GREEN"


def test_append_history_same_day_replaces_not_duplicates(tmp_path):
    entry1 = MachineReportEntry("darkseid", Colour.GREEN, None, Colour.GREEN, ["first"])
    entry2 = MachineReportEntry("darkseid", Colour.RED, None, Colour.RED, ["second"])
    now = datetime(2026, 10, 19, 7, tzinfo=UTC)
    append_history(tmp_path, entry1, now=now)
    append_history(tmp_path, entry2, now=now)
    history = load_history(tmp_path, "darkseid")
    assert len(history) == 1
    assert history[0]["colour"] == "RED"


def test_append_history_keeps_last_seven_days(tmp_path):
    for day in range(1, 11):
        entry = MachineReportEntry("alghul", Colour.GREEN, None, Colour.GREEN, [f"day {day}"])
        append_history(tmp_path, entry, now=datetime(2026, 10, day, tzinfo=UTC))
    history = load_history(tmp_path, "alghul")
    assert len(history) == 7
    assert history[0]["date"] == "2026-10-04"
    assert history[-1]["date"] == "2026-10-10"


def test_weekly_rollup_works_from_a_single_accumulated_day(tmp_path):
    """No artificial 7-day wait: the rollup must render real data starting
    from the very first day history exists, not just once a week has passed.
    """
    entry = MachineReportEntry("darkseid", Colour.YELLOW, None, Colour.YELLOW, ["cache high"])
    append_history(tmp_path, entry, now=datetime(2026, 10, 19, 6, tzinfo=UTC))

    entries = [entry]
    rollups = build_weekly_rollup(tmp_path, entries)
    assert len(rollups) == 1
    assert len(rollups[0].days) == 1
    assert rollups[0].colour == Colour.YELLOW

    html = build_html_body(entries, weekly=True, rollups=rollups)
    assert "2026-10-19" in html
    assert "cache high" in html

    text = build_plaintext_body(entries, weekly=True, rollups=rollups)
    assert "2026-10-19" in text
    assert "cache high" in text


def test_weekly_rollup_worst_state_across_multiple_days(tmp_path):
    green = MachineReportEntry("darkseid", Colour.GREEN, None, Colour.GREEN, ["ok"])
    red = MachineReportEntry("darkseid", Colour.RED, None, Colour.RED, ["disk full"])
    append_history(tmp_path, green, now=datetime(2026, 10, 18, tzinfo=UTC))
    append_history(tmp_path, red, now=datetime(2026, 10, 19, tzinfo=UTC))

    rollups = build_weekly_rollup(tmp_path, [green])
    assert rollups[0].colour == Colour.RED
    assert len(rollups[0].days) == 2
