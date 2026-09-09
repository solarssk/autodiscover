"""Security middleware: rate limiting, headers, safe logging."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from threading import Lock

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings

logger = logging.getLogger("mail_autodiscover.access")

# OrderedDict, not a plain dict: every touch below calls move_to_end() so the
# front of the dict is always the least-recently-touched client, letting
# _enforce_rate_limit_capacity() evict in O(1) instead of sorting the whole
# store by timestamp on every request once at capacity.
_rate_limit_store: OrderedDict[str, list[float]] = OrderedDict()
_rate_limit_lock = Lock()
_last_rate_limit_cleanup = 0.0

_LOG_UNSAFE_RE = re.compile(r"[\x00-\x08\x0E-\x1F\x7F=\s]")
_REQUEST_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_for_log(value: str) -> str:
    """Replace chars that could break key=value log parsing (controls, '=', whitespace)."""
    return _LOG_UNSAFE_RE.sub("?", value)


def _sanitize_request_id(raw: str | None) -> str:
    """Return a sanitised request ID; allow only safe token chars or generate a fresh one."""
    if raw:
        sanitized = _REQUEST_ID_SAFE_RE.sub("", raw)[:64]
        if sanitized:
            return sanitized
    return str(uuid.uuid4())[:8]


def _log_event(
    level: int,
    *,
    json_mode: bool,
    logger_name: logging.Logger,
    **fields: object,
) -> None:
    """Log access events as structured JSON or compact key=value pairs."""
    if json_mode:
        logger_name.log(level, json.dumps(fields, sort_keys=True, separators=(",", ":")))
        return
    message = " ".join(f"{key}={value}" for key, value in fields.items())
    logger_name.log(level, message)


def _peer_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


def _ip_in_trusted_networks(
    ip_str: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    """Return whether an IP address falls within any configured proxy network."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def _parse_ip(value: str) -> str | None:
    """Return a normalized IP string when value is a valid address."""
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _should_trust_forwarded_headers(request: Request, settings: Settings) -> bool:
    """Decide if forwarded client IP headers may be used based on proxy trust settings."""
    if not settings.trust_proxy_headers:
        return False
    networks = settings.trusted_proxy_networks
    if not networks:
        return False
    peer = _peer_ip(request)
    if peer is None:
        return False
    return _ip_in_trusted_networks(peer, networks)


def _client_ip_from_forwarded_for(
    forwarded: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> str | None:
    """Parse X-Forwarded-For right-to-left, skipping trusted proxy hops."""
    tokens = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not tokens:
        return None

    parsed_ips: list[str] = []
    for token in tokens:
        parsed = _parse_ip(token)
        if parsed is None:
            return None
        parsed_ips.append(parsed)

    for parsed in reversed(parsed_ips):
        if not _ip_in_trusted_networks(parsed, networks):
            return parsed

    return parsed_ips[0]


def get_client_ip(request: Request, settings: Settings) -> str:
    """Resolve client IP, honoring forwarded headers only from trusted proxies."""
    peer = _peer_ip(request)
    if _should_trust_forwarded_headers(request, settings):
        networks = settings.trusted_proxy_networks
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            parsed = _parse_ip(real_ip)
            if parsed is not None and not _ip_in_trusted_networks(parsed, networks):
                return parsed
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            parsed = _client_ip_from_forwarded_for(forwarded, networks)
            if parsed is not None:
                return parsed
    if peer:
        return peer
    return "unknown"


def _cleanup_rate_limit_store(now: float, settings: Settings) -> None:
    """Remove stale client entries and evict oldest keys when over capacity."""
    global _last_rate_limit_cleanup

    window = 60.0
    interval = float(settings.rate_limit_cleanup_interval_seconds)
    if now - _last_rate_limit_cleanup >= interval:
        _last_rate_limit_cleanup = now
        stale_keys = [
            ip
            for ip, timestamps in _rate_limit_store.items()
            if not timestamps or now - timestamps[-1] >= window
        ]
        for ip in stale_keys:
            del _rate_limit_store[ip]

def _enforce_rate_limit_capacity(settings: Settings) -> None:
    """Evict least-recently-touched client entries when over configured capacity."""
    max_clients = settings.rate_limit_max_clients
    while len(_rate_limit_store) > max_clients:
        _rate_limit_store.popitem(last=False)


def hash_domain(domain: str) -> str:
    """Return a short stable hash of a domain for privacy-safe access logs."""
    return hashlib.sha256(domain.encode()).hexdigest()[:12]


def should_skip_rate_limit(path: str) -> bool:
    """Return whether the path is exempt from per-IP rate limiting."""
    return path in {"/health", "/ready"}


def should_skip_access_log(path: str, settings: Settings) -> bool:
    """Return whether the path should be omitted from access logs."""
    return path in settings.access_log_skip_paths_set


def is_rate_limited(client_ip: str, settings: Settings) -> bool:
    """Track request timestamps per IP and report when the minute window is exceeded."""
    if not settings.rate_limit_enabled:
        return False

    now = time.monotonic()
    window = 60.0
    limit = settings.rate_limit_per_minute

    with _rate_limit_lock:
        _cleanup_rate_limit_store(now, settings)
        timestamps = [t for t in _rate_limit_store.get(client_ip, []) if now - t < window]
        _rate_limit_store[client_ip] = timestamps
        if len(timestamps) >= limit:
            return True
        timestamps.append(now)
        # Move to the end only for an accepted request: this must track the
        # same "most recent request" recency the old timestamp-sort used
        # (item[1][-1], which only ever advanced on an appended timestamp),
        # not "most recently touched at all". Moving on a rejection too
        # would let a client already over its limit shield itself from
        # eviction by repeatedly getting rejected, while bumping a
        # different, still-within-window client's entry out from under it.
        _rate_limit_store.move_to_end(client_ip)
        _enforce_rate_limit_capacity(settings)
    return False


def reset_rate_limit_store() -> None:
    """Clear in-memory rate limit state (for tests)."""
    global _last_rate_limit_cleanup
    with _rate_limit_lock:
        _rate_limit_store.clear()
        _last_rate_limit_cleanup = 0.0


class SecurityMiddleware(BaseHTTPMiddleware):
    """Apply rate limits, security headers, and privacy-safe access logging."""

    _CSP = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    _PERMISSIONS_POLICY = (
        "accelerometer=(), camera=(), geolocation=(), "
        "gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
    )

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings
        self._hsts_value = (
            "max-age=63072000"
            if settings.public_base_url.lower().startswith("https://")
            else None
        )

    def _apply_security_headers(self, response: Response) -> None:
        """Attach configured security headers to every response path."""
        if not self.settings.security_headers_enabled:
            return
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = self._CSP
        response.headers["Permissions-Policy"] = self._PERMISSIONS_POLICY
        if self._hsts_value:
            response.headers["Strict-Transport-Security"] = self._hsts_value

    def _log_access_event(
        self,
        request: Request,
        response: Response,
        *,
        request_id: str,
        client_ip: str,
        log_endpoint: str,
    ) -> None:
        """Log one completed request without ever including the full email address."""
        domain_allowed = getattr(request.state, "domain_allowed", None)
        if domain_allowed is None:
            domain_info = "domain_allowed=unknown"
        else:
            domain_info = f"domain_allowed={'true' if domain_allowed else 'false'}"
        domain_hash = getattr(request.state, "domain_hash", None)
        if not domain_hash:
            _log_event(
                logging.INFO,
                json_mode=self.settings.structured_json_logs,
                logger_name=logger,
                event="request",
                request_id=request_id,
                client_ip=client_ip,
                method=request.method,
                endpoint=log_endpoint,
                status=response.status_code,
                domain_allowed=domain_allowed,
            )
        elif self.settings.structured_json_logs:
            _log_event(
                logging.INFO,
                json_mode=True,
                logger_name=logger,
                event="request",
                request_id=request_id,
                client_ip=client_ip,
                method=request.method,
                endpoint=log_endpoint,
                status=response.status_code,
                domain_allowed=domain_allowed,
                domain_hash=domain_hash,
            )
        else:
            domain_info += f" domain_hash={domain_hash}"
            logger.info(
                "request_id=%s client_ip=%s method=%s endpoint=%s status=%s %s",
                request_id,
                client_ip,
                request.method,
                log_endpoint,
                response.status_code,
                domain_info,
            )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Enforce limits, attach headers, and log requests without full email addresses."""
        request_id = _sanitize_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        request.state.domain_allowed = None

        path = request.url.path
        log_endpoint = _sanitize_for_log(path)
        client_ip = get_client_ip(request, self.settings)
        if not should_skip_rate_limit(path) and is_rate_limited(client_ip, self.settings):
            _log_event(
                logging.WARNING,
                json_mode=self.settings.structured_json_logs,
                logger_name=logger,
                event="request",
                request_id=request_id,
                endpoint=log_endpoint,
                status=429,
                rate_limited=True,
            )
            rate_limited_response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"X-Request-ID": request_id},
            )
            self._apply_security_headers(rate_limited_response)
            return rate_limited_response

        response = await call_next(request)

        self._apply_security_headers(response)
        response.headers["X-Request-ID"] = request_id

        if not self.settings.disable_access_log and not should_skip_access_log(
            path, self.settings
        ):
            self._log_access_event(
                request,
                response,
                request_id=request_id,
                client_ip=client_ip,
                log_endpoint=log_endpoint,
            )

        return response


def parse_outlook_email_address(body: bytes) -> str | None:
    """Safely parse Outlook autodiscover request XML and extract EMailAddress."""
    from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]

    try:
        root = fromstring(body)
    except Exception:
        return None

    for elem in root.iter():
        local_tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local_tag == "EMailAddress" and elem.text:
            return str(elem.text.strip())
    return None
