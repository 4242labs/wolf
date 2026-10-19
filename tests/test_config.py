from pathlib import Path

import pytest

from wolf.config import parse_machine_config


def test_parse_machine_config_minimal():
    cfg = parse_machine_config({"name": "darkseid"})
    assert cfg.name == "darkseid"
    assert cfg.cache.cap_gb == 50.0
    assert cfg.reboot.allowed is True


def test_parse_machine_config_full():
    raw = {
        "name": "alghul",
        "run_time_utc": "06:00",
        "cache": {"cap_gb": 20, "families": ["npm", "uv"]},
        "docker": {"enabled": True, "cap_gb": 30},
        "reboot": {"allowed": True, "yellow_days": 3, "red_days": 5, "idle_chat_hours": 24},
        "missed_run": {"yellow_days": 1, "red_days": 2},
        "delivery": {"host": "", "user": "", "remote_path": "", "ssh_identity": ""},
        "state_dir": "/tmp/wolf-state",
    }
    cfg = parse_machine_config(raw)
    assert cfg.cache.cap_gb == 20.0
    assert cfg.cache.families == ("npm", "uv")
    assert cfg.docker.enabled is True
    assert cfg.missed_run.yellow_days == 1.0
    assert cfg.state_dir == Path("/tmp/wolf-state")


def test_parse_machine_config_requires_name():
    with pytest.raises(ValueError):
        parse_machine_config({})
