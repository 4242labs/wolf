from pathlib import Path

from wolf import caches


def _touch(path: Path, size_bytes: int, mtime_offset_seconds: float = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * size_bytes)
    import os
    import time

    now = time.time()
    os.utime(path, (now + mtime_offset_seconds, now + mtime_offset_seconds))


def test_family_size_bytes_sums_known_dirs(tmp_path, monkeypatch):
    home = tmp_path
    _touch(home / ".npm" / "a.bin", 1000)
    _touch(home / ".npm" / "b.bin", 2000)
    assert caches.family_size_bytes("npm", home=home) == 3000


def test_trim_to_cap_removes_oldest_first(tmp_path):
    home = tmp_path
    # Oldest file first (further back in time), newest last.
    _touch(home / ".cache" / "uv" / "old.bin", 1000, mtime_offset_seconds=-1000)
    _touch(home / ".cache" / "uv" / "mid.bin", 1000, mtime_offset_seconds=-500)
    _touch(home / ".cache" / "uv" / "new.bin", 1000, mtime_offset_seconds=0)

    cap_bytes = 1000  # must free ~2000 of the 3000 bytes present
    results = caches.trim_to_cap(("uv",), cap_bytes, home=home)

    assert results, "expected at least one trim result"
    remaining = caches.family_size_bytes("uv", home=home)
    assert remaining <= cap_bytes + 1000  # within one file's worth of the cap
    # The newest file should survive; the oldest should be gone.
    assert not (home / ".cache" / "uv" / "old.bin").exists()
    assert (home / ".cache" / "uv" / "new.bin").exists()


def test_trim_to_cap_noop_when_under_cap(tmp_path):
    home = tmp_path
    _touch(home / ".npm" / "a.bin", 100)
    results = caches.trim_to_cap(("npm",), cap_bytes=10_000, home=home)
    assert results == []
    assert (home / ".npm" / "a.bin").exists()


def test_trim_to_cap_never_touches_unrelated_dirs(tmp_path):
    home = tmp_path
    _touch(home / ".npm" / "a.bin", 5000, mtime_offset_seconds=-1000)
    # A directory NOT in FAMILY_DIRS, simulating a venv / project dir.
    _touch(home / "myproject" / "venv" / "lib" / "site.py", 5000)

    caches.trim_to_cap(("npm",), cap_bytes=0, home=home)

    assert not (home / ".npm" / "a.bin").exists()
    assert (home / "myproject" / "venv" / "lib" / "site.py").exists()
