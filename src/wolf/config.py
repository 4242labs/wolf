"""Per-machine settings. Kept OUTSIDE the repo (no machine names/addresses/credentials here);
this module only defines the shape and loads whatever path is given at runtime.

See settings.example.yaml for the documented example shipped in the repo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_SETTINGS_ENV_VAR = "WOLF_SETTINGS"
DEFAULT_SETTINGS_PATH = Path("/etc/wolf/settings.yaml")
USER_SETTINGS_PATH = Path.home() / ".config/wolf/settings.yaml"


@dataclass(frozen=True)
class RebootConfig:
    allowed: bool = True
    yellow_days: float = 3.0
    red_days: float = 5.0
    idle_chat_hours: float = 24.0


@dataclass(frozen=True)
class MissedRunConfig:
    yellow_days: float = 3.0
    red_days: float = 5.0


@dataclass(frozen=True)
class CacheConfig:
    # Package-cache cap, in GiB. Trimmed to this cap regardless of free disk space.
    cap_gb: float = 50.0
    # Oldest-first trim across these cache families. Keys match caches.FAMILIES.
    families: tuple[str, ...] = (
        "npm",
        "npx",
        "pnpm",
        "uv",
        "pip",
        "poetry",
        "homebrew",
        "cargo",
    )


@dataclass(frozen=True)
class DockerConfig:
    enabled: bool = False
    cap_gb: float = 30.0


@dataclass(frozen=True)
class DeliveryConfig:
    # SSH push target: Darkseid -> Alghul. Empty host means "write locally only"
    # (used on the machine that IS the delivery target, e.g. Alghul itself).
    host: str = ""
    user: str = ""
    remote_path: str = ""
    ssh_identity: str = ""


@dataclass(frozen=True)
class MachineConfig:
    name: str
    run_time_utc: str = "06:00"
    cache: CacheConfig = field(default_factory=CacheConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    reboot: RebootConfig = field(default_factory=RebootConfig)
    missed_run: MissedRunConfig = field(default_factory=MissedRunConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    # Where this machine's own run results + locks + logs live.
    state_dir: Path = Path.home() / ".local/share/wolf"


def _reboot_from_dict(d: dict) -> RebootConfig:
    return RebootConfig(
        allowed=d.get("allowed", True),
        yellow_days=float(d.get("yellow_days", 3.0)),
        red_days=float(d.get("red_days", 5.0)),
        idle_chat_hours=float(d.get("idle_chat_hours", 24.0)),
    )


def _missed_run_from_dict(d: dict) -> MissedRunConfig:
    return MissedRunConfig(
        yellow_days=float(d.get("yellow_days", 3.0)),
        red_days=float(d.get("red_days", 5.0)),
    )


def _cache_from_dict(d: dict) -> CacheConfig:
    kwargs = {}
    if "cap_gb" in d:
        kwargs["cap_gb"] = float(d["cap_gb"])
    if "families" in d:
        kwargs["families"] = tuple(d["families"])
    return CacheConfig(**kwargs)


def _docker_from_dict(d: dict) -> DockerConfig:
    return DockerConfig(
        enabled=d.get("enabled", False),
        cap_gb=float(d.get("cap_gb", 30.0)),
    )


def _delivery_from_dict(d: dict) -> DeliveryConfig:
    return DeliveryConfig(
        host=d.get("host", ""),
        user=d.get("user", ""),
        remote_path=d.get("remote_path", ""),
        ssh_identity=d.get("ssh_identity", ""),
    )


def load_machine_config(path: Path | None = None) -> MachineConfig:
    """Load a MachineConfig from a YAML settings file.

    Resolution order: explicit `path` argument, then $WOLF_SETTINGS, then
    ~/.config/wolf/settings.yaml, then /etc/wolf/settings.yaml. Raises
    FileNotFoundError if none resolve.
    """
    if path is not None:
        candidate = path
    elif DEFAULT_SETTINGS_ENV_VAR in os.environ:
        candidate = Path(os.environ[DEFAULT_SETTINGS_ENV_VAR])
    elif USER_SETTINGS_PATH.exists():
        candidate = USER_SETTINGS_PATH
    else:
        candidate = DEFAULT_SETTINGS_PATH
    if not candidate.exists():
        raise FileNotFoundError(f"Wolf settings file not found: {candidate}")

    raw = yaml.safe_load(candidate.read_text()) or {}
    return parse_machine_config(raw)


def parse_machine_config(raw: dict) -> MachineConfig:
    if "name" not in raw:
        raise ValueError("Wolf settings must set 'name' (the machine's name)")

    kwargs: dict = {"name": raw["name"]}
    if "run_time_utc" in raw:
        kwargs["run_time_utc"] = raw["run_time_utc"]
    if "cache" in raw:
        kwargs["cache"] = _cache_from_dict(raw["cache"])
    if "docker" in raw:
        kwargs["docker"] = _docker_from_dict(raw["docker"])
    if "reboot" in raw:
        kwargs["reboot"] = _reboot_from_dict(raw["reboot"])
    if "missed_run" in raw:
        kwargs["missed_run"] = _missed_run_from_dict(raw["missed_run"])
    if "delivery" in raw:
        kwargs["delivery"] = _delivery_from_dict(raw["delivery"])
    if "state_dir" in raw:
        kwargs["state_dir"] = Path(raw["state_dir"]).expanduser()

    return MachineConfig(**kwargs)
