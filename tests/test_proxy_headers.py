"""Unit tests for trusted-proxy client IP resolution."""

from app.security import get_client_ip
from tests.conftest import make_settings


def _fake_request(
    *,
    peer_host: str | None,
    headers: dict[str, str] | None = None,
) -> object:
    class FakeClient:
        host = peer_host

    class FakeRequest:
        def __init__(self) -> None:
            self.headers = headers or {}
            self.client = FakeClient() if peer_host is not None else None

    return FakeRequest()


def test_untrusted_peer_ignores_forwarded_headers() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.0/24",
    )
    request = _fake_request(
        peer_host="203.0.113.99",
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "X-Real-IP": "198.51.100.7",
        },
    )
    assert get_client_ip(request, settings) == "203.0.113.99"  # type: ignore[arg-type]


def test_trusted_peer_uses_x_real_ip() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.1",
    )
    request = _fake_request(
        peer_host="172.16.2.1",
        headers={"X-Real-IP": "198.51.100.7"},
    )
    assert get_client_ip(request, settings) == "198.51.100.7"  # type: ignore[arg-type]


def test_trusted_x_real_ip_falls_through_to_xff() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.1,203.0.113.0/24",
    )
    request = _fake_request(
        peer_host="172.16.2.1",
        headers={
            "X-Real-IP": "203.0.113.1",
            "X-Forwarded-For": "198.51.100.7, 203.0.113.1",
        },
    )
    assert get_client_ip(request, settings) == "198.51.100.7"  # type: ignore[arg-type]


def test_spoofed_xff_does_not_override_x_real_ip() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.1",
    )
    request = _fake_request(
        peer_host="172.16.2.1",
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "X-Real-IP": "203.0.113.10",
        },
    )
    assert get_client_ip(request, settings) == "203.0.113.10"  # type: ignore[arg-type]


def test_invalid_x_real_ip_falls_back_to_xff() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="10.0.0.0/8",
    )
    request = _fake_request(
        peer_host="10.0.0.1",
        headers={
            "X-Real-IP": "not-an-ip",
            "X-Forwarded-For": "203.0.113.5, 10.0.0.1",
        },
    )
    assert get_client_ip(request, settings) == "203.0.113.5"  # type: ignore[arg-type]


def test_invalid_forwarded_ip_is_ignored() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="127.0.0.1/32",
    )
    request = _fake_request(
        peer_host="127.0.0.1",
        headers={"X-Forwarded-For": "not-an-ip"},
    )
    assert get_client_ip(request, settings) == "127.0.0.1"  # type: ignore[arg-type]


def test_mixed_valid_invalid_xff_chain_rejected() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="10.0.0.0/8",
    )
    request = _fake_request(
        peer_host="10.0.0.1",
        headers={"X-Forwarded-For": "198.51.100.7, garbage, 10.0.0.1"},
    )
    assert get_client_ip(request, settings) == "10.0.0.1"  # type: ignore[arg-type]


def test_xff_parsed_right_to_left_skips_trusted() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="10.0.0.0/8",
    )
    request = _fake_request(
        peer_host="10.0.0.1",
        headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1"},
    )
    assert get_client_ip(request, settings) == "203.0.113.5"  # type: ignore[arg-type]


def test_xff_proxy_add_chain_not_spoofed() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.1",
    )
    request = _fake_request(
        peer_host="172.16.2.1",
        headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.50"},
    )
    assert get_client_ip(request, settings) == "203.0.113.50"  # type: ignore[arg-type]


def test_get_client_ip_ignores_forwarded_when_no_trusted_ips() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="",
    )
    request = _fake_request(
        peer_host="203.0.113.99",
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert get_client_ip(request, settings) == "203.0.113.99"  # type: ignore[arg-type]


def test_no_peer_and_no_trusted_headers_returns_unknown() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="10.0.0.0/8",
    )
    request = _fake_request(peer_host=None)
    assert get_client_ip(request, settings) == "unknown"  # type: ignore[arg-type]


def test_trusted_peer_with_no_forwarded_headers_uses_peer() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.1",
    )
    request = _fake_request(peer_host="172.16.2.1")
    assert get_client_ip(request, settings) == "172.16.2.1"  # type: ignore[arg-type]


def test_empty_xff_falls_back_to_peer() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="172.16.2.1",
    )
    request = _fake_request(
        peer_host="172.16.2.1",
        headers={"X-Forwarded-For": " , "},
    )
    assert get_client_ip(request, settings) == "172.16.2.1"  # type: ignore[arg-type]


def test_xff_all_trusted_falls_back_to_leftmost() -> None:
    settings = make_settings(
        trust_proxy_headers=True,
        trusted_proxy_ips="10.0.0.0/8",
    )
    request = _fake_request(
        peer_host="10.0.0.1",
        headers={"X-Forwarded-For": "10.0.0.5, 10.0.0.1"},
    )
    assert get_client_ip(request, settings) == "10.0.0.5"  # type: ignore[arg-type]
