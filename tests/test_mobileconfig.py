"""Tests for Apple .mobileconfig profile generation."""

import plistlib

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FixedSettingsProvider, make_settings


def test_mobileconfig_returns_plist_for_allowed_domain() -> None:
    settings = make_settings()
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        response = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user@example.com"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-apple-aspen-config")
    assert "mail-autodiscover-example.com.mobileconfig" in response.headers.get(
        "content-disposition", ""
    )

    profile = plistlib.loads(response.content)
    assert profile["PayloadType"] == "Configuration"
    mail = profile["PayloadContent"][0]
    assert mail["PayloadType"] == "com.apple.mail.managed"
    assert mail["EmailAccountType"] == "EmailTypeIMAP"
    assert mail["EmailAddress"] == "user@example.com"
    assert "user@example.com" in profile["PayloadDisplayName"]
    assert "user@example.com" in mail["PayloadDisplayName"]
    assert mail["IncomingMailServerHostName"] == "mail.example.com"
    assert mail["IncomingMailServerPortNumber"] == 993
    assert mail["OutgoingMailServerHostName"] == "mail.example.com"
    assert mail["OutgoingMailServerPortNumber"] == 587
    assert "IncomingPassword" not in mail
    assert "OutgoingPassword" not in mail


def test_mobileconfig_missing_emailaddress() -> None:
    settings = make_settings()
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        response = client.get("/mail/ios.mobileconfig")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


def test_mobileconfig_unknown_domain_404() -> None:
    settings = make_settings()
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        response = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user@evil.org"},
        )
    assert response.status_code == 404


def test_mobileconfig_wellknown_alias() -> None:
    settings = make_settings()
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        response = client.get(
            "/.well-known/apple-mail.mobileconfig",
            params={"emailaddress": "user@example.com"},
        )
    assert response.status_code == 200


def test_mobileconfig_stable_identifiers() -> None:
    settings = make_settings()
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        first = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user@example.com"},
        )
        second = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user@example.com"},
        )

    profile_a = plistlib.loads(first.content)
    profile_b = plistlib.loads(second.content)
    assert profile_a["PayloadUUID"] == profile_b["PayloadUUID"]
    assert profile_a["PayloadIdentifier"] == profile_b["PayloadIdentifier"]
    mail_a = profile_a["PayloadContent"][0]
    mail_b = profile_b["PayloadContent"][0]
    assert mail_a["PayloadUUID"] == mail_b["PayloadUUID"]
    assert mail_a["PayloadIdentifier"] == mail_b["PayloadIdentifier"]


def test_mobileconfig_identifiers_differ_per_account() -> None:
    settings = make_settings()
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        first = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user1@example.com"},
        )
        second = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user2@example.com"},
        )

    profile_a = plistlib.loads(first.content)
    profile_b = plistlib.loads(second.content)
    assert profile_a["PayloadIdentifier"] != profile_b["PayloadIdentifier"]
    assert (
        profile_a["PayloadContent"][0]["PayloadIdentifier"]
        != profile_b["PayloadContent"][0]["PayloadIdentifier"]
    )


def test_mobileconfig_disabled() -> None:
    settings = make_settings(apple_mobileconfig_enabled=False)
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as client:
        response = client.get(
            "/mail/ios.mobileconfig",
            params={"emailaddress": "user@example.com"},
        )
    assert response.status_code == 404
