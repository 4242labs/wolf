"""wolf CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wolf import __version__
from wolf.config import load_machine_config
from wolf.runner import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wolf", description="Fleet cleanup, healing, and health-check agent.")
    parser.add_argument("--version", action="version", version=f"wolf {__version__}")
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="Path to this machine's settings YAML (default: $WOLF_SETTINGS or /etc/wolf/settings.yaml)",
    )
    parser.add_argument(
        "--print-result",
        action="store_true",
        help="Print the run result JSON to stdout after the run",
    )
    args = parser.parse_args(argv)

    try:
        config = load_machine_config(args.settings)
    except (FileNotFoundError, ValueError) as exc:
        print(f"wolf: {exc}", file=sys.stderr)
        return 1

    result = run(config)

    if args.print_result:
        print(result.to_json())

    return 0 if result.colour.name != "RED" else 2


if __name__ == "__main__":
    sys.exit(main())
