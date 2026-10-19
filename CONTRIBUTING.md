# Contributing

**Status: passively maintained.** Wolf is used in production at 42labs and gets commits
regularly — but it is not a staffed product. There is no support rota and no SLA. Issues and
pull requests are welcome and genuinely read; expect a reply in weeks rather than days, and
sometimes not at all. That is capacity, not disinterest. Plan accordingly before you invest a
weekend.

## What's welcome

- **Bug reports with a reproduction.** The smaller the repro, the faster it moves.
- **Small, focused pull requests.** One logical change, tests green.
- **Documentation** — typos, unclear passages, missing setup steps. Always welcome, usually fast.

## What is unlikely to land

- Large refactors, architecture changes, rewrites.
- Features not discussed in an issue first. **Open the issue before you write the code** — one message, potentially a saved weekend.
- Unrequested dependency bumps, formatting-only diffs, build-tooling swaps.
- A new "which processes/caches Wolf touches" default without a settings-file override — every destructive default must stay configurable per machine.

## If you need it faster

Fork it. The AGPL-3.0 grants you exactly that. A fork that moves faster than this repo is a
good outcome, not a betrayal — this is a real answer, not a brush-off.

## Before you open a PR

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

## Licensing

Wolf is dual-licensed: AGPL-3.0 for open source, commercial terms on request — see
[LICENSING.md](LICENSING.md).

**By submitting a pull request you grant 42labs the right to distribute your contribution
under both the AGPL-3.0 and 42labs' commercial license.** You keep the copyright to what you
wrote. Without this grant a single merged patch would make the commercial half unsellable, and
we would have to refuse it.
