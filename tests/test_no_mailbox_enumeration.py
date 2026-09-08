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
    assert profile_a["PayloadType"] == profile_b["PayloadType"]

    mail_a = profile_a["PayloadContent"][0]
    mail_b = profile_b["PayloadContent"][0]
    assert set(mail_a.keys()) == set(mail_b.keys())

    # These keys legitimately differ because they embed the requested
    # mailbox (identifiers, UUIDs, display strings, the address itself).
    # A denylist rather than an allowlist means every other field -- present
    # or added later -- is checked, not just the ones we thought of today.
    varying_keys = {
        "PayloadIdentifier",
        "PayloadUUID",
        "PayloadDisplayName",
        "EmailAccountDescription",
        "EmailAddress",
        "IncomingMailServerUsername",
        "OutgoingMailServerUsername",
    }
    mailbox_independent_a = {k: v for k, v in mail_a.items() if k not in varying_keys}
    mailbox_independent_b = {k: v for k, v in mail_b.items() if k not in varying_keys}
    assert mailbox_independent_a == mailbox_independent_b
