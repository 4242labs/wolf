from pathlib import Path

from wolf import caches

# `du`-based sizing (the fast path) rounds to the filesystem's own allocation
# unit, which differs by platform and includes directory-entry overhead
# (macOS APFS vs Linux ext4/tmpfs report different totals for the same file
# sizes). Assertions here check behavior — relative growth, zero vs nonzero,
# which files survive a trim — never an exact byte count against `du`'s
# platform-dependent output.
_FILE_SIZE = 100_000  # large enough that allocation overhead is a rounding error


def _touch(path: Path, size_bytes: int = _FILE_SIZE, mtime_offset_seconds: float = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * size_bytes)
    import os
    import time

    now = time.time()
    os.utime(path, (now + mtime_offset_seconds, now + mtime_offset_seconds))


def test_family_size_bytes_sums_known_dirs(tmp_path):
    home = tmp_path
    _touch(home / ".npm" / "a.bin")
    one_file = caches.family_size_bytes("npm", home=home)
    _touch(home / ".npm" / "b.bin")
    two_files = caches.family_size_bytes("npm", home=home)
    assert one_file > 0
    assert two_files > one_file


def test_trim_to_cap_removes_oldest_first(tmp_path):
    home = tmp_path
    # Oldest file first (further back in time), newest last.
    _touch(home / ".cache" / "uv" / "old.bin", mtime_offset_seconds=-1000)
    _touch(home / ".cache" / "uv" / "mid.bin", mtime_offset_seconds=-500)
    _touch(home / ".cache" / "uv" / "new.bin", mtime_offset_seconds=0)

    total = caches.family_size_bytes("uv", home=home)
    # Cap set to free roughly one file's worth (allowing for `du`'s
    # allocation-unit rounding), so only the oldest file should go.
    cap_bytes = total - (_FILE_SIZE // 2)
    results = caches.trim_to_cap(("uv",), cap_bytes, home=home)

    assert results, "expected at least one trim result"
    remaining = caches.family_size_bytes("uv", home=home)
    assert remaining < total
    # The oldest file is removed first; the newest two survive.
    assert not (home / ".cache" / "uv" / "old.bin").exists()
    assert (home / ".cache" / "uv" / "new.bin").exists()


def test_trim_to_cap_noop_when_under_cap(tmp_path):
    home = tmp_path
    _touch(home / ".npm" / "a.bin", size_bytes=100)
    results = caches.trim_to_cap(("npm",), cap_bytes=10 * _FILE_SIZE, home=home)
    assert results == []
    assert (home / ".npm" / "a.bin").exists()


def test_trim_to_cap_never_touches_unrelated_dirs(tmp_path):
    home = tmp_path
    _touch(home / ".npm" / "a.bin", mtime_offset_seconds=-1000)
    # A directory NOT in FAMILY_DIRS, simulating a venv / project dir.
    _touch(home / "myproject" / "venv" / "lib" / "site.py")

    caches.trim_to_cap(("npm",), cap_bytes=0, home=home)

    assert not (home / ".npm" / "a.bin").exists()
    assert (home / "myproject" / "venv" / "lib" / "site.py").exists()
