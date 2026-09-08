"""Tests for email validation."""

from app.config import UsernameFormat
from app.email_utils import EmailValidationError, build_username, extract_domain, validate_email
from tests.conftest import make_settings


def test_valid_email_allowed_domain() -> None:
    settings = make_settings()
    validated, error = validate_email("jan@example.com", settings)
    assert error is None
    assert validated is not None
    assert validated.email == "jan@example.com"
    assert validated.domain == "example.com"


def test_domain_case_insensitive() -> None:
    settings = make_settings()
    validated, error = validate_email("jan@EXAMPLE.COM", settings)
    assert error is None
    assert validated is not None
    assert validated.domain == "example.com"


def test_missing_at_rejected() -> None:
    settings = make_settings()
    _, error = validate_email("janexample.com", settings)
    assert error == EmailValidationError.INVALID_FORMAT


def test_empty_rejected() -> None:
    settings = make_settings()
    _, error = validate_email("", settings)
    assert error == EmailValidationError.EMPTY


def test_disallowed_domain_rejected() -> None:
    settings = make_settings()
    _, error = validate_email("jan@evil.org", settings)
    assert error == EmailValidationError.DOMAIN_NOT_ALLOWED


def test_weird_characters_rejected() -> None:
    settings = make_settings()
    _, error = validate_email("jan<script>@example.com", settings)
    assert error == EmailValidationError.INVALID_FORMAT


def test_subdomain_not_allowed_unless_explicit() -> None:
    settings = make_settings()
    _, error = validate_email("jan@mail.example.com", settings)
    assert error == EmailValidationError.DOMAIN_NOT_ALLOWED


def test_subdomain_allowed_when_explicit() -> None:
    settings = make_settings(allowed_domains="mail.example.com")
    validated, error = validate_email("jan@mail.example.com", settings)
    assert error is None
    assert validated is not None
    assert validated.domain == "mail.example.com"


def test_build_username_email_format() -> None:
    settings = make_settings(username_format=UsernameFormat.EMAIL)
    validated, _ = validate_email("jan@example.com", settings)
    assert validated is not None
    assert build_username(validated, settings.username_format) == "jan@example.com"


def test_extract_domain_without_at_returns_none() -> None:
    assert extract_domain("no-at-sign") is None


def test_build_username_localpart_format() -> None:
    settings = make_settings(username_format=UsernameFormat.LOCALPART)
    validated, _ = validate_email("jan@example.com", settings)
    assert validated is not None
    assert build_username(validated, settings.username_format) == "jan"
