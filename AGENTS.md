# AGENTS.md — project context for AI coding agents

> `CLAUDE.md` imports this file (`@AGENTS.md`) and adds Claude-Code-specific workflow
> notes on top. Keep project-wide context here so both files can't drift apart.

## Repository standard

This repository follows the solarssk engineering standard: https://github.com/solarssk/playbook
Tier: 2 (see playbook/docs/tiers.md) — it ships a container image and runs as a
deploy-and-forget service, which puts it at Tier 2 by the tier system's own first
question, even though it has one maintainer and a narrow, deliberately small feature set.

## What this project is

`mail-autodiscover` is a stateless FastAPI service that returns mail client configuration
(IMAP/SMTP/POP3) for allowed domains. It serves three autodiscovery protocols:

- **Outlook Autodiscover** — `POST /autodiscover/autodiscover.xml`
- **Thunderbird Autoconfig** — `GET /mail/config-v1.1.xml`
- **Apple Mail profile** — `GET /mail/ios.mobileconfig`

There is no database, no admin panel, no mailbox existence check, and no LDAP integration.
Keep it that way.

## Critical security invariant — never break this

The service must return **the same response shape** for every syntactically valid address in an
allowed domain, regardless of whether the mailbox actually exists. Any code path that reveals
whether `alice@example.com` exists while `bob@example.com` does not is a bug.

## Tech stack

| Layer | Choice |
|-------|--------|
| Framework | FastAPI |
| Config | `pydantic-settings` (ENV or YAML via `CONFIG_FILE`) |
| XML parsing | `defusedxml` (safe) |
| XML escaping | `html.escape(..., quote=False)` |
| YAML | `PyYAML` |
| Server | `uvicorn[standard]` |
| Python | ≥ 3.12 |

## Project layout

```
app/
  main.py          # FastAPI app factory + all routes
  config.py        # Settings, DomainMailSettings, YAML loader
  security.py      # SecurityMiddleware, rate limiter, logging, header sanitisation
  templates.py     # Outlook XML and Thunderbird XML builders
  mobileconfig.py  # Apple Mail .mobileconfig builder
  email_utils.py   # Email validation
  landing.py       # Landing page HTML and robots.txt
  static/          # favicon.ico, apple-touch-icon.png
config/
  config.example.yaml   # Multi-domain YAML example
docs/              # Reverse-proxy, DNS, client, and troubleshooting guides
scripts/
  check.sh                  # Local CI mirror
  format_release_notes.py   # Formats CHANGELOG entry into GitHub release body
tests/             # pytest — ≥ 90 % coverage on app/ is enforced
```

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
pre-commit install
cp .env.example .env          # set APP_ENV=development
uvicorn app.main:app --reload
```

Set `APP_ENV=development` or `APP_ENV=test` to bypass production-only startup validation.

## Running checks

```bash
./scripts/check.sh                        # full CI mirror (ruff, mypy, pytest, bandit, etc.)
SKIP_PIP_AUDIT=1 SKIP_DEPTRY=1 ./scripts/check.sh  # skip slower scans
pytest                                    # tests only
```

## Configuration modes

**Single-domain (ENV):** set `ALLOWED_DOMAINS`, `IMAP_HOST`, `SMTP_HOST`, etc. in `.env`.

**Multi-domain (YAML):** set `CONFIG_FILE=/config/config.yaml` and mount a YAML file that
follows the shape in `config/config.example.yaml`. When `CONFIG_FILE` exists and is valid,
ENV-based `ALLOWED_DOMAINS`/`IMAP_*`/`SMTP_*` values are ignored for routing.

`USERNAME_FORMAT` is always read from ENV, even in YAML mode.

## Release process

1. Bump `version` in `pyproject.toml`.
2. Add a `## [X.Y.Z] - YYYY-MM-DD` entry in `CHANGELOG.md` following the hybrid format
   described in `CONTRIBUTING.md` (narrative sections first, then KaC technical sections).
3. Update the version comparison links at the bottom of `CHANGELOG.md`:
   each `[VERSION]` must link to `compare/vPREV...vVERSION`.
4. Open a PR, merge to `main`.
5. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
   The Release workflow reads `CHANGELOG.md` and publishes formatted notes automatically.

## Things to be careful about

- **No `--no-verify` on commits** — pre-commit hooks enforce code quality.
- **Never log full email addresses** — `security.py` intentionally logs only domain hashes.
- **Proxy header trust is off by default** (`TRUST_PROXY_HEADERS=false`). Do not change the
  default.
- **Production startup validation** in `config.py` rejects placeholder values and unsafe proxy
  settings — do not weaken it.
- **Rate limiter is in-process** — one counter per uvicorn worker. Document this limitation
  when discussing multi-worker deployments.
- **XML escaping uses `html.escape(..., quote=False)`**, not `xml.sax.saxutils.escape`.
  Keep it that way (Bandit B406).
- **Runtime dependencies are locked in `requirements.txt`** (hash-pinned, generated with
  `pip-compile`). If you change `[project.dependencies]` in `pyproject.toml`, regenerate
  it in the same change: `pip-compile --generate-hashes --allow-unsafe -o requirements.txt
  pyproject.toml`. CI fails if the two drift apart.
