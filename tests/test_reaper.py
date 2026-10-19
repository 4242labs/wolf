from wolf.reaper import _parse_etime


def test_parse_etime_seconds_only():
    assert _parse_etime("45") == 45


def test_parse_etime_minutes_seconds():
    assert _parse_etime("12:30") == 12 * 60 + 30


def test_parse_etime_hours_minutes_seconds():
    assert _parse_etime("01:02:03") == 1 * 3600 + 2 * 60 + 3


def test_parse_etime_days():
    assert _parse_etime("2-03:04:05") == 2 * 86400 + 3 * 3600 + 4 * 60 + 5
