"""Structured per-run result and its delivery to Alghul.

Delivery (resolved decision, 42L-2204): Darkseid pushes its structured run
result to Alghul over SSH; Dagu then reads results from Alghul's local
filesystem. A machine with no delivery.host configured (i.e. Alghul itself,
or any machine that IS the aggregation point) writes locally only.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from wolf.colour import Colour
from wolf.config import DeliveryConfig


@dataclass
class RunResult:
    machine: str
    started_at: str
    finished_at: str
    colour: Colour
    cache_freed_bytes: int = 0
    cache_total_bytes_after: int = 0
    processes_reaped: list[str] = field(default_factory=list)
    docker_images_removed: list[str] = field(default_factory=list)
    docker_freed_bytes: int = 0
    services: list[dict] = field(default_factory=list)
    reboot: dict = field(default_factory=dict)
    updates_pending: int = 0
    updates_summary: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["colour"] = self.colour.name
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def new_run_result(machine: str) -> tuple[RunResult, str]:
    """Create a RunResult with started_at set to now; returns (result, started_iso)."""
    started = datetime.now(UTC).isoformat()
    return (
        RunResult(machine=machine, started_at=started, finished_at="", colour=Colour.GREEN),
        started,
    )


def finalize(result: RunResult) -> RunResult:
    result.finished_at = datetime.now(UTC).isoformat()
    return result


def write_local(result: RunResult, state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / f"run-{result.started_at.replace(':', '').replace('+', 'Z')}.json"
    out_path.write_text(result.to_json())
    latest = state_dir / "latest.json"
    latest.write_text(result.to_json())
    return out_path


def deliver(result: RunResult, state_dir: Path, delivery: DeliveryConfig) -> str:
    """Write the result locally, then push to Alghul over SSH if delivery.host
    is configured. Returns a status string.
    """
    write_local(result, state_dir)

    if not delivery.host:
        return "written locally (no delivery host configured)"

    local_latest = state_dir / "latest.json"
    remote = f"{delivery.user}@{delivery.host}:{delivery.remote_path}/{result.machine}-latest.json"

    cmd = ["scp"]
    if delivery.ssh_identity:
        cmd += ["-i", delivery.ssh_identity]
    cmd += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(local_latest), remote]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return f"delivered to {delivery.host}"
        return f"delivery failed: {proc.stderr.strip()}"
    except FileNotFoundError:
        return "delivery failed: scp not found"
