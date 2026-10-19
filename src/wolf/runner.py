"""Orchestrates one full Wolf run on a machine: both guards, cache trim,
reaping, Docker prune, health checks, reboot gate, updates check, and
delivery of the structured result.
"""

from __future__ import annotations

from wolf import caches, docker_prune, health, reaper, reboot, updates
from wolf.colour import Colour, worst
from wolf.config import MachineConfig
from wolf.locking import AlreadyRunningError, active_tooling, run_lock
from wolf.result import RunResult, deliver, finalize, new_run_result


def run(config: MachineConfig) -> RunResult:
    lock_dir = config.state_dir / "wolf.lock"
    config.state_dir.mkdir(parents=True, exist_ok=True)

    result, _ = new_run_result(config.name)

    try:
        with run_lock(lock_dir):
            _run_body(config, result)
    except AlreadyRunningError as exc:
        result.notes.append(str(exc))
        result.colour = Colour.YELLOW

    finalize(result)
    status = deliver(result, config.state_dir, config.delivery)
    result.notes.append(status)
    return result


def _run_body(config: MachineConfig, result: RunResult) -> None:
    colours: list[Colour] = []

    # 1. Cache trimming — skipped entirely while installs/builds are active.
    busy = active_tooling()
    if busy:
        result.notes.append(f"cache trim skipped: active tooling detected ({busy})")
    else:
        cap_bytes = int(config.cache.cap_gb * (1000**3))
        trims = caches.trim_to_cap(config.cache.families, cap_bytes)
        result.cache_freed_bytes = sum(t.freed_bytes for t in trims)
        result.cache_total_bytes_after = caches.total_cache_bytes(config.cache.families)
        result.notes.extend(f"trimmed {t.family}: {t.freed_bytes} bytes freed" for t in trims)

    # 2. Stale process reaping.
    candidates = reaper.find_candidates()
    reaped = reaper.reap(candidates)
    result.processes_reaped = [f"pid={c.pid} reason={c.reason} cmd={c.command}" for c in reaped]

    # 3. Docker image pruning.
    if config.docker.enabled:
        cap_bytes = int(config.docker.cap_gb * (1000**3))
        prune_result = docker_prune.prune_to_cap(cap_bytes)
        result.docker_images_removed = prune_result.images_removed
        result.docker_freed_bytes = prune_result.freed_bytes

    # 4. Service health checks.
    checks = health.run_night_watch_equivalent_checks()
    result.services = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks]
    if any(not c.ok for c in checks):
        colours.append(Colour.YELLOW)

    # 5. Pending updates.
    update_status = updates.pending_updates()
    result.updates_pending = update_status.pending_count
    result.updates_summary = update_status.pending_summary

    # 6. Reboot logic (includes the idle-chat gate).
    reboot_status = reboot.reboot_status(config.reboot)
    result.reboot = {
        "colour": reboot_status.colour.name,
        "required_by_updates": reboot_status.reboot_required_by_updates,
        "days_since_last_reboot": reboot_status.days_since_last_reboot,
        "attempted": reboot_status.reboot_attempted,
        "performed": reboot_status.reboot_performed,
        "reason": reboot_status.reason,
    }
    colours.append(reboot_status.colour)

    result.colour = worst(colours)
