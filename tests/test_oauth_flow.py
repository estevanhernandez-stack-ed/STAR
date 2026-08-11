"""The authorization server as a client actually meets it, end to end.

`tests/test_oauth.py` and `tests/test_oauth_ssrf.py` cover the protocol modules
in isolation, which is where the algorithms live. This file covers the seam
those modules are wired across: the routes in `star/server.py`, the redirect
that carries a reader from a client's request to a consent screen and back, and
the point where an issued access token has to open the MCP door.

Every one of these passed as a hand-driven script first. That is the reason the
file exists rather than the reason it does not need to: a flow proved once by
hand is a flow nobody will notice breaking.

No network, no Firestore. The two collections this flow touches are substituted
with dicts, which is what `star/store.py` being the only module that talks to
Firestore buys.
"""

import base64
import hashlib
import secrets
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient

from star import server

RESOURCE = "https://star.626labs.dev"
REDIRECT = "http://127.0.0.1:33418/callback"
READER = "uid-of-the-reader"


class _FakeCollection:
    """A dict wearing the three methods these routes call."""

    def __init__(self):
        self.data = {}

    def save(self, key, document):
        self.data[key] = dict(document)

    def get(self, key):
        return dict(self.data[key]) if key in self.data else None

    def revoke(self, uid, token_id, when):
        if token_id in self.data:
            self.data[token_id]["revoked_at"] = when

    def list_for_family(self, family_id):
        return [
            dict(d) for d in self.data.values() if d.get("family_id") == family_id
        ]

    def revoke_family(self, family_id, when):
        for document in self.data.values():
            if document.get("family_id") == family_id:
                document["revoked_at"] = when


@pytest.fixture
def door(monkeypatch):
    """A client, a token store, and a code store nobody else has touched."""
    monkeypatch.setattr(server, "_client_store", _FakeCollection())
    monkeypatch.setattr(server, "_token_store", _FakeCollection())
    server._pending_authorizations.clear()
    return TestClient(server.app, follow_redirects=False)


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _register(client, **overrides):
    body = {
        "client_name": "Some Desktop Client",
        "redirect_uris": [REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    body.update(overrides)
    return client.post("/oauth/register", json=body)


def _query(location):
    return dict(parse_qsl(urlsplit(location).query))


def _authorize(client, client_id, challenge, **overrides):
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "rooms:read rooms:write",
        "state": "client-state-xyz",
        "resource": RESOURCE,
    }
    params.update(overrides)
    return client.get("/oauth/authorize", params=params)


def _approve(client, state_key, decision="approve"):
    with mock.patch("star.server.verify_token", return_value=READER):
        return client.post(
            "/oauth/authorize/decide",
            json={"state_key": state_key, "decision": decision},
            headers={"Authorization": "Bearer firebase.id.token"},
        )


def test_the_whole_flow_ends_with_a_token_that_opens_the_door(door):
    """Register, authorize, consent, exchange, and call. The point of all of it.

    The last assertion is the one that matters: an access token minted by this
    server is accepted by the MCP door as a credential for this resource. Every
    step before it is machinery in service of that sentence.
    """
    verifier, challenge = _pkce()
    client_id = _register(door).json()["client_id"]

    sent = _authorize(door, client_id, challenge)
    assert sent.status_code == 303
    handed_off = _query(sent.headers["location"])
    assert sent.headers["location"].startswith("/consent.html?")
    # The consent screen is given what it needs to tell the truth and nothing
    # it could leak: a hostname, never the whole redirect URI.
    assert handed_off["redirect_host"] == "127.0.0.1"
    assert handed_off["scope"] == "rooms:read rooms:write"

    answered = _approve(door, handed_off["state_key"])
    assert answered.status_code == 200
    back = _query(answered.json()["redirect_to"])
    assert back["state"] == "client-state-xyz", "the client's own value, echoed"
    assert "code" in back

    issued = door.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": back["code"],
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
            "resource": RESOURCE,
        },
    )
    assert issued.status_code == 200
    # A bearer credential in a response body that a proxy is free to cache is
    # the next reader's access token.
    assert issued.headers["cache-control"] == "no-store"
    grant = issued.json()
    assert grant["token_type"] == "Bearer"
    assert grant["scope"] == "rooms:read rooms:write"
    assert grant["expires_in"] > 0, "an access token that never expires is a card token"

    opened = door.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={
            "Authorization": f"Bearer {grant['access_token']}",
            "MCP-Protocol-Version": "2025-11-25",
        },
    )
    assert opened.status_code == 200
    assert [t["name"] for t in opened.json()["result"]["tools"]] == [
        "list_rooms",
        "get_room",
        "build_room",
        "check_scene",
    ]


def test_the_wrong_verifier_cannot_redeem_a_real_code(door):
    """PKCE, doing the one job it exists for.

    An intercepted authorization code is worth nothing without the verifier
    that never left the client, and this is the assertion that says so.
    """
    _, challenge = _pkce()
    client_id = _register(door).json()["client_id"]
    handed_off = _query(_authorize(door, client_id, challenge).headers["location"])
    code = _query(_approve(door, handed_off["state_key"]).json()["redirect_to"])["code"]

    stolen = door.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_verifier": secrets.token_urlsafe(48),
        },
    )

    assert stolen.status_code == 400
    assert stolen.json()["error"] == "invalid_grant"


def test_an_unregistered_redirect_uri_is_a_dead_end_and_not_a_redirect(door):
    """The asymmetry in `oauth_authorize` is the point of this test.

    Every other refusal in that route redirects, because by then the
    destination has been proved to belong to the client that registered it.
    This one cannot: redirecting to an address nobody validated is precisely
    how an authorization code gets handed to whoever asked for it.
    """
    _, challenge = _pkce()
    client_id = _register(door).json()["client_id"]

    refused = _authorize(
        door, client_id, challenge, redirect_uri="https://not-the-client.example/steal"
    )

    assert refused.status_code == 400
    assert "location" not in refused.headers
    assert "not-the-client.example" not in refused.text


def test_a_declined_request_sends_the_client_away_empty(door):
    """Deny is an answer, and the client is told so in the way OAuth defines.

    It redirects rather than dead-ends, because at this point the destination
    HAS been validated, and a client left hanging on a screen the reader closed
    is a client that never learns the flow ended.
    """
    _, challenge = _pkce()
    client_id = _register(door).json()["client_id"]
    handed_off = _query(_authorize(door, client_id, challenge).headers["location"])

    declined = _approve(door, handed_off["state_key"], decision="deny")

    back = _query(declined.json()["redirect_to"])
    assert back["error"] == "access_denied"
    assert back["state"] == "client-state-xyz"
    assert "code" not in back


def test_a_consent_nobody_signed_in_answered_is_refused(door):
    """The `state_key` proves the question is real. It does not prove who.

    Without this the grant would bind to whoever the browser happened to be,
    or to nobody, on a route whose entire job is deciding whose rooms are being
    handed over.
    """
    _, challenge = _pkce()
    client_id = _register(door).json()["client_id"]
    handed_off = _query(_authorize(door, client_id, challenge).headers["location"])

    with mock.patch("star.server.verify_token", return_value=None):
        anonymous = door.post(
            "/oauth/authorize/decide",
            json={"state_key": handed_off["state_key"], "decision": "approve"},
        )

    assert anonymous.status_code == 401


def test_a_state_key_answered_twice_is_gone_the_second_time(door):
    """One question, one answer. A pending authorization is consumed on use."""
    _, challenge = _pkce()
    client_id = _register(door).json()["client_id"]
    handed_off = _query(_authorize(door, client_id, challenge).headers["location"])

    assert _approve(door, handed_off["state_key"]).status_code == 200
    assert _approve(door, handed_off["state_key"]).status_code == 400


def test_pkce_is_required_and_plain_is_not_a_method(door):
    """OAuth 2.1 requires S256, and a server that quietly accepts `plain`
    advertises a protection it does not have."""
    _, challenge = _pkce()
    client_id = _register(door).json()["client_id"]

    for method in ("plain", "s256", "S512"):
        refused = _authorize(
            door, client_id, challenge, code_challenge_method=method
        )
        assert refused.status_code == 303
        assert _query(refused.headers["location"])["error"] == "invalid_request"


def test_a_client_may_not_register_a_redirect_uri_it_could_not_be_trusted_with(door):
    """HTTPS or loopback, per the spec's Communication Security MUST."""
    refused = _register(door, redirect_uris=["http://evil.example/callback"])

    assert refused.status_code == 400
    assert refused.json()["error"]
