"""Tests for production configuration fail-fast validation."""

import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def _production_settings(**overrides: object):
    base: dict[str, object] = {
        "app_env": "production",
        "public_base_url": "https://autodiscover.example.com",
        "allowed_domains": "mydomain.com",
        "imap_host": "mail.mydomain.com",
        "smtp_host": "mail.mydomain.com",
        "trust_proxy_headers": False,
    }
    base.update(overrides)
    return make_settings(**base)


def test_production_accepts_valid_configuration() -> None:
    settings = _production_settings()
    assert settings.app_env == "production"


def test_production_rejects_example_domain() -> None:
    with pytest.raises(ValidationError, match="ALLOWED_DOMAINS"):
        _production_settings(allowed_domains="example.com")


def test_production_rejects_placeholder_mail_hosts() -> None:
    with pytest.raises(ValidationError, match="mail.example.com"):
        _production_settings(
            imap_host="mail.example.com",
            smtp_host="mail.example.com",
        )


def test_production_rejects_http_public_base_url() -> None:
    with pytest.raises(ValidationError, match="https://"):
        _production_settings(public_base_url="http://autodiscover.example.com")


def test_production_rejects_localhost_public_base_url() -> None:
    with pytest.raises(ValidationError, match="localhost"):
        _production_settings(public_base_url="https://localhost:8000")


def test_production_rejects_proxy_trust_without_ips() -> None:
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_IPS"):
        _production_settings(trust_proxy_headers=True, trusted_proxy_ips="")


def test_production_rejects_invalid_trusted_proxy_ips() -> None:
    with pytest.raises(ValidationError, match="no valid CIDR"):
        _production_settings(
            trust_proxy_headers=True,
            trusted_proxy_ips="not-a-cidr",
        )


def test_production_rejects_partially_invalid_trusted_proxy_ips() -> None:
    with pytest.raises(ValidationError, match="invalid entry: not-a-cidr"):
        _production_settings(
            trust_proxy_headers=True,
            trusted_proxy_ips="172.18.0.0/16,not-a-cidr",
        )


def test_production_accepts_uvicorn_forwarded_allow_ips_when_proxy_trust_disabled() -> None:
    settings = _production_settings(
        trust_proxy_headers=False,
        trusted_proxy_ips="*",
    )
    assert settings.trusted_proxy_ips == "*"


def test_production_ignores_invalid_trusted_proxy_ips_when_proxy_trust_disabled() -> None:
    settings = _production_settings(
        trust_proxy_headers=False,
        trusted_proxy_ips="172.18.0.0/16,not-a-cidr",
    )
    assert settings.trusted_proxy_ips == "172.18.0.0/16,not-a-cidr"


def test_production_rejects_non_positive_rate_limit() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_PER_MINUTE"):
        _production_settings(rate_limit_enabled=True, rate_limit_per_minute=0)


def test_production_rejects_non_positive_rate_limit_capacity() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_MAX_CLIENTS"):
        _production_settings(rate_limit_enabled=True, rate_limit_max_clients=0)


def test_production_rejects_body_limit_over_max() -> None:
    with pytest.raises(ValidationError, match="must not exceed"):
        _production_settings(max_request_body_bytes=2_000_000)


def test_non_production_allows_placeholder_defaults() -> None:
    settings = make_settings(app_env="test")
    assert settings.allowed_domains_set == frozenset({"example.com", "example.pl"})
