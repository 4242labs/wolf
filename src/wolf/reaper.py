"""Stale / orphaned MCP, Playwright, and chrome-devtools process reaping.

Ported from stale-mcp-reaper.sh: a process matching the agent-tooling pattern
is a candidate for termination only if it is old enough AND either orphaned
(ppid == 1) or its parent is stopped (state starts with 'T'). Agent root
processes themselves are never matched or terminated.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

MIN_AGE_SECONDS = 900
PROCESS_PATTERN = re.compile(r"(mcp|playwright|chrome-devtools)")


@dataclass
class ReapCandidate:
    pid: int
    ppid: int
    age_seconds: int
    reason: str
    command: str


def _parse_etime(value: str) -> int:
    """Parse ps's etime format: [[dd-]hh:]mm:ss."""
    days = 0
    rest = value
    if "-" in value:
        days_str, rest = value.split("-", 1)
        days = int(days_str)
    parts = rest.split(":")
    parts = [int(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, seconds = parts[-3], parts[-2], parts[-1]
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _parent_state(ppid: int) -> str:
    try:
        out = subprocess.run(
            ["ps", "-p", str(ppid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return out.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def find_candidates(min_age_seconds: int = MIN_AGE_SECONDS) -> list[ReapCandidate]:
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,etime=,stat=,command="],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    candidates: list[ReapCandidate] = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid_s, ppid_s, etime_s, _stat_s, command = parts
        if not (pid_s.isdigit() and ppid_s.isdigit()):
            continue
        if not PROCESS_PATTERN.search(command):
            continue

        try:
            age = _parse_etime(etime_s)
        except ValueError:
            continue
        if age < min_age_seconds:
            continue

        pid, ppid = int(pid_s), int(ppid_s)
        reason = ""
        if ppid == 1:
            reason = "orphaned"
        else:
            parent_state = _parent_state(ppid)
            if parent_state.startswith("T"):
                reason = "parent-stopped"
        if not reason:
            continue

        candidates.append(
            ReapCandidate(pid=pid, ppid=ppid, age_seconds=age, reason=reason, command=command)
        )
    return candidates


def reap(candidates: list[ReapCandidate]) -> list[ReapCandidate]:
    """Send SIGTERM to each candidate. Returns the ones successfully signalled."""
    terminated: list[ReapCandidate] = []
    for c in candidates:
        try:
            subprocess.run(["kill", "-TERM", str(c.pid)], capture_output=True, check=False)
            terminated.append(c)
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    return terminated
