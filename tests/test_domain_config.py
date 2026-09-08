"""Tests for YAML-backed domain configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from tests.conftest import OUTLOOK_REQUEST_TEMPLATE, FixedSettingsProvider, make_settings


def _write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_yaml_domain_config_replaces_allowed_domains(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  example.com:
    display_name: Example Mail
    display_short_name: Example
    imap:
      host: mail.example.com
      port: 993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: mail.example.com
      port: 587
      socket_type: STARTTLS
      authentication: password-cleartext
""".strip(),
    )

    settings = make_settings(config_file=str(config_file), allowed_domains="ignored.test")
    assert settings.allowed_domains_set == frozenset({"example.com"})


def test_yaml_multi_domain_serves_per_domain_settings(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  example.com:
    display_name: Example Mail
    display_short_name: Example
    imap:
      host: mail.example.com
      port: 993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: smtp.example.com
      port: 587
      socket_type: STARTTLS
      authentication: password-cleartext
  second.example:
    display_name: Second Mail
    display_short_name: Second
    imap:
      host: imap.second.example
      port: 1993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: smtp.second.example
      port: 2587
      socket_type: STARTTLS
      authentication: password-cleartext
    pop3:
      enabled: true
      host: pop.second.example
      port: 1995
      socket_type: SSL
      authentication: password-cleartext
""".strip(),
    )
    settings = make_settings(config_file=str(config_file))
    app = create_app(FixedSettingsProvider(settings))

    with TestClient(app) as client:
        tb = client.get("/mail/config-v1.1.xml", params={"emailaddress": "user@second.example"})
        mobileconfig = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user@second.example"},
        )
        outlook = client.post(
            "/autodiscover/autodiscover.xml",
            content=OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com"),
            headers={"Content-Type": "text/xml"},
        )

    assert tb.status_code == 200
    assert "<hostname>imap.second.example</hostname>" in tb.text
    assert "<hostname>pop.second.example</hostname>" in tb.text
    assert "<displayName>Second Mail</displayName>" in tb.text
    assert mobileconfig.status_code == 200
    assert "mail-autodiscover-second.example.mobileconfig" in mobileconfig.headers[
        "content-disposition"
    ]
    assert outlook.status_code == 200
    assert "<Server>mail.example.com</Server>" in outlook.text
    assert "<Server>smtp.example.com</Server>" in outlook.text


def test_yaml_config_unknown_domain_keeps_neutral_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  example.com:
    display_name: Example Mail
    display_short_name: Example
    imap:
      host: mail.example.com
      port: 993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: mail.example.com
      port: 587
      socket_type: STARTTLS
      authentication: password-cleartext
""".strip(),
    )
    settings = make_settings(config_file=str(config_file))
    app = create_app(FixedSettingsProvider(settings))

    with TestClient(app) as client:
        response = client.get("/mail/config-v1.1.xml", params={"emailaddress": "user@evil.org"})

    assert response.status_code == 404
    assert "evil.org" not in response.text


def test_invalid_yaml_config_raises_validation_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  example.com:
    display_name: Example Mail
""".strip(),
    )

    with pytest.raises(ValidationError, match="CONFIG_FILE"):
        make_settings(config_file=str(config_file))


def test_empty_yaml_domains_raises_validation_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains: {}
""".strip(),
    )

    with pytest.raises(ValidationError, match="must define at least one domain"):
        make_settings(config_file=str(config_file))


def test_invalid_yaml_syntax_raises_validation_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(config_file, "domains: [unterminated")

    with pytest.raises(ValidationError, match="not valid YAML"):
        make_settings(config_file=str(config_file))


def test_empty_config_file_raises_validation_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(config_file, "")

    with pytest.raises(ValidationError, match="is empty"):
        make_settings(config_file=str(config_file))


def test_config_file_directory_raises_validation_error(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Unable to read CONFIG_FILE"):
        make_settings(config_file=str(tmp_path))


def test_yaml_empty_domain_key_raises_validation_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  " ":
    display_name: Example Mail
    display_short_name: Example
    imap:
      host: mail.example.com
      port: 993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: mail.example.com
      port: 587
      socket_type: STARTTLS
      authentication: password-cleartext
""".strip(),
    )

    with pytest.raises(ValidationError, match="empty domain key"):
        make_settings(config_file=str(config_file))


def test_production_yaml_rejects_example_com_domain(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  example.com:
    display_name: Example Mail
    display_short_name: Example
    imap:
      host: mail.mydomain.com
      port: 993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: mail.mydomain.com
      port: 587
      socket_type: STARTTLS
      authentication: password-cleartext
""".strip(),
    )

    with pytest.raises(ValidationError, match="example.com"):
        make_settings(
            app_env="production",
            public_base_url="https://autodiscover.mydomain.com",
            trust_proxy_headers=False,
            config_file=str(config_file),
        )


def test_production_yaml_rejects_placeholder_hosts(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    _write_config(
        config_file,
        """
domains:
  mydomain.com:
    display_name: My Mail
    display_short_name: My Mail
    imap:
      host: mail.example.com
      port: 993
      socket_type: SSL
      authentication: password-cleartext
    smtp:
      host: mail.example.com
      port: 587
      socket_type: STARTTLS
      authentication: password-cleartext
""".strip(),
    )

    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(
            app_env="production",
            public_base_url="https://autodiscover.mydomain.com",
            trust_proxy_headers=False,
            config_file=str(config_file),
        )
