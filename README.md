# mail-autodiscover

[![CI](https://github.com/solarssk/mail-autodiscover/actions/workflows/ci.yml/badge.svg)](https://github.com/solarssk/mail-autodiscover/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/solarssk/mail-autodiscover)](https://github.com/solarssk/mail-autodiscover/releases)
![Platforms](https://img.shields.io/badge/platforms-amd64%20%7C%20arm64-informational)

`mail-autodiscover` is a small deploy-and-forget HTTP service for self-hosted mail admins.

It exposes standard autodiscovery endpoints for:

- Outlook Autodiscover
- Thunderbird Autoconfig
- Apple Mail `.mobileconfig`
- POP3 in Thunderbird config when enabled for a domain

The product goal is deliberately narrow:

- stateless container
- no admin panel
- no database
- no mailbox existence checks
- no LDAP / Synology / directory lookups

If you want a small service you can deploy behind HTTPS and mostly forget about, this is what it is for.

## Table of Contents

- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
  - [Single-Domain Or Shared Global Config](#single-domain-or-shared-global-config)
  - [Multi-Domain Config File](#multi-domain-config-file)
- [Docker / Portainer](#docker--portainer)
- [Reverse Proxy Contract](#reverse-proxy-contract)
- [Endpoints](#endpoints)
- [Apple Mail Notes](#apple-mail-notes)
- [Logging And Observability](#logging-and-observability)
- [Documentation](#documentation)
- [Security At A Glance](#security-at-a-glance)
- [Local Development](#local-development)
- [Quality Checks](#quality-checks)
- [License](#license)

## What It Does

For any syntactically valid mailbox in an allowed domain, the service returns the configured IMAP/SMTP settings and, optionally, POP3 for Thunderbird.

It does **not**:

- verify whether a mailbox exists
- expose your internal domain list on the landing page
- return different answers for existing vs non-existing mailboxes
- manage users or credentials

## Quick Start

1. Copy [`.env.example`](.env.example) to `.env`.
2. Choose one configuration mode:
   - single/global config in ENV
   - multi-domain config in [`config/config.example.yaml`](config/config.example.yaml)
3. Deploy with Docker Compose or Portainer.
4. Put the service behind HTTPS reverse proxy.
5. Point `autodiscover.` and `autoconfig.` DNS records to that proxy.
6. Test the endpoints before sharing them with users.

### Single-Domain Or Shared Global Config

```env
APP_ENV=production
PUBLIC_BASE_URL=https://autodiscover.example.com
ALLOWED_DOMAINS=example.com,example.org
MAIL_DISPLAY_NAME=Example Mail
MAIL_DISPLAY_SHORT_NAME=Example
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_SOCKET_TYPE=SSL
SMTP_HOST=mail.example.com
SMTP_PORT=587
SMTP_SOCKET_TYPE=STARTTLS
POP3_ENABLED=false
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IPS=127.0.0.1,10.0.0.0/8
```

This mode serves the same IMAP/SMTP profile for every domain listed in `ALLOWED_DOMAINS`.

### Multi-Domain Config File

Set:

```env
CONFIG_FILE=/config/config.yaml
```

Then mount a file like [`config/config.example.yaml`](config/config.example.yaml).

If `CONFIG_FILE` exists, domain settings are loaded from YAML and the application ignores the global `ALLOWED_DOMAINS`/`IMAP_*`/`SMTP_*` values for request routing.

`USERNAME_FORMAT` is not per-domain in YAML mode; it still comes from ENV and applies to every configured domain.

## Docker / Portainer

For local builds:

```bash
docker compose up -d
```

For GHCR images:

```bash
docker compose -f docker-compose.ghcr.yml up -d
```

The compose examples mount `./config:/config:ro`, so placing `config/config.yaml` next to the compose file is enough for multi-domain mode.

Prebuilt images are published to GHCR:

```text
ghcr.io/solarssk/mail-autodiscover:latest
ghcr.io/solarssk/mail-autodiscover:0.3.2
```

Prefer pinned tags or digests in production.

## Reverse Proxy Contract

- `TRUST_PROXY_HEADERS=false` is the safe default.
- Enable `TRUST_PROXY_HEADERS=true` only when traffic really arrives through your own proxy.
- In production, `TRUSTED_PROXY_IPS` is required whenever proxy header trust is enabled.
- Thunderbird and Apple Mail use `?emailaddress=user@example.com` in the query string.

Important:

Your reverse proxy may log the full query string even though this application does not. Review access log settings for:

- `/mail/config-v1.1.xml`
- `/.well-known/autoconfig/mail/config-v1.1.xml`
- `/mail/ios.mobileconfig`
- `/.well-known/apple-mail.mobileconfig`

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe |
| `GET` | `/` | Minimal landing page |
| `GET` | `/robots.txt` | No-index hint |
| `GET` | `/mail/config-v1.1.xml?emailaddress=...` | Thunderbird Autoconfig |
| `GET` | `/.well-known/autoconfig/mail/config-v1.1.xml?emailaddress=...` | Thunderbird alias |
| `GET` | `/mail/ios.mobileconfig?emailaddress=...` | Apple Mail profile |
| `GET` | `/.well-known/apple-mail.mobileconfig?emailaddress=...` | Apple Mail alias |
| `POST` | `/autodiscover/autodiscover.xml` | Outlook Autodiscover |
| `GET` | `/autodiscover/autodiscover.xml` | Neutral Outlook response |

## Apple Mail Notes

- Profiles are unsigned by default.
- iOS and macOS warn about unsigned profiles in self-hosted setups; this is expected.
- Profiles never contain mailbox passwords.
- Re-downloading the same mailbox profile updates the existing profile because identifiers are stable.
- If you need signed profiles, sign them externally before distribution.

## Logging And Observability

- `X-Request-ID` is attached to responses and access logs.
- Access logs never include the full mailbox address.
- `STRUCTURED_JSON_LOGS=true` switches access logging to JSON.
- `/metrics` is intentionally not built in.

## Documentation

- [Reverse Proxy and DNS](docs/dns.md)
- [Nginx](docs/reverse-proxy/nginx.md)
- [Caddy](docs/reverse-proxy/caddy.md)
- [Nginx Proxy Manager](docs/reverse-proxy/nginx-proxy-manager.md)
- [Synology Reverse Proxy](docs/reverse-proxy/synology-reverse-proxy.md)
- [Cloudflare Tunnel / Generic Proxy](docs/reverse-proxy/cloudflare-tunnel.md)
- [Outlook client setup](docs/clients/outlook.md)
- [Thunderbird client setup](docs/clients/thunderbird.md)
- [Apple Mail client setup](docs/clients/apple-mail.md)
- [Troubleshooting](docs/troubleshooting.md)

## Security At A Glance

- no mailbox enumeration
- no full email address logging
- safe XML parsing
- bounded in-memory rate limiting
- security headers enabled by default
- no admin API

See [SECURITY.md](SECURITY.md) for the detailed trust model.

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
pre-commit install
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log --reload
```

For development with placeholder values, set `APP_ENV=test` or `APP_ENV=development`.

## Quality Checks

Run the same Python checks as GitHub CI:

```bash
./scripts/check.sh
```

`pre-commit install` also runs `ruff`, `mypy`, and `pytest` automatically before each commit.

Developer workflow and release process live in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE).
