"""Idle-chat signal for the reboot gate.

Resolved decision (42L-2204): a machine counts as "active" if any Hermes
session-state file on that machine was modified within the configured
window (default 24h). Checked per-machine, scoped to local session state —
not a global/cross-machine signal. This matches how sessions already
persist state (~/.hermes/runtime/active_sessions.json, ~/.hermes/sessions/),
so no new mechanism is introduced.
"""

from __future__ import annotations

import time
from pathlib import Path

# Hermes session-state files, in the order checked. First existing file wins
# (its mtime is the signal); if none exist, the machine is treated as idle.
SESSION_STATE_CANDIDATES = (
    Path.home() / ".hermes" / "runtime" / "active_sessions.json",
    Path.home() / ".hermes" / "sessions" / "sessions.json",
)


def is_active(idle_hours: float = 24.0, now: float | None = None) -> bool:
    """True if any known session-state file's mtime is within idle_hours of now."""
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
