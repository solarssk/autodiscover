"""Tests for Outlook Autodiscover endpoints."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.security import reset_rate_limit_store
from tests.conftest import OUTLOOK_REQUEST_TEMPLATE, FixedSettingsProvider, make_settings


def test_outlook_post_valid_xml(client: TestClient) -> None:
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com")
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert response.status_code == 200


def test_outlook_contains_account_type(client: TestClient) -> None:
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com")
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert "<AccountType>email</AccountType>" in response.text


def test_outlook_contains_action_settings(client: TestClient) -> None:
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com")
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert "<Action>settings</Action>" in response.text


def test_outlook_contains_imap_and_smtp(client: TestClient) -> None:
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com")
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert "<Type>IMAP</Type>" in response.text
    assert "<Type>SMTP</Type>" in response.text
    assert "<Server>mail.example.com</Server>" in response.text


def test_outlook_contains_login_name(client: TestClient) -> None:
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com")
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert "<LoginName>user@example.com</LoginName>" in response.text


def test_outlook_invalid_xml(client: TestClient) -> None:
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content="<not-valid-xml",
        headers={"Content-Type": "text/xml"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


def test_outlook_missing_email_address(client: TestClient) -> None:
    body = """<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006">
  <Request>
    <AcceptableResponseSchema>
      http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a
    </AcceptableResponseSchema>
  </Request>
</Autodiscover>"""
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert response.status_code == 400


def test_outlook_body_too_large() -> None:
    reset_rate_limit_store()
    settings = make_settings(max_request_body_bytes=100)
    app = create_app(FixedSettingsProvider(settings))
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@example.com")
    with TestClient(app) as c:
        response = c.post(
            "/autodiscover/autodiscover.xml",
            content=body,
            headers={"Content-Type": "text/xml"},
        )
    assert response.status_code == 413


def test_outlook_body_at_exact_limit_succeeds() -> None:
    """Boundary check: a body of exactly max_request_body_bytes must still
    succeed; the streaming size check compares with '>', not '>=', so only
    an over-limit body is rejected. Guards against an accidental '>' -> '>='
    flip in the request.stream() loop."""
    reset_rate_limit_store()
    limit = 500
    settings = make_settings(max_request_body_bytes=limit)
    app = create_app(FixedSettingsProvider(settings))

    base_length = len(OUTLOOK_REQUEST_TEMPLATE.format(email="x@example.com").encode())
    local_part_length = 1 + (limit - base_length)
    email = ("x" * local_part_length) + "@example.com"
    body = OUTLOOK_REQUEST_TEMPLATE.format(email=email)
    assert len(body.encode()) == limit

    with TestClient(app) as c:
        response = c.post(
            "/autodiscover/autodiscover.xml",
            content=body,
            headers={"Content-Type": "text/xml"},
        )
    assert response.status_code == 200


def test_outlook_unknown_domain_neutral_error(client: TestClient) -> None:
    body = OUTLOOK_REQUEST_TEMPLATE.format(email="user@evil.org")
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=body,
        headers={"Content-Type": "text/xml"},
    )
    assert response.status_code == 404
    assert "evil.org" not in response.text


def test_outlook_get_neutral_response(client: TestClient) -> None:
    response = client.get("/autodiscover/autodiscover.xml")
    assert response.status_code == 200
    assert "Invalid request" in response.text


def test_outlook_xxe_rejected(client: TestClient) -> None:
    xxe_body = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006">
  <Request>
    <EMailAddress>&xxe;</EMailAddress>
  </Request>
</Autodiscover>"""
    response = client.post(
        "/autodiscover/autodiscover.xml",
        content=xxe_body,
        headers={"Content-Type": "text/xml"},
    )
    assert response.status_code == 400
    assert "/etc/passwd" not in response.text
