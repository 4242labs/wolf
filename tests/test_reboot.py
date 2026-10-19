from wolf.colour import Colour, worst
from wolf.config import RebootConfig
from wolf.reboot import reboot_status


def test_worst_colour_picks_most_severe():
    assert worst([Colour.GREEN, Colour.YELLOW, Colour.RED]) == Colour.RED
    assert worst([Colour.GREEN]) == Colour.GREEN
    assert worst([]) == Colour.GREEN


def test_reboot_not_due_is_green(monkeypatch):
    monkeypatch.setattr("wolf.reboot.reboot_required_by_updates", lambda: False)
    monkeypatch.setattr("wolf.reboot.days_since_boot", lambda: 1.0)
    status = reboot_status(RebootConfig(allowed=True, yellow_days=3, red_days=5))
    assert status.colour == Colour.GREEN
    assert status.reboot_attempted is False


def test_reboot_yellow_at_threshold(monkeypatch):
    monkeypatch.setattr("wolf.reboot.reboot_required_by_updates", lambda: False)
    monkeypatch.setattr("wolf.reboot.days_since_boot", lambda: 3.5)
    status = reboot_status(RebootConfig(allowed=True, yellow_days=3, red_days=5))
    assert status.colour == Colour.YELLOW
    assert status.reboot_attempted is False


def test_reboot_due_and_idle_reboots(monkeypatch):
    monkeypatch.setattr("wolf.reboot.reboot_required_by_updates", lambda: False)
    monkeypatch.setattr("wolf.reboot.days_since_boot", lambda: 6.0)
    monkeypatch.setattr("wolf.reboot.is_active", lambda hours: False)
    monkeypatch.setattr("wolf.reboot.perform_reboot", lambda: "rebooted")
    status = reboot_status(RebootConfig(allowed=True, yellow_days=3, red_days=5))
    assert status.reboot_attempted is True
    assert status.reboot_performed is True


def test_reboot_due_but_chat_active_defers(monkeypatch):
    monkeypatch.setattr("wolf.reboot.reboot_required_by_updates", lambda: False)
    monkeypatch.setattr("wolf.reboot.days_since_boot", lambda: 6.0)
    monkeypatch.setattr("wolf.reboot.is_active", lambda hours: True)
    status = reboot_status(RebootConfig(allowed=True, yellow_days=3, red_days=5))
    assert status.reboot_attempted is False
    assert "deferred" in status.reason
    assert status.colour == Colour.RED  # still due, still red


def test_reboot_due_but_not_allowed_is_report_only(monkeypatch):
    monkeypatch.setattr("wolf.reboot.reboot_required_by_updates", lambda: False)
    monkeypatch.setattr("wolf.reboot.days_since_boot", lambda: 6.0)
    status = reboot_status(RebootConfig(allowed=False, yellow_days=3, red_days=5))
    assert status.reboot_attempted is False
    assert "not allowed" in status.reason
    assert status.colour == Colour.RED


def test_reboot_required_by_updates_forces_red(monkeypatch):
    monkeypatch.setattr("wolf.reboot.reboot_required_by_updates", lambda: True)
    monkeypatch.setattr("wolf.reboot.days_since_boot", lambda: 0.5)
    monkeypatch.setattr("wolf.reboot.is_active", lambda hours: True)
    status = reboot_status(RebootConfig(allowed=True, yellow_days=3, red_days=5))
    assert status.colour == Colour.RED
    assert status.reboot_required_by_updates is True
