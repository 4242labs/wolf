"""Two distinct, independent guards ported from safe-cache-cleanup.sh.

1. run_lock(): an mkdir-based lock directory preventing two Wolf invocations
   from overlapping on the same machine (source: safe-cache-cleanup.sh lines
   14-17, the `mkdir "$lock_dir"` / trap cleanup pattern).
2. active_tooling(): a pgrep-based check that reports whether a package
   manager or build tool is currently running, so cache trimming can be
   skipped while one is active (source: safe-cache-cleanup.sh lines 26-29,
   the `pgrep -f '(npm|npx|poetry|pip|brew|cargo|rustc)...|playwright'` guard).

These solve different problems (overlap prevention vs. skip-while-building)
and must not be collapsed into one guard.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Matches safe-cache-cleanup.sh's pattern, extended with rustc/playwright
# exactly as that script does.
ACTIVE_TOOLING_PATTERN = re.compile(
    r"(^|/)(npm|npx|poetry|pip|brew|cargo|rustc)( |$)|playwright"
)


class AlreadyRunningError(RuntimeError):
    """Raised by run_lock() when another Wolf invocation already holds the lock."""


@contextmanager
def run_lock(lock_dir: Path) -> Iterator[None]:
    """Overlap guard: mkdir-based lock, ported from safe-cache-cleanup.sh.

    Raises AlreadyRunningError if the lock directory already exists.
    """
    try:
        lock_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise AlreadyRunningError(f"another Wolf run holds the lock: {lock_dir}") from exc
    try:
        yield
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass


def active_tooling() -> str | None:
    """Skip-while-building guard, ported from safe-cache-cleanup.sh.

    Returns the matching process command line if a package manager or build
    tool is currently running, else None. Cache trimming should be skipped
    (not Wolf's whole run — service checks, reaping, etc. still proceed)
    when this returns non-None.
    """
    try:
        out = subprocess.run(
            ["ps", "-axo", "command="],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    for line in out.splitlines():
        if ACTIVE_TOOLING_PATTERN.search(line):
            return line.strip()
    return None
