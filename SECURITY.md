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

## Built-in mitigations

- Safe XML parsing with `defusedxml`
- Request body size limit
- XML output escaping via `html.escape`
- Log-injection prevention: `X-Request-ID` and URL paths are restricted to safe characters before any log write (`X-Request-ID`: alphanumerics plus `._-`; paths: control chars, whitespace, and `=` replaced)
- Rate limiting per IP with `RATE_LIMIT_PER_MINUTE` and bounded in-memory storage
- Security headers: `nosniff`, `no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store`, `Content-Security-Policy`, `Permissions-Policy`, and `Strict-Transport-Security` (when `PUBLIC_BASE_URL` uses `https://`)
- Neutral error responses that do not expose your domain list
- Non-root container user
- CI security checks with `gitleaks`, `bandit`, `pip-audit`, Trivy, and CodeQL

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

## Vulnerability disclosure

Please open a private security advisory instead of a public issue:

[Create a private advisory](https://github.com/solarssk/mail-autodiscover/security/advisories/new)

Include:

- a short description of the issue,
- steps to reproduce,
- expected impact,
- an optional suggested fix.

We aim to acknowledge reports within 48 hours.
