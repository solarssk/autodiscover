"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from app.config import EnvSettingsProvider, Settings, SettingsProvider
from app.email_utils import EmailValidationError, validate_email
from app.landing import landing_page_html, robots_txt
from app.mobileconfig import (
    MOBILECONFIG_CONTENT_TYPE,
    apple_mail_mobileconfig,
    mobileconfig_filename,
)
from app.security import SecurityMiddleware, hash_domain, parse_outlook_email_address
from app.templates import outlook_autodiscover, outlook_get_neutral_response, thunderbird_autoconfig

XML_CONTENT_TYPE = "application/xml; charset=utf-8"
_NOT_FOUND_DETAIL = "Not found"
_STATIC_DIR = Path(__file__).resolve().parent / "static"

_settings_provider: SettingsProvider = EnvSettingsProvider()


def get_settings_provider() -> SettingsProvider:
    """FastAPI dependency that returns the active settings provider."""
    return _settings_provider


def get_settings(
    provider: Annotated[SettingsProvider, Depends(get_settings_provider)],
) -> Settings:
    """FastAPI dependency that loads application settings."""
    return provider.get_settings()


def _not_found_response() -> JSONResponse:
    """Return the standard 404 for a disabled protocol or an unknown domain."""
    return JSONResponse(status_code=404, content={"detail": _NOT_FOUND_DETAIL})


def _domain_error_response(settings: Settings) -> JSONResponse:
    """Return the configured response for disallowed mailbox domains."""
    if settings.return_404_for_unknown_domain:
        return _not_found_response()
    return JSONResponse(status_code=400, content={"detail": "Configuration not available"})


def _invalid_request() -> JSONResponse:
    """Return a generic 400 for malformed autodiscovery requests."""
    return JSONResponse(status_code=400, content={"detail": "Invalid request"})


def _xml_response(content: str) -> Response:
    """Wrap autodiscovery XML with the standard response content type."""
    return Response(content=content, media_type=XML_CONTENT_TYPE)


def _thunderbird_config(
    request: Request,
    emailaddress: str | None,
    settings: Settings,
) -> Response:
    """Shared handler for Thunderbird autoconfig endpoints."""
    if not settings.thunderbird_enabled:
        return _not_found_response()

    validated, error = validate_email(emailaddress, settings)
    if error == EmailValidationError.EMPTY:
        return _invalid_request()
    if error is not None:
        request.state.domain_allowed = False
        return _domain_error_response(settings)

    assert validated is not None
    domain_settings = settings.domain_settings_for(validated.domain)
    if domain_settings is None:
        request.state.domain_allowed = False
        return _domain_error_response(settings)

    request.state.domain_allowed = True
    request.state.domain_hash = hash_domain(validated.domain)
    xml = thunderbird_autoconfig(validated, domain_settings, settings.username_format)
    return _xml_response(xml)


def _apple_mobileconfig(
    request: Request,
    emailaddress: str | None,
    settings: Settings,
) -> Response:
    """Shared handler for Apple Mail mobileconfig endpoints."""
    if not settings.apple_mobileconfig_enabled:
        return _not_found_response()

    validated, error = validate_email(emailaddress, settings)
    if error == EmailValidationError.EMPTY:
        return _invalid_request()
    if error is not None:
        request.state.domain_allowed = False
        return _domain_error_response(settings)

    assert validated is not None
    domain_settings = settings.domain_settings_for(validated.domain)
    if domain_settings is None:
        request.state.domain_allowed = False
        return _domain_error_response(settings)

    request.state.domain_allowed = True
    request.state.domain_hash = hash_domain(validated.domain)
    body = apple_mail_mobileconfig(validated, domain_settings, settings.username_format)
    return Response(
        content=body,
        media_type=MOBILECONFIG_CONTENT_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{mobileconfig_filename(validated.domain)}"'
            )
        },
    )


async def _handle_outlook_autodiscover_post(request: Request, settings: Settings) -> Response:
    """Read, validate, and answer an Outlook autodiscover POST request."""
    if not settings.outlook_enabled:
        return _not_found_response()

    # Enforce the limit while reading, not after: request.body() buffers
    # the entire stream into memory before any check can run, which lets
    # an oversized POST exhaust worker memory regardless of the limit.
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > settings.max_request_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request entity too large"})
        chunks.append(chunk)
    body = b"".join(chunks)

    email_raw = parse_outlook_email_address(body)
    if not email_raw:
        return _invalid_request()

    validated, error = validate_email(email_raw, settings)
    if error is not None:
        request.state.domain_allowed = False
        if error == EmailValidationError.DOMAIN_NOT_ALLOWED:
            return _domain_error_response(settings)
        return _invalid_request()

    assert validated is not None
    domain_settings = settings.domain_settings_for(validated.domain)
    if domain_settings is None:
        request.state.domain_allowed = False
        return _domain_error_response(settings)

    request.state.domain_allowed = True
    request.state.domain_hash = hash_domain(validated.domain)
    xml = outlook_autodiscover(validated, domain_settings, settings.username_format)
    return _xml_response(xml)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure process logging when the application starts."""
    settings = _settings_provider.get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    yield


def create_app(settings_provider: SettingsProvider | None = None) -> FastAPI:
    """Build the FastAPI app with autodiscovery routes and security middleware."""
    global _settings_provider
    if settings_provider is not None:
        _settings_provider = settings_provider

    settings = _settings_provider.get_settings()

    app = FastAPI(
        title=settings.app_name,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(SecurityMiddleware, settings=settings)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/", response_class=HTMLResponse)
    async def root(settings: Annotated[Settings, Depends(get_settings)]) -> HTMLResponse:
        return HTMLResponse(content=landing_page_html(settings.app_name))

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots() -> PlainTextResponse:
        return PlainTextResponse(content=robots_txt(), media_type="text/plain")

    @app.get("/favicon.ico")
    async def favicon() -> FileResponse:
        return FileResponse(_STATIC_DIR / "favicon.ico", media_type="image/x-icon")

    @app.get("/apple-touch-icon.png")
    async def apple_touch_icon() -> FileResponse:
        return FileResponse(_STATIC_DIR / "apple-touch-icon.png", media_type="image/png")

    @app.get("/mail/config-v1.1.xml")
    async def thunderbird_config(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        emailaddress: Annotated[str | None, Query()] = None,
    ) -> Response:
        return _thunderbird_config(request, emailaddress, settings)

    @app.get("/.well-known/autoconfig/mail/config-v1.1.xml")
    async def thunderbird_config_wellknown(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        emailaddress: Annotated[str | None, Query()] = None,
    ) -> Response:
        return _thunderbird_config(request, emailaddress, settings)

    @app.get("/mail/ios.mobileconfig")
    async def apple_mobileconfig(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        emailaddress: Annotated[str | None, Query()] = None,
    ) -> Response:
        return _apple_mobileconfig(request, emailaddress, settings)

    @app.get("/.well-known/apple-mail.mobileconfig")
    async def apple_mobileconfig_wellknown(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        emailaddress: Annotated[str | None, Query()] = None,
    ) -> Response:
        return _apple_mobileconfig(request, emailaddress, settings)

    @app.post("/autodiscover/autodiscover.xml")
    async def outlook_autodiscover_post(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> Response:
        return await _handle_outlook_autodiscover_post(request, settings)

    @app.get("/autodiscover/autodiscover.xml")
    async def outlook_autodiscover_get() -> Response:
        return _xml_response(outlook_get_neutral_response())

    return app


app = create_app()
