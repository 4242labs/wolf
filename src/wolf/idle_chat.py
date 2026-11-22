"""Idle-chat signal for the reboot gate.

Resolved decision (42L-2204, amended after 2026-11-22 incident): a machine
counts as "active" if EITHER of the following holds:
  1. active_sessions.json lists an entry whose pid is a live process
     (direct liveness check — catches sessions that are open but quiet,
     which never touch the file's mtime and were previously missed); or
  2. any known session-state file's mtime is within the configured window
     (default 24h) — kept as a fallback signal/for sessions.json, which
     carries no per-session pid to check directly.

Incident: on 2026-11-22 Wolf rebooted Alghul while 5 Hermes sessions were
genuinely open, killing all of them plus every Docker container, because
active_sessions.json's mtime was >24h stale even though its "entries" list
still named a live pid — mtime went stale without the session closing.
The pid-liveness check above is the real signal; mtime is now secondary.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Hermes session-state files, in the order checked. First existing file wins
# (its mtime is the signal); if none exist, the machine is treated as idle.
SESSION_STATE_CANDIDATES = (
    Path.home() / ".hermes" / "runtime" / "active_sessions.json",
    Path.home() / ".hermes" / "sessions" / "sessions.json",
)


def _has_live_pid(path: Path) -> bool:
    """True if `path` parses as JSON with an "entries" list containing a
    still-running pid. Any parse/IO error or shape mismatch is treated as
    "no live pid found here", not as an error — mtime fallback still runs.
    """
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False

    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return False

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("pid")
        if not isinstance(pid, int):
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            # Process exists but is owned by someone else — still alive.
            return True
        else:
            return True
    return False


def is_active(idle_hours: float = 24.0, now: float | None = None) -> bool:
    """True if a session-state file shows a live pid, or (fallback) any
    known session-state file's mtime is within idle_hours of now.
    """
    for path in SESSION_STATE_CANDIDATES:
        if path.exists() and _has_live_pid(path):
            return True

    now = now if now is not None else time.time()
    threshold_seconds = idle_hours * 3600

    for path in SESSION_STATE_CANDIDATES:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if now - mtime < threshold_seconds:
            return True
    return False
