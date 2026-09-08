# Security Policy

This document is for maintainers and admins who need the detailed security model behind `mail-autodiscover`.

If you are looking for setup help, start with [`README.md`](README.md) and the in-repo `docs/` guides.

## What this service is allowed to do

`mail-autodiscover` may return mail client configuration for allowed domains.

It may not:

- verify that a mailbox exists,
- expose internal domain lists on the public landing page,
- act as an admin panel,
- connect to LDAP, IMAP, Synology APIs, or user databases to validate an email address.

Those limits are intentional. They keep the service small and reduce the risk of mailbox enumeration.

## Core security property: no mailbox enumeration

For every syntactically valid address in an allowed domain, the service returns the same configuration shape.

That means the service must not reveal whether `alice@example.com` exists while `bob@example.com` does not. Any future feature that checks mailbox existence would break the project's main security guarantee.

## Trust boundaries

```text
[Mail clients: Outlook, Thunderbird, Apple Mail]
        │ HTTPS
        ▼
[Reverse proxy: TLS termination, optional rate limiting]
        │
        ▼
[mail-autodiscover container]
```

## Public endpoints

- `GET /health`
- `GET /ready`
- `GET /`
- `GET /robots.txt`
- `GET /favicon.ico`
- `GET /apple-touch-icon.png`
- `GET /mail/config-v1.1.xml`
- `GET /.well-known/autoconfig/mail/config-v1.1.xml`
- `GET /mail/ios.mobileconfig`
- `GET /.well-known/apple-mail.mobileconfig`
- `POST /autodiscover/autodiscover.xml`
- `GET /autodiscover/autodiscover.xml`

There is no admin API in the current version. Configuration comes from environment variables or an optional mounted YAML file.

## Data handling

| Data | Logged? | Notes |
|------|---------|-------|
| Full email addresses | No | Logs include only `domain_allowed=true/false` and a hashed domain prefix |
| Request XML body | No | Request bodies are never logged |
| Client IP | Yes | Stored in the unified access log as `client_ip=` |
| IMAP/SMTP hosts | Returned to clients | Comes from ENV or mounted YAML config, not from a user database |

## Main risks and mitigations

### XXE / XML bombs via the Outlook Autodiscover body

**Risk:** `POST /autodiscover/autodiscover.xml` accepts an attacker-controlled XML body. A crafted payload with external entity references or nested entity expansion (billion laughs) could try to read local files or exhaust memory during parsing.

**Mitigation:** `parse_outlook_email_address()` (`app/security.py`) parses with `defusedxml.ElementTree.fromstring`, called with its default arguments: `forbid_entities=True` and `forbid_external=True` reject entity definitions and external references — the actual XXE and entity-expansion vectors — regardless of `forbid_dtd` (which defaults to `False`, so a bare, entity-free DTD is not itself refused). A payload using either vector fails to parse and is treated as "no email address found," not executed.

### Memory exhaustion via an oversized request body

**Risk:** A very large POST body to the Outlook endpoint could be used to exhaust a worker's memory.

**Mitigation:** the request body is read via `request.stream()` and checked against `MAX_REQUEST_BODY_BYTES` on every chunk, rejecting with `413` the instant the limit is crossed — never buffering the full body first to decide.

**Not mitigated here:** a body sent slowly, one byte at a time, stays under the size cap indefinitely — this code has no read deadline of its own. Guard against slow-drip / slowloris-style requests with a read timeout at the reverse proxy in front of the service (see `docs/reverse-proxy/`).

### Log injection via request metadata

**Risk:** A forged `X-Request-ID` header or a URL path containing control characters, `=`, or embedded newlines could be used to forge fake log lines or break `key=value` log parsing.

**Mitigation:** `_sanitize_request_id()` keeps only `[A-Za-z0-9._-]` and caps the result at 64 characters (falling back to a fresh UUID otherwise); `_sanitize_for_log()` replaces control characters, `=`, and whitespace in the logged path with `?` before anything is written.

### Client-IP spoofing via forwarded headers

**Risk:** A client could set `X-Forwarded-For` or `X-Real-IP` directly on its own request, trying to poison the access log or dodge per-IP rate limiting.

**Mitigation:** `get_client_ip()` only honors these headers when the immediate TCP peer is inside `TRUSTED_PROXY_IPS`, and even then parses `X-Forwarded-For` right-to-left, skipping hops that are themselves trusted proxies. `TRUST_PROXY_HEADERS` defaults to `false`.

### Domain membership is observable — mailbox existence is not

The guarantee under "Core security property" above is scoped to mailboxes *within* an allowed domain; it does not extend to hiding which domains are configured at all. A request for a domain this server doesn't handle reaches `_domain_error_response()` and returns 404 or 400 (per `RETURN_404_FOR_UNKNOWN_DOMAIN`), while any syntactically valid mailbox in a configured domain returns a successful configuration regardless of whether that specific mailbox exists. Probing a list of candidate domains against this server can therefore reveal which ones it serves — that's an inherent consequence of the server correctly declining domains it doesn't handle, not something a response-shape mitigation can close. The landing page at least never lists configured domains outright, so it doesn't hand that list over for free.

Don't rely on domain membership being hidden. If that matters for your deployment, restrict network access to this service rather than expecting the response shape to hide it.

### Everything else

- XML output escaping via `html.escape(..., quote=False)`, not `xml.sax.saxutils.escape` (see `AGENTS.md`)
- Security headers on every response: `nosniff`, `no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store`, `Content-Security-Policy`, `Permissions-Policy`, and `Strict-Transport-Security` when `PUBLIC_BASE_URL` uses `https://`
- Non-root container user
- CI security checks: `gitleaks`, `bandit`, `pip-audit`, Trivy, and CodeQL (see the table below)

## Security controls / CI

| Control | Scope | When | Workflow |
|---|---|---|---|
| gitleaks | Secret scan, scoped to the run's own commit range | Every push and PR | `.github/workflows/ci.yml` (`gitleaks`) |
| bandit | Static analysis (Python) | Every push and PR | `.github/workflows/ci.yml` (`security`) |
| pip-audit | Dependency vulnerability audit | Every push and PR | `.github/workflows/ci.yml` (`security`) |
| deptry | Unused / missing dependency check | Every push and PR | `.github/workflows/ci.yml` (`security`) |
| CodeQL | SAST (Python, GitHub Actions) | Every push, every PR, and weekly | `.github/workflows/codeql.yml` |
| Trivy (pre-merge) | Container image scan; blocks on HIGH/CRITICAL on PRs, advisory SARIF upload only on push to `main` | Every push and PR | `.github/workflows/ci.yml` (`docker`) |
| Trivy (pre-publish) | Container image scan of the actual image about to be pushed, gates on fixable HIGH/CRITICAL | Push to `main` and version tags | `.github/workflows/docker-publish.yml` |
| CycloneDX SBOM | Software bill of materials for the published image | Version tags, attached to the GitHub Release | `.github/workflows/docker-publish.yml` |
| Dependabot | Dependency and GitHub Actions update PRs | Weekly | `.github/dependabot.yml` |
| Documentation-impact check | PR's declared doc-update checkbox verified against the actual diff | Every non-Dependabot PR | `.github/workflows/ci.yml` (`docs-impact`) |
| Codecov | Coverage report and patch-coverage signal (not yet a merge gate) | Every push and PR | `.github/workflows/ci.yml` (`test`) |
| SonarCloud | Static analysis, code smells, and security rating (not yet a merge gate) | Every push and PR | `.github/workflows/ci.yml` (`test`) |
| Verify standard | Mechanical check against the `solarssk/playbook` Tier 2 checklist (SHA-pinning, `SECURITY.md`, issue templates, `concurrency:` blocks, and more) | Every push and PR | `.github/workflows/verify-standard.yml` |

This table is a claim you can check directly: open the named workflow file and confirm the
step is really there. Keep it honest rather than complete — remove a row the day a control is
removed, rather than leaving a stale entry.

## Deployment requirements

1. Run the service behind an HTTPS reverse proxy.
2. Enable `TRUST_PROXY_HEADERS=true` only when requests really come through a trusted proxy.
3. Set `TRUSTED_PROXY_IPS` or `FORWARDED_ALLOW_IPS` to your own proxy or Docker bridge CIDRs.
4. Keep `ALLOWED_DOMAINS` limited to domains you actually operate.
5. Do not expose the container directly to the public internet without TLS.
6. In production, pin GHCR images by semver tag or digest instead of using `latest`.
7. With `APP_ENV=production`, the service refuses to start on placeholder values (`example.com`, `mail.example.com`, `http://localhost`, missing `TRUSTED_PROXY_IPS` when proxy trust is on).
8. **Do not run multiple uvicorn workers** (`--workers N` or Gunicorn multi-process) without an external rate-limiter. The built-in rate limiter is in-process only; with N workers the effective per-IP limit becomes `N × RATE_LIMIT_PER_MINUTE`.

## Reverse proxy logging

Thunderbird Autoconfig and Apple Mail profile URLs include `?emailaddress=user@example.com` in the query string. Mail clients require this parameter.

This service does not log full email addresses, but your reverse proxy may log the full request URI unless you configure it otherwise. Review access-log settings for paths such as `/mail/config-v1.1.xml`, `/.well-known/autoconfig/`, and `/mail/ios.mobileconfig`.

## Apple Mail profiles

`.mobileconfig` profiles are generated without a code-signing certificate. iOS and macOS warn that the profile is unsigned before installation. That is expected for self-hosted mail setup.

Profile identifiers are stable per mailbox so users can re-download and update the same profile instead of accumulating duplicates.

## What not to add casually

Changes in the list below need a deliberate security review because they would alter the trust model:

- mailbox existence checks,
- public endpoints that query LDAP, IMAP, or Synology APIs,
- user-specific routing logic,
- a public page that exposes internal hostnames or allowed domains,
- forwarded-header trust without explicit proxy restrictions.

## Supported versions

Only the latest tagged release is supported. There are no long-term-support branches; upgrade to the current tag (see [CHANGELOG.md](CHANGELOG.md)) before reporting an issue that a newer release may have already fixed.

## Vulnerability disclosure

This is a small, single-maintainer service. We follow coordinated disclosure: please give us reasonable time to ship a fix before making an issue public, and we'll credit researchers who do.

Please open a private security advisory instead of a public issue:

[Create a private advisory](https://github.com/solarssk/mail-autodiscover/security/advisories/new)

Include:

- a short description of the issue,
- steps to reproduce,
- expected impact,
- an optional suggested fix.

We aim to acknowledge reports within 48 hours and to ship a fix for a confirmed critical issue within 14 days.
