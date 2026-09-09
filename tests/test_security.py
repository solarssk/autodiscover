"""Tests for security features."""

import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import (
    _rate_limit_store,
    _sanitize_for_log,
    _sanitize_request_id,
    is_rate_limited,
    reset_rate_limit_store,
)
from tests.conftest import FixedSettingsProvider, make_settings


def test_root_does_not_expose_domains_or_hosts(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "example.com" not in response.text
    assert "mail.example.com" not in response.text


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers.get("Content-Security-Policy") == (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert response.headers.get("Permissions-Policy") == (
        "accelerometer=(), camera=(), geolocation=(), "
        "gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
    )


def test_hsts_set_when_https_base_url() -> None:
    settings = make_settings(public_base_url="https://autodiscover.example.com")
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as c:
        response = c.get("/health")
    assert "Strict-Transport-Security" in response.headers
    assert response.headers["Strict-Transport-Security"] == "max-age=63072000"


def test_hsts_not_set_when_http_base_url() -> None:
    settings = make_settings(public_base_url="http://localhost:8000")
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as c:
        response = c.get("/health")
    assert "Strict-Transport-Security" not in response.headers


def test_rate_limit_response_includes_security_headers() -> None:
    reset_rate_limit_store()
    settings = make_settings(
        public_base_url="https://autodiscover.example.com",
        rate_limit_enabled=True,
        rate_limit_per_minute=1,
    )
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as c:
        assert c.get("/robots.txt").status_code == 200
        response = c.get("/robots.txt")

    assert response.status_code == 429
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers.get("Content-Security-Policy") == (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert response.headers.get("Permissions-Policy") == (
        "accelerometer=(), camera=(), geolocation=(), "
        "gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
    )
    assert "Strict-Transport-Security" in response.headers


def test_sanitize_for_log_replaces_unsafe_chars() -> None:
    assert _sanitize_for_log("/probe\nendpoint=/admin") == "/probe?endpoint?/admin"
    assert _sanitize_for_log("/probe status=200") == "/probe?status?200"
    assert _sanitize_for_log("no-controls") == "no-controls"


def test_sanitize_request_id_strips_unsafe_chars() -> None:
    assert _sanitize_request_id("legit\nevil") == "legitevil"
    assert _sanitize_request_id("abc=def ghi") == "abcdefghi"
    fallback = _sanitize_request_id("\n\r=")
    assert "\n" not in fallback
    assert "\r" not in fallback
    assert "=" not in fallback
    assert len(fallback) == 8


def test_request_id_control_chars_stripped(caplog: pytest.LogCaptureFixture) -> None:
    """X-Request-ID with embedded newlines must not reach logs or response headers intact."""
    reset_rate_limit_store()
    settings = make_settings(disable_access_log=False, log_level="INFO")
    app = create_app(FixedSettingsProvider(settings))
    injected = "legit\nevil=injected endpoint=/admin status=200"
    expected_id = _sanitize_request_id(injected)
    with caplog.at_level(logging.INFO, logger="mail_autodiscover.access"), TestClient(
        app, headers={"X-Request-ID": injected}
    ) as c:
        response = c.get("/mail/config-v1.1.xml", params={"emailaddress": "user@example.com"})

    returned_id = response.headers.get("X-Request-ID", "")
    assert returned_id == expected_id
    assert "\n" not in returned_id
    assert "\r" not in returned_id
    assert "\x00" not in returned_id
    assert "=" not in returned_id
    assert " " not in returned_id

    assert len(caplog.records) == 1
    log_text = caplog.records[0].message
    for record in caplog.records:
        assert "\n" not in record.message
        assert "\r" not in record.message
    assert log_text.startswith(f"request_id={expected_id} ")
    assert log_text.count("status=") == 1


def test_path_control_chars_sanitized_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Encoded newlines in URL paths must not forge extra log lines."""
    reset_rate_limit_store()
    settings = make_settings(disable_access_log=False, log_level="INFO")
    app = create_app(FixedSettingsProvider(settings))

    with caplog.at_level(logging.INFO, logger="mail_autodiscover.access"), TestClient(app) as c:
        c.get("/probe%0aendpoint=/admin%20status=200")

    assert len(caplog.records) == 1
    log_text = caplog.records[0].message
    for record in caplog.records:
        assert "\n" not in record.message
        assert "\r" not in record.message
    # Forged status=200 must not appear as a separate key=value token.
    assert "endpoint=" in log_text
    assert log_text.endswith("status=404 domain_allowed=None")
    assert log_text.count("status=") == 1


def test_rate_limit_when_enabled() -> None:
    reset_rate_limit_store()
    settings = make_settings(rate_limit_enabled=True, rate_limit_per_minute=3)
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as c:
        for _ in range(3):
            response = c.get("/robots.txt")
            assert response.status_code == 200
        response = c.get("/robots.txt")
        assert response.status_code == 429
        assert response.json() == {"detail": "Too many requests"}


def test_health_not_rate_limited() -> None:
    reset_rate_limit_store()
    settings = make_settings(rate_limit_enabled=True, rate_limit_per_minute=2)
    app = create_app(FixedSettingsProvider(settings))
    with TestClient(app) as c:
        for _ in range(5):
            assert c.get("/health").status_code == 200


def test_logs_do_not_contain_full_email(caplog: pytest.LogCaptureFixture) -> None:
    reset_rate_limit_store()
    settings = make_settings(disable_access_log=False, log_level="INFO")
    app = create_app(FixedSettingsProvider(settings))

    with caplog.at_level(logging.INFO, logger="mail_autodiscover.access"), TestClient(app) as c:
        c.get("/mail/config-v1.1.xml", params={"emailaddress": "secret.user@example.com"})

    log_text = " ".join(r.message for r in caplog.records)
    assert "secret.user@example.com" not in log_text
    assert "domain_allowed=true" in log_text
    assert "client_ip=" in log_text
    assert "method=GET" in log_text


def test_rate_limit_evicts_oldest_clients_when_over_capacity() -> None:
    reset_rate_limit_store()
    settings = make_settings(
        rate_limit_enabled=True,
        rate_limit_per_minute=100,
        rate_limit_max_clients=2,
        rate_limit_cleanup_interval_seconds=0,
    )

    assert is_rate_limited("203.0.113.1", settings) is False
    assert is_rate_limited("203.0.113.2", settings) is False
    assert len(_rate_limit_store) == 2

    assert is_rate_limited("203.0.113.3", settings) is False
    assert len(_rate_limit_store) == 2
    assert "203.0.113.1" not in _rate_limit_store


def test_rate_limit_eviction_keeps_most_recently_touched_clients() -> None:
    """A flood of far more distinct clients than capacity must still cap the
    store at max_clients and keep exactly the most-recently-touched ones,
    regardless of how many distinct identities came before them."""
    reset_rate_limit_store()
    settings = make_settings(
        rate_limit_enabled=True,
        rate_limit_per_minute=100,
        rate_limit_max_clients=5,
        rate_limit_cleanup_interval_seconds=0,
    )

    client_count = 200
    for i in range(client_count):
        assert is_rate_limited(f"198.51.100.{i}", settings) is False
        assert len(_rate_limit_store) <= 5

    assert len(_rate_limit_store) == 5
    surviving = list(_rate_limit_store.keys())
    expected = [f"198.51.100.{i}" for i in range(client_count - 5, client_count)]
    assert surviving == expected


def test_rate_limit_cleanup_evicts_stale_entries() -> None:
    reset_rate_limit_store()
    settings = make_settings(
        rate_limit_enabled=True,
        rate_limit_per_minute=100,
        rate_limit_cleanup_interval_seconds=0,
    )

    assert is_rate_limited("203.0.113.9", settings) is False
    assert "203.0.113.9" in _rate_limit_store

    # Age the entry past the 60s window; the next call's cleanup pass
    # (interval=0 forces one on every call) should evict it.
    _rate_limit_store["203.0.113.9"] = [time.monotonic() - 61]
    assert is_rate_limited("203.0.113.10", settings) is False
    assert "203.0.113.9" not in _rate_limit_store


def test_health_not_logged_by_default(caplog: pytest.LogCaptureFixture) -> None:
    reset_rate_limit_store()
    settings = make_settings(disable_access_log=False, log_level="INFO")
    app = create_app(FixedSettingsProvider(settings))

    with caplog.at_level(logging.INFO, logger="mail_autodiscover.access"), TestClient(app) as c:
        c.get("/health")

    assert not caplog.records


def test_json_access_logs_are_structured(caplog: pytest.LogCaptureFixture) -> None:
    reset_rate_limit_store()
    settings = make_settings(
        disable_access_log=False,
        log_level="INFO",
        structured_json_logs=True,
    )
    app = create_app(FixedSettingsProvider(settings))

    with caplog.at_level(logging.INFO, logger="mail_autodiscover.access"), TestClient(app) as c:
        c.get("/mail/config-v1.1.xml", params={"emailaddress": "secret.user@example.com"})

    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "request"
    assert payload["method"] == "GET"
    assert payload["domain_allowed"] is True
    assert payload["endpoint"] == "/mail/config-v1.1.xml"
    assert "secret.user@example.com" not in caplog.records[-1].message
