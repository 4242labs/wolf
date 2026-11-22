import time

from wolf.idle_chat import is_active


def test_is_active_true_when_recent_mtime(tmp_path, monkeypatch):
    fake = tmp_path / "active_sessions.json"
    fake.write_text("{}")
    monkeypatch.setattr("wolf.idle_chat.SESSION_STATE_CANDIDATES", (fake,))
    assert is_active(idle_hours=24.0) is True


def test_is_active_false_when_stale(tmp_path, monkeypatch):
    import os

    fake = tmp_path / "active_sessions.json"
    fake.write_text("{}")
    old = time.time() - (48 * 3600)
    os.utime(fake, (old, old))
    monkeypatch.setattr("wolf.idle_chat.SESSION_STATE_CANDIDATES", (fake,))
    assert is_active(idle_hours=24.0) is False


def test_is_active_false_when_no_files_exist(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr("wolf.idle_chat.SESSION_STATE_CANDIDATES", (missing,))
    assert is_active(idle_hours=24.0) is False


def test_is_active_true_when_live_pid_despite_stale_mtime(tmp_path, monkeypatch):
    """Regression for the 2026-11-22 incident: file mtime stale (>24h) but
    its "entries" list still names a genuinely running pid — must be active.
    """
    import json
    import os

    fake = tmp_path / "active_sessions.json"
    fake.write_text(json.dumps({"entries": [{"pid": os.getpid()}]}))
    old = time.time() - (48 * 3600)
    os.utime(fake, (old, old))
    monkeypatch.setattr("wolf.idle_chat.SESSION_STATE_CANDIDATES", (fake,))
    assert is_active(idle_hours=24.0) is True


def test_is_active_false_when_stale_and_pid_dead(tmp_path, monkeypatch):
    """Stale mtime AND the listed pid no longer exists -> correctly idle."""
    import json
    import os
    import subprocess

    proc = subprocess.Popen(["true"])
    proc.wait()  # has already exited by now
    dead_pid = proc.pid
    fake = tmp_path / "active_sessions.json"
    fake.write_text(json.dumps({"entries": [{"pid": dead_pid}]}))
    old = time.time() - (48 * 3600)
    os.utime(fake, (old, old))
    monkeypatch.setattr("wolf.idle_chat.SESSION_STATE_CANDIDATES", (fake,))
    assert is_active(idle_hours=24.0) is False
