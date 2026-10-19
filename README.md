# wolf

[![Project Status: Active](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![Maintenance](https://img.shields.io/badge/maintenance-passively--maintained-yellowgreen.svg)](CONTRIBUTING.md)

> One agent per machine that cleans, heals, and reports — so the cleanup that used to run silently is finally visible.

Wolf replaces a handful of separate, unreported cron jobs (cache trimming, stale-process reaping) with one tool, installed per machine, that does cache trimming, stale/orphaned process reaping, Docker image pruning, service health checks, and reboot management — then writes one structured result per run. A consolidated SysAdmin Daily/Weekly Report reads every machine's latest result and sends one email, only when something needs attention (daily) or always as a weekly summary (Monday).

## How it works

Each machine runs `wolf` on its own schedule (default 06:00 UTC, configurable). A run:

1. Skips cache trimming entirely if a package manager or build tool is currently active (ported from the previous `safe-cache-cleanup.sh` guard) — a separate guard from the overlap lock below.
2. Guards against two Wolf invocations overlapping on the same machine (an `mkdir`-based lock, also ported from `safe-cache-cleanup.sh`).
3. Trims package caches (npm, npx, pnpm, uv, pip, Poetry, Homebrew, Cargo) oldest-first to a configured cap — never touching virtualenvs, projects, models, or build output.
4. Reaps stale/orphaned MCP, Playwright, and chrome-devtools processes (ported from `stale-mcp-reaper.sh`).
5. Prunes unused Docker images oldest-first to a configured cap, on machines that run Docker.
6. Runs the same service/binary health checks Alghul's Night Watch ran.
7. Reports pending OS updates (never installs them — that stays the OS's own unattended-upgrade mechanism).
8. Decides whether a reboot is due (updates pending, or days-since-boot over threshold) and, if due, reboots unless an agent chat was active on that machine within the configured idle window (checked via Hermes session-state file mtimes) or the machine has `reboot.allowed: false` (report-only).
9. Writes a structured JSON result locally, and — if configured — pushes it to the machine that aggregates results (over SSH).

A separate `wolf-report` command, run once a day by a scheduler, reads every machine's latest result and sends the consolidated email.

## Per-machine settings

Wolf reads per-machine configuration from a YAML file outside this repo (default `/etc/wolf/settings.yaml`, overridable with `$WOLF_SETTINGS`). See [`settings.example.yaml`](settings.example.yaml) for every field, documented. No machine names, addresses, or credentials belong in this repo — only in each machine's private copy.

The report reads its own small config the same way; see [`report-settings.example.yaml`](report-settings.example.yaml). SMTP credentials are read from environment variables at send time, populated by the scheduler from a secrets store — never from a file in this repo.

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

## Contributing

**Status: passively maintained.** Wolf runs in production at 42labs and gets commits regularly, but it is not a staffed product — no SLA, no support rota. Issues and small, focused pull requests are welcome and genuinely read.

## Contributors

<!-- contributors:start -->
<!-- contributors:end -->

## License

Open source — [AGPL-3.0](LICENSE). Commercial — contact ahoy@42labs.io.

---
If it earned its keep, [coffee is appreciated](https://buymeacoffee.com/42piratas). ☕
