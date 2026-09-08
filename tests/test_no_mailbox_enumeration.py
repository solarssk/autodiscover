"""Regression tests for the invariant documented as a "critical security
invariant" in AGENTS.md and a "core security property" in SECURITY.md: the
service must return the same response shape and status code for any
syntactically valid mailbox in an allowed domain, regardless of whether that
mailbox actually exists. The app holds this today only because it never
performs a mailbox-existence lookup at all; these tests exist so a future
change that quietly adds one gets caught here instead of shipping silently.
"""

import plistlib

from fastapi.testclient import TestClient

from tests.conftest import OUTLOOK_REQUEST_TEMPLATE

MAILBOX_A = "alice@example.com"
MAILBOX_B = "completely-different-user@example.com"

# Root-level plist keys that legitimately embed the requested mailbox.
_ROOT_VARYING_KEYS = {
    "PayloadIdentifier",
    "PayloadUUID",
    "PayloadDisplayName",
    "PayloadDescription",
}
# Per-payload keys (inside PayloadContent) that legitimately embed it too.
_PAYLOAD_VARYING_KEYS = {
    "PayloadIdentifier",
    "PayloadUUID",
    "PayloadDisplayName",
    "EmailAccountDescription",
    "EmailAddress",
    "IncomingMailServerUsername",
    "OutgoingMailServerUsername",
}


def _normalize_profile(profile: dict[str, object]) -> dict[str, object]:
    """Strip mailbox-derived values from a whole .mobileconfig plist so two
    profiles for different mailboxes can be compared structurally: same root
    keys, same number of PayloadContent entries, same content in each entry
    once the values that are supposed to vary are removed."""
    payload_content = profile["PayloadContent"]
    assert isinstance(payload_content, list)
    normalized_content = [
        {k: v for k, v in item.items() if k not in _PAYLOAD_VARYING_KEYS}
        for item in payload_content
    ]
    normalized_root = {
        k: v for k, v in profile.items() if k not in _ROOT_VARYING_KEYS and k != "PayloadContent"
    }
    normalized_root["PayloadContent"] = normalized_content
    return normalized_root


def test_outlook_same_shape_for_different_mailboxes(client: TestClient) -> None:
    response_a = client.post(
        "/autodiscover/autodiscover.xml",
        content=OUTLOOK_REQUEST_TEMPLATE.format(email=MAILBOX_A),
        headers={"Content-Type": "text/xml"},
    )
    response_b = client.post(
        "/autodiscover/autodiscover.xml",
        content=OUTLOOK_REQUEST_TEMPLATE.format(email=MAILBOX_B),
        headers={"Content-Type": "text/xml"},
    )

    assert response_a.status_code == response_b.status_code == 200
    normalized_a = response_a.text.replace(MAILBOX_A, "MAILBOX")
    normalized_b = response_b.text.replace(MAILBOX_B, "MAILBOX")
    assert normalized_a == normalized_b


def test_thunderbird_same_shape_for_different_mailboxes(client: TestClient) -> None:
    response_a = client.get("/mail/config-v1.1.xml", params={"emailaddress": MAILBOX_A})
    response_b = client.get("/mail/config-v1.1.xml", params={"emailaddress": MAILBOX_B})

    assert response_a.status_code == response_b.status_code == 200
    normalized_a = response_a.text.replace(MAILBOX_A, "MAILBOX")
    normalized_b = response_b.text.replace(MAILBOX_B, "MAILBOX")
    assert normalized_a == normalized_b


def test_mobileconfig_same_shape_for_different_mailboxes(client: TestClient) -> None:
    response_a = client.get("/mail/ios.mobileconfig", params={"emailaddress": MAILBOX_A})
    response_b = client.get("/mail/ios.mobileconfig", params={"emailaddress": MAILBOX_B})

    assert response_a.status_code == response_b.status_code == 200

    profile_a = plistlib.loads(response_a.content)
    profile_b = plistlib.loads(response_b.content)

    # Compare the whole plist structurally, not just the first payload: a
    # future change that adds or removes a PayloadContent entry for one
    # mailbox but not the other (e.g. a conditional extra payload gated on
    # some existence check) would reveal mailbox existence even if the
    # first entry stayed identical, and a check scoped to PayloadContent[0]
    # alone would never notice.
    assert set(profile_a.keys()) == set(profile_b.keys())
    assert len(profile_a["PayloadContent"]) == len(profile_b["PayloadContent"])
    assert _normalize_profile(profile_a) == _normalize_profile(profile_b)
