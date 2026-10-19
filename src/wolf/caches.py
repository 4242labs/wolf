"""Package-cache trimming: oldest-first, to a configured cap, never touching
venvs, projects, models, build output, or user data.

Each family maps to a real, regenerable cache directory and a strategy for
freeing space from it. A family absent on a given machine (directory missing)
is silently skipped, not an error.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrimResult:
    family: str
    freed_bytes: int
    note: str = ""


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    du_bytes = _dir_size_via_du(path)
    if du_bytes is not None:
        return du_bytes
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def _dir_size_via_du(path: Path) -> int | None:
    """Fast path for sizing a cache directory: the system `du` binary walks
    the tree in C and is an order of magnitude faster than a Python
    rglob+stat loop over tens of thousands of small cache files. Falls back
    to None (caller does the slow walk) if `du` is unavailable or fails.
    """
    if shutil.which("du") is None:
        return None
    try:
        # -s: summary total only. -k: force 1024-byte blocks (consistent
        # output across BSD/macOS and GNU/Linux du, which default to
        # different block sizes otherwise).
        proc = subprocess.run(
            ["du", "-sk", str(path)], capture_output=True, text=True, check=False, timeout=60
        )
        if proc.returncode != 0:
            return None
        kib = int(proc.stdout.split()[0])
        return kib * 1024
    except (subprocess.SubprocessError, ValueError, IndexError, OSError):
        return None


def _oldest_first_trim(path: Path, target_bytes_to_free: int) -> int:
    """Delete files under `path`, oldest mtime first, until target_bytes_to_free
    have been freed or there is nothing left. Returns bytes actually freed.
    """
    if not path.exists():
        return 0

    entries: list[tuple[float, Path, int]] = []
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                st = p.stat()
                entries.append((st.st_mtime, p, st.st_size))
        except OSError:
            continue

    entries.sort(key=lambda e: e[0])  # oldest mtime first

    freed = 0
    for _, p, size in entries:
        if freed >= target_bytes_to_free:
            break
        try:
            p.unlink()
            freed += size
        except OSError:
            continue

    # Clean up now-empty directories left behind.
    for d in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass

    return freed


# -- Family definitions --------------------------------------------------
# Each entry: (family_name, directories_relative_to_home, trim_strategy)
# trim_strategy: "oldest_first" (direct file deletion) or a callable name
# for a package manager's own prune command, which is safer where one exists.


def _npm_dirs(home: Path) -> list[Path]:
    return [home / ".npm"]


def _npx_dirs(home: Path) -> list[Path]:
    return [home / ".npm" / "_npx"]


def _pnpm_dirs(home: Path) -> list[Path]:
    # macOS pnpm store + cache; Linux equivalents differ but both are
    # regenerable package stores, safe for oldest-first trimming.
    return [
        home / "Library" / "pnpm",
        home / "Library" / "Caches" / "pnpm",
        home / ".local" / "share" / "pnpm",
        home / ".cache" / "pnpm",
    ]


def _uv_dirs(home: Path) -> list[Path]:
    return [home / ".cache" / "uv", home / "Library" / "Caches" / "uv"]


def _pip_dirs(home: Path) -> list[Path]:
    return [home / ".cache" / "pip", home / "Library" / "Caches" / "pip"]


def _poetry_dirs(home: Path) -> list[Path]:
    # Deliberately only the downloaded-artifact cache, never virtualenvs.
    return [
        home / "Library" / "Caches" / "pypoetry" / "artifacts",
        home / ".cache" / "pypoetry" / "artifacts",
    ]


def _homebrew_dirs(home: Path) -> list[Path]:
    return [home / "Library" / "Caches" / "Homebrew"]


def _cargo_dirs(home: Path) -> list[Path]:
    # Registry cache + src only. Never ~/.cargo/bin or installed toolchains.
    return [home / ".cargo" / "registry" / "cache", home / ".cargo" / "registry" / "src"]


FAMILY_DIRS = {
    "npm": _npm_dirs,
    "npx": _npx_dirs,
    "pnpm": _pnpm_dirs,
    "uv": _uv_dirs,
    "pip": _pip_dirs,
    "poetry": _poetry_dirs,
    "homebrew": _homebrew_dirs,
    "cargo": _cargo_dirs,
}


def family_size_bytes(family: str, home: Path | None = None) -> int:
    home = home or Path.home()
    dirs = FAMILY_DIRS.get(family, lambda h: [])(home)
    return sum(_dir_size_bytes(d) for d in dirs)


def total_cache_bytes(families: tuple[str, ...], home: Path | None = None) -> int:
    home = home or Path.home()
    return sum(family_size_bytes(f, home) for f in families)


def trim_to_cap(
    families: tuple[str, ...],
    cap_bytes: int,
    home: Path | None = None,
) -> list[TrimResult]:
    """Trim cache families oldest-first until total usage is at or below cap_bytes.

    Families are visited in the order given; within a family, files are
    deleted oldest-mtime-first. Stops as soon as the cap is satisfied.
    """
    home = home or Path.home()
    results: list[TrimResult] = []

    current_total = total_cache_bytes(families, home)
    if current_total <= cap_bytes:
        return results

    over_by = current_total - cap_bytes

    for family in families:
        if over_by <= 0:
            break
        dirs = FAMILY_DIRS.get(family, lambda h: [])(home)
        family_freed = 0
        for d in dirs:
            if over_by <= 0:
                break
            freed = _oldest_first_trim(d, over_by)
            family_freed += freed
            over_by -= freed
        if family_freed > 0:
            results.append(TrimResult(family=family, freed_bytes=family_freed))

    return results


def npm_cache_clean() -> TrimResult | None:
    """Prefer npm's own prune where available; safer than raw deletion for npm's
    internal index/lock bookkeeping. Returns None if npm is not installed.
    """
    if shutil.which("npm") is None:
        return None
    before = family_size_bytes("npm")
    try:
        subprocess.run(["npm", "cache", "clean", "--force"], capture_output=True, check=False)
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    after = family_size_bytes("npm")
    return TrimResult(family="npm", freed_bytes=max(0, before - after), note="npm cache clean")
