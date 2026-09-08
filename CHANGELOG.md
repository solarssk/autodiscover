# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- `requirements.txt`: hash-pinned lockfile for runtime dependencies, generated with
  `pip-compile`. The Docker image now installs from this instead of resolving
  `pyproject.toml`'s `>=` bounds fresh on every build, so the exact same dependency
  versions and artifacts ship every time. CI fails if it drifts from `pyproject.toml`.
- `CODE_OF_CONDUCT.md`.
- `.coderabbit.yaml`: automatic CodeRabbit review is off; trigger one on demand by
  commenting `@coderabbitai review` on a PR. Matches the same setting already used in
  `ssf-transmitter` and `wp-critical-css`.
- `.github/CODEOWNERS`.
- "Repository standard" pointer in `AGENTS.md` declaring this repo as Tier 2 of the
  solarssk engineering standard (`solarssk/playbook`).
- README table of contents, badge row, and License section.
- CycloneDX SBOM generated on version tags and attached to the GitHub Release.
- "Documentation impact" declaration on pull requests, checked in CI against the actual diff.
- `SECURITY.md` now has a "Security controls / CI" table and a stated response-time SLA.
- Regression tests for the documented "no mailbox enumeration" invariant: two different
  mailboxes in an allowed domain must get the same response shape and status code across
  Outlook, Thunderbird, and Apple Mail.
- `.github/workflows/verify-standard.yml`: calls `solarssk/playbook`'s reusable `verify-tier`
  workflow on every push and PR, mechanically checking this repo against its own declared
  Tier 2 checklist (SHA-pinning, `SECURITY.md`, issue templates, `concurrency:` blocks, and
  more). Same setup already used by `ssf-transmitter`.
- Published images are now also mirrored to **Docker Hub** (`docker.io/solarssk/mail-autodiscover`)
  alongside GHCR. `docker-publish.yml` copies the already-built, already-scanned GHCR
  manifest into Docker Hub by digest — never a second build — so both registries always
  carry byte-identical images with identical Trivy results. `latest` is now enabled only
  for `main` pushes (previously also a clean version tag): main pushes are already
  serialized against each other, but a tag push runs in its own concurrency group fully
  parallel to any in-flight main push, so both being eligible to write `latest` in two
  registries each could interleave and leave GHCR and Docker Hub's `latest` pointing at
  different digests. The release process always tags a commit already pushed to `main`,
  so `main`'s own run has already published `latest` for that content by the time the tag
  exists. `sha-<short>` is restricted to `main` for the same reason: a version tag shares
  its commit's short SHA with an already-published main run, and the `apt-get upgrade` in
  the Dockerfile means two independent builds of that same commit aren't guaranteed to
  produce the same digest, so the same cross-registry interleaving risk applied there too.
  Added `docker-compose.dockerhub.yml` as a Docker-Hub equivalent of the existing
  `docker-compose.ghcr.yml`, defaulting to `latest` rather than a pinned version for now,
  since no version tag has been published to Docker Hub yet. Also dropped the
  `{{major}}.{{minor}}` floating tag (e.g. `1.2`) entirely: two different patch releases in
  the same minor series are two different immutable tags with their own concurrency
  groups, so nothing serializes them against each other, and both would write the same
  "1.2" name from genuinely different, both-correct digests — the identical
  cross-registry interleaving risk as above, but with no single already-serialized run to
  defer to this time. Serializing all version-tag pushes into one group to fix it would
  reintroduce the silent-eviction failure mode already rejected at the top of this file
  (a third tag arriving mid-build would drop a queued release's image and SBOM entirely).
  The precise per-version tag is immune to this by construction, since no two releases
  ever share one.

### Changed

- `CLAUDE.md` is now a short `@AGENTS.md` import plus Claude-Code-specific notes, instead
  of duplicating `AGENTS.md` in full.
- `docker-publish.yml` now scans the actual image about to be pushed with Trivy (gated on
  fixable HIGH/CRITICAL) before pushing it, instead of only scanning a separate PR-time
  build that never reaches the registry.
- `ci.yml`'s secret scan is now scoped to each run's own commit range instead of the
  gitleaks GitHub Action's full-history default.
- All workflows now declare a `concurrency:` group (cancel-on-supersede for CI checks,
  never-cancel for release/publish workflows).
- README badges now sit after the description paragraph instead of before it.
- `app/main.py`: `create_app()`'s Thunderbird/Apple Mail handlers and the Outlook POST body
  are now plain module-level functions instead of nested closures, and a shared
  `_not_found_response()` helper replaces four duplicated 404 responses. Reduces
  SonarCloud-flagged Cognitive Complexity and unused `async` findings with no behavior
  change (verified by the full test suite, including the mailbox-enumeration invariant).
- `app/config.py`: `_shared_validation_errors()` is split into four focused validation
  methods, and the duplicated `"mail.example.com"`/`"example.com"` literals are now single
  constants. Same validation behavior and error messages, lower Cognitive Complexity.
- `app/security.py`: `SecurityMiddleware.dispatch()`'s access-log branching is extracted
  into `_log_access_event()`, and the log-sanitizer regex's character class no longer
  duplicates `\t\n\v\f\r` between an explicit range and `\s` (same matched character set,
  verified against the full BMP). Lower Cognitive Complexity, same logging output.
- `README.md` rewritten to match the house style used across `solarssk` repos
  (`ssf-transmitter` as the closest peer): centered badge row (adds Codecov and
  SonarCloud Quality Gate badges) and platform badge ahead of the description, a
  collapsed table of contents, a Mermaid "How it works" diagram, and an emoji-tagged
  Documentation table. Badges now sit before the description again, reversing the
  earlier "badges after description" change to match the actually-practiced sibling-repo
  convention rather than the more literal reading of the playbook doc. All content
  verified against the current repo (endpoints, env vars, compose files, doc links).
- `SECURITY.md`'s flat "Built-in mitigations" list is now "Main risks and mitigations":
  four named risks (XXE/XML bombs, oversized-request-body memory exhaustion, log
  injection, client-IP spoofing), each paired with the specific function and file
  that mitigates it, plus an explicit "Domain membership is observable — mailbox
  existence is not" section correcting an earlier draft that implied domain
  probing was also defended against (it isn't; only mailbox enumeration within an
  already-allowed domain is). Also corrects the XXE description (`defusedxml`
  blocks entity definitions and external references by default, not DTDs
  themselves) and drops an inaccurate "slow-drip" mitigation claim from the
  body-size section, pointing instead at reverse-proxy read timeouts for that.
  Added "Supported versions" and a responsible-disclosure commitment (coordinated
  disclosure, researcher credit) to "Vulnerability disclosure".

### Fixed

- `POST /autodiscover/autodiscover.xml` now enforces `MAX_REQUEST_BODY_BYTES` while
  reading the request body, instead of buffering the entire body into memory first and
  only checking the size afterward. An oversized POST is now rejected as soon as the
  limit is crossed, without ever fully buffering it.

## [0.3.3] - 2026-06-21

### What's new

- AI coding-agent context files added; documentation corrections.

### What this means

- `CLAUDE.md` and `AGENTS.md` give AI coding assistants (Claude Code, OpenAI Codex, and others)
  a concise map of the project: architecture, commands, security invariants, and release process.
  This avoids agents having to re-derive project conventions from scratch on each session.
- CHANGELOG version links now point to the correct diff range for each release.
- `CONTRIBUTING.md` correctly references the `docs/` directory instead of the GitHub Wiki,
  which was superseded in `0.3.0`.
- `pyproject.toml` project description now includes Apple Mail, which has been supported since `0.2.0`.

### Action required

- No action required.

### Added

- `CLAUDE.md` — project context file for Claude Code.
- `AGENTS.md` — project context file for OpenAI Codex and other AI agents (mirrors `CLAUDE.md`).

### Changed

- Fixed all CHANGELOG version comparison links — each link now points to `compare/vPREV...vVERSION` for its own release.
- Updated `CONTRIBUTING.md`: replaced the stale reference to the GitHub Wiki with the `docs/` directory.
- Updated `pyproject.toml` description to include Apple Mail profile support.

## [0.3.2] - 2026-06-20

### What's new

- Security hardening for the public autodiscover endpoints and their access logs.
- Maintenance updates for the Docker base image and GitHub secret-scanning action.

### What this means

- Plain text access logs are harder to spoof. Request-controlled values such as `X-Request-ID` and URL paths can no longer inject extra log lines or fake `key=value` fields like `status=200`.
- HTTPS deployments now send stricter browser security headers on normal responses and rate-limited `429` responses.
- The GHCR Docker image now builds on the Python 3.14 slim Bookworm base image.
- CI secret scanning now uses `gitleaks/gitleaks-action` v3, which moves the action runtime to Node 24.

### Action required

- No configuration changes are required for existing deployments.
- If you run multiple uvicorn/Gunicorn workers, keep an external rate limiter in front of the service. The built-in limiter is intentionally in-process and each worker has its own counter.

### Security

- Sanitized `X-Request-ID` before storing it on request state, returning it to clients, or writing it to logs. Only token-safe characters are kept.
- Sanitized logged URL paths so control characters, whitespace, and `=` cannot create forged fields in text-mode access logs.
- Added `Strict-Transport-Security: max-age=63072000` when `PUBLIC_BASE_URL` uses HTTPS. The header intentionally does not include `includeSubDomains` by default, because this app cannot know whether sibling subdomains are HTTPS-ready.
- Added `Content-Security-Policy` and `Permissions-Policy` headers.
- Applied security headers to rate-limited `429` responses as well as normal responses.
- Replaced `xml.sax.saxutils.escape` with `html.escape(..., quote=False)` for XML response text escaping, removing the Bandit B406 warning without changing output behavior.

### Changed

- Updated `Dockerfile` from `python:3.12-slim-bookworm` to `python:3.14-slim-bookworm`.
- Updated CI secret scanning from `gitleaks/gitleaks-action` v2 to v3.
- Documented the built-in rate limiter's multi-worker limitation in `SECURITY.md`.

### Tests

- Added regression coverage for request ID sanitization, URL path log sanitization, exact CSP/Permissions-Policy values, HSTS behavior, and security headers on rate-limited responses.

## [0.3.1] - 2026-06-12

### What's new

- Security hardening for reverse-proxy client IP handling and stricter production validation of `TRUSTED_PROXY_IPS`.

### Fixed

- Prefer `X-Real-IP` over `X-Forwarded-For` when the direct peer is a trusted proxy, preventing spoofed leftmost XFF entries from bypassing rate limits or polluting logs.
- Parse `X-Forwarded-For` from right to left, skipping trusted proxy hops, when `X-Real-IP` is missing or invalid.

### Changed

- In production, every non-empty `TRUSTED_PROXY_IPS` entry must be a valid IP or CIDR; invalid tokens now fail startup instead of being silently ignored.
- Nginx reverse-proxy docs now recommend `X-Forwarded-For $remote_addr` instead of `$proxy_add_x_forwarded_for` for single-hop deployments.

## [0.3.0] - 2026-06-12

### What's new

- Production-complete release before `1.0`: multi-domain YAML config, deployment docs, `/ready`, and optional JSON access logs.

### What this means

- You can run one container for multiple mail domains via mounted `config/config.yaml`, or keep the existing single-profile ENV mode.
- Reverse-proxy, DNS, client, and troubleshooting guides now live in `docs/`.

### Action required

- If you upgrade from `0.2.x`, review the updated README and mount `./config:/config:ro` when using YAML mode.
- Set `TRUSTED_PROXY_IPS` when `TRUST_PROXY_HEADERS=true` in production (unchanged from `0.2.2`).

### Added

- Optional multi-domain YAML config via `CONFIG_FILE` with per-domain IMAP/SMTP/POP3 settings.
- `GET /ready` readiness endpoint for container and reverse-proxy health checks.
- Optional structured JSON access logs via `STRUCTURED_JSON_LOGS=true`.
- In-repo deployment guides under `docs/` plus sample multi-domain config in `config/config.example.yaml`.

### Changed

- Apple Mail `.mobileconfig` downloads now use clearer per-domain filenames and mailbox-specific profile labels.
- Docker Compose examples now mount `/config` and expose the new config/logging settings.

### Fixed

- Reject YAML config files that define an empty `domains` map instead of silently falling back to ENV mode.

## [0.2.3] - 2026-06-12

### What's new

- This is a small follow-up release that closes a rate-limit configuration gap introduced in `0.2.2`.

### What this means

- Production deployments now reject `RATE_LIMIT_MAX_CLIENTS <= 0` instead of accepting a value that would silently weaken throttling behavior.

### Action required

- No action required if you already use a positive `RATE_LIMIT_MAX_CLIENTS` value.
- If you explicitly set `RATE_LIMIT_MAX_CLIENTS=0` or a negative value, replace it with a positive number before upgrading.

### Fixed

- Reject non-positive `RATE_LIMIT_MAX_CLIENTS` values when rate limiting is enabled, preventing ineffective throttling caused by immediate client-eviction behavior.

## [0.2.2] - 2026-06-12

### What's new

- Production deployments now fail fast on unsafe placeholder configuration instead of starting with `example.com` defaults.
- Reverse-proxy trust is safer by default: forwarded headers require explicit trusted proxy CIDRs.

### What this means

- Misconfigured production stacks surface a clear startup error instead of silently serving placeholder mail settings.
- Rate limiting uses a bounded in-memory store with periodic cleanup, reducing memory growth under abuse.

### Action required

- If you run behind a reverse proxy with `TRUST_PROXY_HEADERS=true`, set `TRUSTED_PROXY_IPS` to your proxy or Docker bridge CIDRs before upgrading to `0.2.2` in production.
- Review reverse-proxy access logs: Thunderbird and Apple Mail endpoints pass `emailaddress` in the query string.

### Security

- Default `TRUST_PROXY_HEADERS` changed to `false`; empty `TRUSTED_PROXY_IPS` no longer trusts all peers.
- `X-Forwarded-For` and `X-Real-IP` values are validated as real IP addresses before use.
- Production startup validation for HTTPS `PUBLIC_BASE_URL`, real domains, and proxy trust settings.

### Added

- `RATE_LIMIT_MAX_CLIENTS` and `RATE_LIMIT_CLEANUP_INTERVAL_SECONDS` for bounded rate-limit storage.
- Stable UUIDv5 identifiers in Apple `.mobileconfig` profiles (re-download updates the same profile).
- Healthcheck in `docker-compose.ghcr.yml`.

### Changed

- `TRUST_PROXY_HEADERS` default is now `false` in application config, `.env.example`, and GHCR compose.
- Trivy blocks CRITICAL vulnerabilities on pull requests; `main` keeps advisory SARIF upload.

### Fixed

- `docker-compose.ghcr.yml` port mapping now respects `CONTAINER_PORT`.
- Apple `.mobileconfig` `PayloadIdentifier` values are account-specific so multiple mailboxes on one domain do not collide.
- `docker-compose.ghcr.yml` default `IMAGE_TAG` matches the release version (`0.2.2`).

## [0.2.1] - 2026-06-11

### What's new

- The project now lives at `mail-autodiscover`, with GHCR images published only under `ghcr.io/solarssk/mail-autodiscover`.
- Documentation moved to the GitHub Wiki, and the public Python API is now documented with module docstrings.

### What this means

- New installs have one canonical repository and container image name.
- Admins follow wiki links from the README instead of the removed in-repo `wiki/` folder.

### Action required

- Pull `ghcr.io/solarssk/mail-autodiscover` instead of the retired `ghcr.io/solarssk/autodiscover` package path.
- Pin `IMAGE_TAG=0.2.1` (or newer) in production rather than the old `autodiscover` image tags.

### Changed

- GitHub repository renamed to `mail-autodiscover`; GHCR images publish as `ghcr.io/solarssk/mail-autodiscover`
- Documentation now links to the GitHub Wiki instead of the in-repo `wiki/` folder
- Replace flaky GitHub CodeQL default setup with explicit `.github/workflows/codeql.yml`
- Add docstrings across the `app/` package for public API and security helpers

## [0.2.0] - 2026-06-10

### What's new

- This release makes reverse-proxy deployments safer, adds a simple landing page, and introduces Apple Mail profile downloads.

### What this means

- Admins get clearer logging, better control over forwarded headers, and a cleaner user-facing entry point.
- End users on iPhone, iPad, and Mac can install a mail profile instead of entering all settings by hand.

### Action required

- If you run the service behind a reverse proxy, review and set `TRUSTED_PROXY_IPS` for your own proxy or Docker network ranges.
- If you deploy with Portainer or GHCR images, prefer the pinned `0.2.0` tag in production.

### Added

- `TRUSTED_PROXY_IPS` / `FORWARDED_ALLOW_IPS` so forwarded client IP headers are trusted only from your configured proxy CIDRs
- `ACCESS_LOG_SKIP_PATHS` to reduce noise from health checks and static asset requests
- Apple Mail `.mobileconfig` profiles (`GET /mail/ios.mobileconfig`, `/.well-known/apple-mail.mobileconfig`)
- HTML landing page, `robots.txt`, `favicon.ico`, `apple-touch-icon.png`
- `docker-compose.ghcr.yml` example for Portainer / GHCR deployments

### Changed

- Unified access logs now show `client_ip`, method, endpoint, and status in a single line
- `GET /` now returns a small landing page instead of JSON metadata
- `/health` is no longer rate limited

### Security

- Forwarded headers are honored only when the direct peer matches `TRUSTED_PROXY_IPS` when that setting is present

## [0.1.2] - 2026-06-10

### What's new

- This is a maintenance and hardening release focused on container safety and CI security checks.

### What this means

- Runtime behavior stays the same, but the delivery pipeline and base image are more defensive.

### Action required

- No action required.

### Security

- Docker image hardening: `python:3.12-slim-bookworm`, `apt-get upgrade`, pip >= `26.1.2`
- CodeQL-related test adjustments to avoid unsafe URL substring assertions

### Note

- CodeQL ran via GitHub default setup in this release

## [0.1.1] - 2026-06-10

### What's new

- This is a dependency and CI maintenance release.

### What this means

- There are no product-level changes for admins or end users, only safer and cleaner project maintenance.

### Action required

- No action required.

### Changed

- Bump `actions/checkout` to `v6.0.3`
- Bump `gitleaks/gitleaks-action` through Dependabot

### Note

- Python `3.14` Docker base image bump was intentionally declined to keep CI and runtime aligned on `3.12`

## [0.1.0] - 2026-06-10

### What's new

- First public release of `mail-autodiscover` with Outlook and Thunderbird support, Docker packaging, and baseline security controls.

### What this means

- Self-hosted mail admins can expose standards-based autodiscovery without building a custom service.
- The service is ready for simple production deployments where one domain or a small set of domains share the same mail settings.

### Action required

- Configure your environment variables, deploy behind HTTPS, and create the required DNS records before pointing users to the service.

### Added

- Outlook Autodiscover (`POST /autodiscover/autodiscover.xml`)
- Thunderbird Autoconfig (`GET /mail/config-v1.1.xml`)
- Environment-based configuration via `pydantic-settings`
- Docker and Docker Compose support
- Security middleware for rate limiting, headers, and safe logging
- `pytest` test suite with coverage gate
- Hardened CI with `gitleaks`, `ruff`, `mypy`, `bandit`, `pip-audit`, `deptry`, and Trivy
- GHCR image publishing (`ghcr.io/solarssk/mail-autodiscover`)
- `CONTRIBUTING.md`, `SECURITY.md`, issue templates, PR template, and Dependabot
- Branch protection and repository labels
- MIT license

[Unreleased]: https://github.com/solarssk/mail-autodiscover/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/solarssk/mail-autodiscover/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/solarssk/mail-autodiscover/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/solarssk/mail-autodiscover/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/solarssk/mail-autodiscover/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/solarssk/mail-autodiscover/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/solarssk/mail-autodiscover/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/solarssk/mail-autodiscover/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/solarssk/mail-autodiscover/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/solarssk/mail-autodiscover/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/solarssk/mail-autodiscover/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/solarssk/mail-autodiscover/releases/tag/v0.1.0
