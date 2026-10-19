"""Docker image pruning: unused images trimmed oldest-first to a configured cap."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass
class DockerPruneResult:
    freed_bytes: int
    images_removed: list[str]


def docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _unused_images_oldest_first() -> list[dict]:
    """Images with no running or stopped container referencing them, oldest first."""
    try:
        out = subprocess.run(
            ["docker", "images", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    images = [json.loads(line) for line in out.splitlines() if line.strip()]

    try:
        used_out = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Image}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        used_out = ""
    used = {line.strip() for line in used_out.splitlines() if line.strip()}

    unused = [img for img in images if img.get("Repository:Tag", img.get("ID")) not in used]
    # docker images are already newest-first by default; CreatedAt string sorts
    # lexicographically only if ISO-shaped, so sort explicitly, oldest first.
    unused.sort(key=lambda i: i.get("CreatedAt", ""))
    return unused


def _size_to_bytes(size_str: str) -> int:
    """Parse docker's human size strings, e.g. '1.2GB', '340MB'."""
    size_str = size_str.strip()
    units = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    for suffix, mult in sorted(units.items(), key=lambda kv: -len(kv[0])):
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    return 0


def prune_to_cap(cap_bytes: int) -> DockerPruneResult:
    """Remove unused images, oldest first, until total image usage is at/below cap."""
    if not docker_available():
        return DockerPruneResult(freed_bytes=0, images_removed=[])

    try:
        df_out = subprocess.run(
            ["docker", "system", "df", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return DockerPruneResult(freed_bytes=0, images_removed=[])

    images_total_bytes = 0
    for line in df_out.splitlines():
        row = json.loads(line)
        if row.get("Type") == "Images":
            images_total_bytes = _size_to_bytes(row.get("Size", "0B"))
            break

    if images_total_bytes <= cap_bytes:
        return DockerPruneResult(freed_bytes=0, images_removed=[])

    over_by = images_total_bytes - cap_bytes
    removed: list[str] = []
    freed = 0

    for img in _unused_images_oldest_first():
        if over_by <= 0:
            break
        image_id = img.get("ID")
        size_bytes = _size_to_bytes(img.get("Size", "0B"))
        if not image_id:
            continue
        result = subprocess.run(
            ["docker", "rmi", image_id], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            removed.append(img.get("Repository:Tag", image_id))
            freed += size_bytes
            over_by -= size_bytes

    return DockerPruneResult(freed_bytes=freed, images_removed=removed)
