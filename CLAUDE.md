# CLAUDE.md — project context for Claude Code

@AGENTS.md

Rules below are **Claude Code–specific**. Shared project context (stack, layout, release
process, the mailbox-enumeration invariant) lives in `AGENTS.md` — do not duplicate it here.

## 1. Verify, don't assume

Read the actual file before describing what it does. `config.py`'s production-startup
validation, the rate limiter's in-process scope, and the exact set of public endpoints are
all things a plausible-sounding guess gets wrong. Ground every claim in this repo's current
state, not in what a similar FastAPI service usually looks like.

## 2. Simplicity first

Minimum code that solves the problem, nothing speculative. No abstractions for single-use
code, no error handling for scenarios that cannot happen, no new dependency for something
the standard library already does. If a change adds a database, a queue, or a new external
call, that's a sign it no longer fits this project — say so instead of building it.

## 3. Surgical changes

Touch only what the task requires. Don't "improve" adjacent code while fixing something
else, and match existing style. Every changed line should trace directly back to the task.

## 4. You prepare; the user decides and merges

No `--no-verify` on commits — pre-commit hooks enforce code quality and exist for a reason.
Propose the change, run `./scripts/check.sh`, and let CI and the maintainer confirm it before
it lands on `main`.

## 5. Compounding engineering

When a mistake in this repo trips you up, fix the root cause and update `AGENTS.md` (or this
file, for Claude-only workflow notes) so the next session doesn't repeat it.
