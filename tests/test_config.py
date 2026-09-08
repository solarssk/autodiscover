"""Tests for configuration and SettingsProvider."""

import pytest
from pydantic import ValidationError

from app.config import EnvSettingsProvider, Settings
from tests.conftest import FixedSettingsProvider, make_settings


def test_settings_allowed_domains_parsed() -> None:
    settings = make_settings(allowed_domains="Example.COM, example.pl")
    assert settings.allowed_domains_set == frozenset({"example.com", "example.pl"})


def test_settings_provider_returns_settings() -> None:
    settings = make_settings()
    provider = FixedSettingsProvider(settings)
    assert provider.get_settings() is settings


def test_env_settings_provider() -> None:
    provider = EnvSettingsProvider()
    result = provider.get_settings()
    assert isinstance(result, Settings)


def test_socket_type_normalization() -> None:
    settings = make_settings(imap_socket_type="ssl", smtp_socket_type="starttls")
    assert settings.imap_socket_type.value == "SSL"
    assert settings.smtp_socket_type.value == "STARTTLS"


def test_trusted_proxy_ips_parsed_as_networks() -> None:
    settings = make_settings(trusted_proxy_ips="127.0.0.1, 10.0.0.0/8 ,10.0.0.1")
    assert len(settings.trusted_proxy_networks) == 3


def test_access_log_skip_paths_parsed() -> None:
    settings = make_settings(access_log_skip_paths="/health, /favicon.ico")
    assert settings.access_log_skip_paths_set == frozenset({"/health", "/favicon.ico"})


def test_allowed_domains_none_becomes_empty_set() -> None:
    settings = make_settings(allowed_domains=None)
    assert settings.allowed_domains_set == frozenset()


def test_domain_settings_for_returns_none_for_disallowed_domain() -> None:
    settings = make_settings()
    assert settings.domain_settings_for("not-allowed.test") is None


def test_rejects_non_positive_body_limit() -> None:
    with pytest.raises(ValidationError, match="must be greater than 0"):
        make_settings(max_request_body_bytes=0)
