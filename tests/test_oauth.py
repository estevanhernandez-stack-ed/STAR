"""The authorization server as protocol: discovery, PKCE, codes, clients, tokens.

No network and no server. Every module under star/oauth/ is pure or takes an
injected store, which is what star/mcp/protocol.py's own test file established
for the MCP wire and what makes a conformance surface assertable without a
token issued or a client registered. The one network call in the package is
star/oauth/clients.py's fetch, and it lives behind two seams that
tests/test_oauth_ssrf.py drives.

The property this file watches hardest is the one `spec-oauth-as.md`'s Decision
5 makes and that nothing else in the suite would catch: a card token and an
OAuth token travel the same resolver, and only one of them is checked for
expiry and audience. Every test in tests/test_tokens.py passes unmodified,
which is the other half of the same statement — this file asserts the new
behaviour, that file asserts the old behaviour did not move.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from star import tokens as card_tokens
from star.oauth import clients, codes, metadata, pkce, tokens, validate
from star.store import ClientStore, TokenStore
from tests.test_store import _FakeClient

UID = "uid-one"
CLIENT_ID = "star_client_" + "a" * 32
REDIRECT = "http://127.0.0.1:9876/callback"
NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)  # noqa: UP017
VERIFIER = "L4a" + "z" * 40  # 43 characters, the RFC 7636 floor
CHALLENGE = pkce.challenge_for(VERIFIER)
RESOURCE = "https://star.626labs.dev"


def a_store():
    client = _FakeClient()
    return TokenStore(client=client), client


def a_grant(**overrides):
    fields = {
        "uid": UID,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT,
        "scope": "rooms:read rooms:write",
        "code_challenge": CHALLENGE,
        "resource": RESOURCE,
    }
    fields.update(overrides)
    return codes.Grant(**fields)


def stored(client, token_id):
    return client.data[f"mcp_tokens/{token_id}"]


# === metadata ===============================================================


def test_the_protected_resource_document_names_the_resource_and_its_server():
    document = metadata.protected_resource()

    assert document["resource"] == RESOURCE
    assert document["authorization_servers"] == [RESOURCE]
    assert document["scopes_supported"] == list(metadata.SCOPES_SUPPORTED)
    assert document["bearer_methods_supported"] == ["header"]


def test_the_as_metadata_advertises_s256_and_nothing_else():
    """The one field a client is entitled to hang up over.

    OAuth 2.1 requires PKCE and the MCP authorization spec says a client MUST
    refuse to proceed when the AS metadata does not advertise it, so its
    absence is not a missing nicety — it is a connection that never starts.
    """
    document = metadata.authorization_server()

    assert document["code_challenge_methods_supported"] == ["S256"]
    assert "plain" not in json.dumps(document)


def test_the_as_metadata_carries_every_field_the_spec_names():
    document = metadata.authorization_server()

    assert document["issuer"] == RESOURCE
    assert document["authorization_endpoint"] == f"{RESOURCE}/oauth/authorize"
    assert document["token_endpoint"] == f"{RESOURCE}/oauth/token"
    assert document["registration_endpoint"] == f"{RESOURCE}/oauth/register"
    assert document["response_types_supported"] == ["code"]
    assert document["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert document["scopes_supported"] == list(metadata.SCOPES_SUPPORTED)
    assert document["token_endpoint_auth_methods_supported"] == ["none"]
    assert document["client_id_metadata_document_supported"] is True


def test_the_two_documents_agree_about_who_the_authorization_server_is():
    """One deployment in both roles, per the spec: STAR cannot delegate the AS
    role to Google, because it has to validate that a token was issued FOR
    STAR and Google will not mint one carrying STAR's canonical URI."""
    assert metadata.protected_resource()["authorization_servers"] == [
        metadata.authorization_server()["issuer"]
    ]


def test_canonicalising_folds_the_spellings_that_mean_the_same_resource():
    for spelling in (
        "https://star.626labs.dev",
        "https://star.626labs.dev/",
        "HTTPS://STAR.626LABS.DEV",
        "https://star.626labs.dev:443",
    ):
        assert metadata.canonical(spelling) == RESOURCE, spelling


def test_canonicalising_keeps_the_differences_that_are_real_resources():
    """A path is part of a resource identifier. Folding `/mcp` into the origin
    would widen what every token issued here is valid for."""
    assert metadata.canonical("https://star.626labs.dev/mcp") != RESOURCE
    assert metadata.canonical("http://star.626labs.dev") != RESOURCE
    assert metadata.canonical("https://star.626labs.dev:8443") != RESOURCE


def test_an_unusable_resource_identifier_folds_to_nothing_rather_than_to_something():
    for junk in (None, "", "   ", 42, "not a uri", "https://star.626labs.dev#frag"):
        assert metadata.canonical(junk) == "", junk


def test_the_resource_parameter_is_accepted_only_for_this_resource():
    assert metadata.accepts_resource(RESOURCE) is True
    assert metadata.accepts_resource(RESOURCE + "/") is True
    # Absent is accepted on purpose: one resource, nothing to guess.
    assert metadata.accepts_resource(None) is True
    assert metadata.accepts_resource("") is True
    assert metadata.accepts_resource("https://elsewhere.example") is False
    assert metadata.accepts_resource("https://star.626labs.dev/mcp") is False


def test_the_challenge_points_at_the_metadata_document():
    """The whole reason this epic exists. star/mcp/router.py's current bare
    `Bearer` gives a discovery-first client nothing to follow."""
    header = metadata.www_authenticate()

    assert 'resource_metadata="' in header
    assert f"{RESOURCE}/.well-known/oauth-protected-resource" in header
    # No error code when nothing was presented, per RFC 6750.
    assert "error=" not in header


def test_the_challenge_cannot_be_used_to_split_a_response():
    """A newline in a response header is response splitting. The values that
    reach this today are this project's own constants, which is a fact about
    the call sites rather than a property of the function — star/auth.py's
    `_failure_detail` records what it cost to learn that difference."""
    header = metadata.www_authenticate(
        error="invalid_token",
        description='broken\r\nX-Injected: yes\nand a " quote',
        scope="rooms:write",
    )

    assert "\r" not in header
    assert "\n" not in header
    assert "X-Injected: yes" in header  # neutered, not dropped
    # The quote is escaped rather than removed, so it cannot end the quoted
    # string early and turn the rest of the description into auth-params.
    assert '\\"' in header
    assert header.endswith('scope="rooms:write"')


# === PKCE ===================================================================


def test_a_description_long_enough_to_be_cut_is_never_cut_mid_escape():
    """The bound and the escaping have to agree. A truncation landing between
    a backslash and what it escapes leaves a lone trailing backslash, which
    escapes the closing quote and hands the rest of the header to the parser
    as auth-params."""
    header = metadata.www_authenticate(error="invalid_token", description='"' * 400)

    assert header.endswith('"')
    value = header.split('error_description="', 1)[1][:-1]
    assert (len(value) - len(value.rstrip("\\"))) % 2 == 0


def test_a_verifier_that_produced_the_challenge_is_accepted():
    assert pkce.verify(VERIFIER, pkce.challenge_for(VERIFIER)) is True


def test_the_challenge_is_unpadded_base64url_of_the_sha256():
    challenge = pkce.challenge_for(VERIFIER)

    assert len(challenge) == 43
    assert "=" not in challenge
    assert "+" not in challenge and "/" not in challenge
    assert pkce.is_valid_challenge(challenge)


def test_a_verifier_that_did_not_produce_the_challenge_is_refused():
    other = "M4a" + "y" * 40

    assert pkce.verify(other, CHALLENGE) is False
    assert pkce.verify(VERIFIER, pkce.challenge_for(other)) is False


def test_plain_is_refused_outright_rather_than_supported_and_discouraged():
    """Under `plain` the challenge IS the verifier, so anyone who saw the
    authorization request can complete the exchange — the exact attack PKCE
    exists to stop. OAuth 2.1 removes it and the AS metadata never offers it.
    """
    assert pkce.verify(VERIFIER, VERIFIER, "plain") is False
    assert pkce.verify(VERIFIER, CHALLENGE, "plain") is False
    # An absent method defaults to `plain` in OAuth's own reading, so absent
    # has to be refused for the same reason.
    for method in (None, "", "s256", "S512", "PLAIN", 256):
        assert pkce.verify(VERIFIER, CHALLENGE, method) is False, method


def test_a_verifier_below_the_entropy_floor_is_refused_even_if_it_hashes_right():
    """43 characters is 256 bits, which is the point of the whole exercise. A
    four-digit verifier would pass a hash comparison just as happily as a real
    one, and this is where that is refused."""
    short = "abc"

    assert pkce.is_valid_verifier(short) is False
    assert pkce.verify(short, pkce.challenge_for(short)) is False


def test_a_verifier_outside_the_unreserved_alphabet_is_refused():
    for bad in ("a" * 42 + "!", "a" * 42 + " ", "a" * 129, 17, None, "a" * 42 + "+"):
        assert pkce.is_valid_verifier(bad) is False, bad


def test_the_comparison_is_delegated_to_compare_digest():
    """Not `==`. This is a comparison against a value derived from a secret,
    and star/tokens.py makes the same call for the same reason."""
    with mock.patch.object(pkce.hmac, "compare_digest", return_value=False) as never:
        assert pkce.verify(VERIFIER, CHALLENGE) is False

    never.assert_called_once()


# === authorization codes ====================================================


def a_code_store(**kwargs):
    return codes.CodeStore(**kwargs)


def test_a_code_redeems_once_into_the_grant_it_was_issued_for():
    store = a_code_store()
    grant = a_grant()
    code = store.issue(grant, now=1000.0)

    outcome = store.redeem(
        code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        now=1001.0,
    )

    assert isinstance(outcome, codes.Redeemed)
    assert outcome.grant == grant


def test_a_second_redemption_of_the_same_code_fails_and_is_reported_as_a_replay():
    """OAuth 2.1 requires the server to deny it and says it SHOULD revoke every
    token already issued from that code. That is not bookkeeping: the only way
    one code is presented twice is that somebody other than the client that
    requested it got hold of it, so the second presentation is an interception
    report."""
    store = a_code_store()
    code = store.issue(a_grant(), now=1000.0)
    first = store.redeem(
        code, client_id=CLIENT_ID, redirect_uri=REDIRECT, verifier=VERIFIER, now=1001.0
    )
    store.bind_issued(first.receipt, ("access-1", "refresh-1"))

    second = store.redeem(
        code, client_id=CLIENT_ID, redirect_uri=REDIRECT, verifier=VERIFIER, now=1002.0
    )

    assert isinstance(second, codes.Replayed)
    assert second.uid == UID
    assert second.token_ids == ("access-1", "refresh-1")
    assert store.is_spent(code) is True


def test_a_code_past_its_ttl_is_refused():
    store = a_code_store()
    code = store.issue(a_grant(), now=1000.0)

    outcome = store.redeem(
        code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        now=1000.0 + codes.TTL_SECONDS,
    )

    assert isinstance(outcome, codes.Denied)
    assert outcome.reason == codes.UNKNOWN
    assert len(store) == 0


def test_a_code_one_second_inside_the_ttl_still_redeems():
    """The boundary in both directions, so a change to either comparison shows
    up here rather than as a flow that fails for one reader in ten."""
    store = a_code_store()
    code = store.issue(a_grant(), now=1000.0)

    outcome = store.redeem(
        code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        now=1000.0 + codes.TTL_SECONDS - 1,
    )

    assert isinstance(outcome, codes.Redeemed)


def test_a_code_nobody_issued_is_refused_the_same_way_an_expired_one_is():
    store = a_code_store()

    for code in ("f" * 64, "", None, 17):
        outcome = store.redeem(
            code,
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT,
            verifier=VERIFIER,
            now=1000.0,
        )
        assert isinstance(outcome, codes.Denied), code
        assert outcome.reason == codes.UNKNOWN, code


def test_the_wrong_client_the_wrong_redirect_and_the_wrong_verifier_each_refuse():
    for wrong, reason in (
        ({"client_id": "star_client_" + "b" * 32}, codes.CLIENT_MISMATCH),
        ({"redirect_uri": "http://127.0.0.1:1/other"}, codes.REDIRECT_MISMATCH),
        ({"verifier": "Q" * 43}, codes.PKCE_FAILED),
    ):
        store = a_code_store()
        code = store.issue(a_grant(), now=1000.0)
        arguments = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT,
            "verifier": VERIFIER,
            **wrong,
        }

        outcome = store.redeem(code, now=1001.0, **arguments)

        assert isinstance(outcome, codes.Denied), reason
        assert outcome.reason == reason


def test_a_failed_redemption_still_burns_the_code():
    """The deliberate call, with its cost named. A caller holding a real code
    either requested it or intercepted it — 256 bits are not guessed — so
    leaving it alive after a failed check leaves an intercepted code for the
    interceptor to retry with a better guess."""
    store = a_code_store()
    code = store.issue(a_grant(), now=1000.0)

    store.redeem(
        code, client_id="wrong", redirect_uri=REDIRECT, verifier=VERIFIER, now=1001.0
    )
    retry = store.redeem(
        code, client_id=CLIENT_ID, redirect_uri=REDIRECT, verifier=VERIFIER, now=1002.0
    )

    assert isinstance(retry, codes.Replayed)


def test_the_bound_holds_and_refuses_to_issue_rather_than_growing():
    """star/guards.py's RateLimiter posture, for the documented reason: the
    stale sweep is O(n) and runs on the single-threaded loop every open SSE
    stream shares, so a store already at capacity that accepts one more makes
    every future call cost more for everyone."""
    store = a_code_store(max_keys=3)

    issued = [store.issue(a_grant(), now=1000.0) for _ in range(5)]

    assert len(store) == 3
    assert issued[:3] == [code for code in issued[:3] if code]
    assert issued[3] is None and issued[4] is None


def test_the_sweep_frees_the_bound_once_the_codes_expire():
    """The bound is a ceiling on concurrent in-flight consents, not on daily
    volume. A store that filled up an hour ago and never recovered would be a
    denial of service with a sixty-second fuse."""
    store = a_code_store(max_keys=2)
    store.issue(a_grant(), now=1000.0)
    store.issue(a_grant(), now=1000.0)
    assert store.issue(a_grant(), now=1000.0) is None

    later = store.issue(a_grant(), now=1000.0 + codes.TTL_SECONDS + 1)

    assert later is not None
    assert len(store) == 1


def test_a_code_is_never_its_own_dict_key():
    """A traceback, a debugger, or a `repr` prints this object's keys, and a
    key that is a live credential is a credential in a crash report."""
    store = a_code_store()
    code = store.issue(a_grant(), now=1000.0)

    assert code not in json.dumps(list(store._entries))


def test_every_issued_code_is_distinct():
    store = a_code_store()

    minted = {store.issue(a_grant(), now=1000.0) for _ in range(50)}

    assert len(minted) == 50


# === clients: dynamic registration ==========================================


def test_dcr_refuses_a_redirect_uri_that_is_neither_https_nor_loopback():
    for uri in (
        "http://example.com/callback",
        "http://192.168.1.5/callback",
        "http://localhost.attacker.example/callback",
        "http://127.0.0.1.attacker.example/callback",
        "myapp://callback",
        "https://user:pw@example.com/callback",
        "https://example.com/callback#fragment",
        "not a uri",
        "",
    ):
        outcome = clients.register({"redirect_uris": [uri]}, NOW)

        assert isinstance(outcome, clients.Rejected), uri
        assert outcome.error == clients.INVALID_REDIRECT_URI, uri


def test_dcr_accepts_https_and_the_three_loopback_hosts_on_any_port():
    """RFC 8252's loopback flow: the client binds whatever port the operating
    system gives it, so a fixed port would refuse every second launch. And
    there is no certificate for 127.0.0.1 to serve, which is why http is
    allowed for exactly these three hosts and nowhere else."""
    for uri in (
        "https://client.example/callback",
        "http://127.0.0.1:9876/callback",
        "http://127.0.0.1:1/callback",
        "http://localhost:52341/cb",
        "http://[::1]:8080/cb",
        "https://localhost:8443/cb",
    ):
        outcome = clients.register({"redirect_uris": [uri]}, NOW)

        assert isinstance(outcome, clients.Client), uri
        assert outcome.redirect_uris == (uri,)


def test_dcr_requires_redirect_uris_at_all():
    for document in ({}, {"redirect_uris": []}, {"redirect_uris": "one"}, "nope", None):
        outcome = clients.register(document, NOW)

        assert isinstance(outcome, clients.Rejected), document


def test_dcr_refuses_a_client_that_thinks_it_has_a_secret():
    """Public clients only. Issuing a secret to a program that ships to a
    laptop is theatre, and a client that believes it registered with one will
    send it and be confused when it changes nothing."""
    outcome = clients.register(
        {"redirect_uris": ["https://c.example/cb"], "token_endpoint_auth_method": "client_secret_post"},
        NOW,
    )

    assert isinstance(outcome, clients.Rejected)
    assert outcome.error == clients.INVALID_CLIENT_METADATA
    assert "`none`" in outcome.description


def test_dcr_refuses_a_grant_type_or_response_type_this_server_does_not_run():
    for document in (
        {"redirect_uris": ["https://c.example/cb"], "grant_types": ["password"]},
        {"redirect_uris": ["https://c.example/cb"], "grant_types": ["implicit"]},
        {"redirect_uris": ["https://c.example/cb"], "response_types": ["token"]},
    ):
        outcome = clients.register(document, NOW)

        assert isinstance(outcome, clients.Rejected), document
        assert outcome.error == clients.INVALID_CLIENT_METADATA


def test_dcr_refuses_a_scope_this_server_does_not_offer_rather_than_dropping_it():
    """Silently narrowing a registration is how a client ends up asking for
    something it was told it had and being refused at `/authorize` with no
    explanation."""
    outcome = clients.register(
        # A scope this server genuinely does not offer. It used to be
        # `rooms:delete`, which stopped being an example of an unknown scope
        # the day delete shipped — a fixture that quietly becomes valid is a
        # test that quietly stops testing.
        {"redirect_uris": ["https://c.example/cb"], "scope": "rooms:read rooms:publish"},
        NOW,
    )

    assert isinstance(outcome, clients.Rejected)
    assert "rooms:publish" in outcome.description
    assert " ".join(metadata.SCOPES_SUPPORTED) in outcome.description


def test_dcr_defaults_an_absent_scope_to_everything_on_offer():
    outcome = clients.register({"redirect_uris": ["https://c.example/cb"]}, NOW)

    assert outcome.scope == " ".join(metadata.SCOPES_DEFAULT)
    assert "rooms:delete" not in outcome.scope, (
        "a client that named no scope must not come away registered for "
        "delete — registration is what a client may ASK for, and a blank "
        "field should never be how a reader is asked to hand over their "
        "ability to keep their own rooms"
    )


def test_a_registered_client_id_can_never_be_mistaken_for_a_metadata_url():
    """`lookup` routes on the shape of the id, so the two families have to be
    disjoint by construction rather than by luck."""
    outcome = clients.register({"redirect_uris": ["https://c.example/cb"]}, NOW)

    assert outcome.client_id.startswith("star_client_")
    assert clients.looks_like_metadata_document(outcome.client_id) is False
    assert len({clients.new_client_id() for _ in range(50)}) == 50


def test_the_registration_response_carries_no_secret_and_no_secret_expiry():
    """RFC 7591 requires `client_secret_expires_at` only when a secret was
    issued. Including it set to zero would tell a client it holds a
    non-expiring secret it does not hold."""
    client = clients.register({"redirect_uris": ["https://c.example/cb"]}, NOW)

    body = clients.registration_response(client, 1000)

    assert "client_secret" not in body
    assert "client_secret_expires_at" not in body
    assert body["token_endpoint_auth_method"] == "none"


def test_a_redirect_the_client_never_registered_is_refused():
    """The one check at `/authorize` that cannot be skipped. An AS that
    redirects a code to a URI the client never registered is an open
    redirector with credentials flowing through it: an attacker starts a flow
    under a legitimate client's id, names their own callback, and the reader
    approves a screen showing the legitimate client's name."""
    client = clients.register(
        {"redirect_uris": ["https://client.example/cb"]}, NOW
    )

    assert clients.redirect_allowed(client, "https://client.example/cb") is True
    for wrong in (
        "https://client.example/cb/more",
        "https://client.example/cb?next=https://elsewhere.example",
        "https://client.example/CB",
        "https://attacker.example/cb",
        "https://client.example:443/cb",
        "",
        None,
        17,
    ):
        assert clients.redirect_allowed(client, wrong) is False, wrong


def test_a_loopback_client_may_bind_any_port_and_nothing_else_may():
    """RFC 8252 §7.3's MUST, and it costs nothing: any program on that machine
    can bind any loopback port already, so pinning one buys no security and
    breaks every second launch. The exception stops at the three loopback
    hosts — two https URLs differing only in port are two endpoints."""
    loopback = clients.register(
        {"redirect_uris": ["http://127.0.0.1:9876/callback"]}, NOW
    )
    remote = clients.register({"redirect_uris": ["https://client.example:443/cb"]}, NOW)

    assert clients.redirect_allowed(loopback, "http://127.0.0.1:51234/callback") is True
    assert clients.redirect_allowed(loopback, "http://127.0.0.1/callback") is True
    # Everything else about the URI still has to match.
    assert clients.redirect_allowed(loopback, "http://127.0.0.1:51234/other") is False
    assert clients.redirect_allowed(loopback, "http://localhost:51234/callback") is False
    assert clients.redirect_allowed(loopback, "https://127.0.0.1:51234/callback") is False
    assert clients.redirect_allowed(remote, "https://client.example:8443/cb") is False


def test_a_registered_client_survives_a_round_trip_through_its_document():
    client = clients.register(
        {"redirect_uris": ["https://c.example/cb"], "client_name": "Desk"}, NOW
    )

    assert clients.from_document(clients.to_document(client)) == client
    assert clients.from_document(None) is None
    assert clients.from_document({}) is None


# === clients: metadata documents ============================================


def a_cimd_document(url, **overrides):
    document = {
        "client_id": url,
        "client_name": "A desktop client",
        "redirect_uris": ["http://127.0.0.1:9876/callback"],
    }
    document.update(overrides)
    return document


def test_cimd_refuses_a_document_whose_client_id_is_not_its_url():
    """The whole mechanism. Without it, anybody who can host JSON can publish a
    document naming somebody else's client id, and the consent screen shows the
    victim's name."""
    url = "https://client.example/id.json"
    for claimed in (
        "https://someone-else.example/id.json",
        "https://client.example/id.json/",
        "https://CLIENT.example/id.json",
        "http://client.example/id.json",
        "",
        None,
    ):
        fetched = clients.Fetched(url, a_cimd_document(url, client_id=claimed))

        outcome = clients.from_metadata_document(url, fetched)

        assert isinstance(outcome, clients.Rejected), claimed
        assert outcome.description == clients.CIMD_REFUSED


def test_cimd_compares_against_the_id_presented_not_the_url_a_redirect_ended_on():
    """A redirect must not be able to change which identity a document may
    claim. The document below is internally consistent with where it was
    finally served from, and it still does not answer the question that was
    asked."""
    presented = "https://client.example/id.json"
    final = "https://cdn.example/id.json"
    fetched = clients.Fetched(final, a_cimd_document(final))

    outcome = clients.from_metadata_document(presented, fetched)

    assert isinstance(outcome, clients.Rejected)


def test_cimd_requires_the_three_fields_the_spec_names():
    url = "https://client.example/id.json"
    for missing in clients.REQUIRED_CIMD_FIELDS:
        document = a_cimd_document(url)
        del document[missing]
        outcome = clients.from_metadata_document(url, clients.Fetched(url, document))

        assert isinstance(outcome, clients.Rejected), missing


def test_cimd_holds_a_documents_redirect_uris_to_the_same_rule_dcr_uses():
    url = "https://client.example/id.json"
    fetched = clients.Fetched(
        url, a_cimd_document(url, redirect_uris=["http://elsewhere.example/cb"])
    )

    outcome = clients.from_metadata_document(url, fetched)

    assert isinstance(outcome, clients.Rejected)
    assert outcome.error == clients.INVALID_REDIRECT_URI


def test_an_unsafe_url_becomes_the_same_refusal_a_bad_document_does():
    """The generic answer, for star/tokens.py's reason. The caller supplying
    the URL is unauthenticated, and telling them the fetch was refused for a
    private address rather than for a 404 is a probe with this server's network
    position behind it."""
    url = "https://client.example/id.json"

    refused = clients.from_metadata_document(url, clients.Unsafe("address:private"))
    missing = clients.from_metadata_document(
        url, clients.Fetched(url, {"client_id": url})
    )

    assert refused.description == missing.description == clients.CIMD_REFUSED


def test_a_good_metadata_document_becomes_a_client_labelled_as_one():
    url = "https://client.example/id.json"
    fetched = clients.Fetched(url, a_cimd_document(url))

    outcome = clients.from_metadata_document(url, fetched)

    assert isinstance(outcome, clients.Client)
    assert outcome.client_id == url
    assert outcome.client_name == "A desktop client"
    assert outcome.source == "cimd"


@pytest.mark.asyncio
async def test_lookup_routes_an_https_id_to_the_fetch_and_everything_else_to_the_store():
    client = _FakeClient()
    store = ClientStore(client=client)
    registered = clients.register({"redirect_uris": ["https://c.example/cb"]}, NOW)
    store.save(registered.client_id, clients.to_document(registered))
    url = "https://client.example/id.json"

    with mock.patch.object(
        clients, "fetch_document", return_value=clients.Fetched(url, a_cimd_document(url))
    ) as fetched:
        by_url = await clients.lookup(url, store)
        by_id = await clients.lookup(registered.client_id, store)
        unknown = await clients.lookup("star_client_" + "9" * 32, store)

    fetched.assert_called_once_with(url)
    assert by_url.source == "cimd"
    assert by_id == registered
    assert isinstance(unknown, clients.Rejected)
    assert "No client is registered" in unknown.description


@pytest.mark.asyncio
async def test_the_cimd_fetch_never_runs_on_the_event_loop():
    """urllib is blocking and this loop is shared with every open SSE stream on
    the instance. A five-second fetch on it is a five-second stall for every
    reader watching a build."""
    import threading

    url = "https://client.example/id.json"
    seen = []

    def _fetch(target):
        seen.append(threading.get_ident())
        return clients.Fetched(target, a_cimd_document(target))

    with mock.patch.object(clients, "fetch_document", side_effect=_fetch):
        await clients.lookup(url, ClientStore(client=_FakeClient()))

    assert seen and threading.get_ident() not in seen


# === tokens: issuance, exchange, rotation ===================================


async def a_pair(store, **overrides):
    fields = {
        "uid": UID,
        "client_id": CLIENT_ID,
        "scope": "rooms:read rooms:write",
        "audience": RESOURCE,
        "store": store,
        "now": NOW,
    }
    fields.update(overrides)
    return await tokens.issue_pair(**fields)


@pytest.mark.asyncio
async def test_an_issued_access_token_is_a_card_token_plus_the_five_oauth_fields():
    """`spec-oauth-as.md`'s Decision 1: opaque tokens on the existing shape,
    not JWTs. The one thing a JWT buys — stateless validation across instances
    — is worth nothing on a deployment pinned to `--max-instances=1`, and this
    door already performs the database read on every call."""
    store, client = a_store()

    issued = await a_pair(store)

    document = stored(client, issued.access_token_id)
    assert set(document) == {
        "token_id",
        "uid",
        "secret_sha256",
        "label",
        "created_at",
        "last_used_at",
        "revoked_at",
        "kind",
        "client_id",
        "audience",
        "scope",
        "expires_at",
        "family_id",
    }
    assert document["kind"] == card_tokens.ACCESS
    assert document["audience"] == RESOURCE
    assert document["scope"] == "rooms:read rooms:write"
    assert document["expires_at"] == (NOW + timedelta(hours=1)).isoformat()


@pytest.mark.asyncio
async def test_neither_half_of_an_issued_pair_stores_its_plaintext():
    store, client = a_store()

    issued = await a_pair(store)

    written = json.dumps(client.data)
    assert issued.access_token not in written
    assert issued.refresh_token not in written
    _, secret = card_tokens.parse(issued.access_token)
    assert secret not in written


@pytest.mark.asyncio
async def test_the_two_halves_of_a_pair_share_a_family_and_differ_in_lifetime():
    store, client = a_store()

    issued = await a_pair(store)

    access = stored(client, issued.access_token_id)
    refresh = stored(client, issued.refresh_token_id)
    assert access["family_id"] == refresh["family_id"] == issued.family_id
    assert access["kind"] == card_tokens.ACCESS
    assert refresh["kind"] == card_tokens.REFRESH
    assert refresh["expires_at"] > access["expires_at"]


@pytest.mark.asyncio
async def test_the_token_response_is_rfc_6749s_shape():
    store, _ = a_store()

    body = (await a_pair(store)).body()

    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert body["scope"] == "rooms:read rooms:write"
    assert body["access_token"].startswith("star_")
    assert body["refresh_token"].startswith("star_")


@pytest.mark.asyncio
async def test_a_code_exchanges_into_a_pair_bound_to_this_resource():
    store, client = a_store()
    code_store = codes.CodeStore()
    code = code_store.issue(a_grant(), now=NOW.timestamp())

    issued = await tokens.exchange_code(
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        resource=RESOURCE,
        code_store=code_store,
        store=store,
        now=NOW,
    )

    assert isinstance(issued, tokens.Issued)
    assert stored(client, issued.access_token_id)["audience"] == RESOURCE
    assert stored(client, issued.access_token_id)["uid"] == UID


@pytest.mark.asyncio
async def test_the_exchange_records_what_the_code_bought_so_a_replay_can_undo_it():
    """One function rather than three the endpoint calls in order, because
    skipping the third leaves OAuth 2.1's answer to a replayed code half-built
    and a half-built revocation is the kind of gap nobody notices until a code
    has already leaked."""
    store, _ = a_store()
    code_store = codes.CodeStore()
    code = code_store.issue(a_grant(), now=NOW.timestamp())

    issued = await tokens.exchange_code(
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        resource=RESOURCE,
        code_store=code_store,
        store=store,
        now=NOW,
    )
    replay = code_store.redeem(
        code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        now=NOW.timestamp(),
    )

    assert isinstance(replay, codes.Replayed)
    assert set(replay.token_ids) == {issued.access_token_id, issued.refresh_token_id}


@pytest.mark.asyncio
async def test_a_replayed_code_kills_the_tokens_the_first_exchange_produced():
    store, client = a_store()
    code_store = codes.CodeStore()
    code = code_store.issue(a_grant(), now=NOW.timestamp())
    exchange = {
        "code": code,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT,
        "verifier": VERIFIER,
        "resource": RESOURCE,
        "code_store": code_store,
        "store": store,
        "now": NOW,
    }
    issued = await tokens.exchange_code(**exchange)

    denied = await tokens.exchange_code(**exchange)

    assert isinstance(denied, tokens.Denied)
    assert denied.error == tokens.INVALID_GRANT
    assert stored(client, issued.access_token_id)["revoked_at"] == NOW.isoformat()
    assert stored(client, issued.refresh_token_id)["revoked_at"] == NOW.isoformat()
    assert await card_tokens.resolve(f"Bearer {issued.access_token}", store) is (
        card_tokens.REVOKED
    )


@pytest.mark.asyncio
async def test_every_way_an_exchange_can_fail_gives_the_same_sentence():
    """A message that named which check failed would tell whoever holds a
    stolen code exactly which part of it to change."""
    store, _ = a_store()
    answers = []
    for wrong in (
        {"client_id": "star_client_" + "b" * 32},
        {"redirect_uri": "http://127.0.0.1:1/other"},
        {"verifier": "Q" * 43},
        {"code": "f" * 64},
    ):
        code_store = codes.CodeStore()
        code = code_store.issue(a_grant(), now=NOW.timestamp())
        answers.append(
            await tokens.exchange_code(
                **{
                    "code": code,
                    "client_id": CLIENT_ID,
                    "redirect_uri": REDIRECT,
                    "verifier": VERIFIER,
                    "resource": RESOURCE,
                    "code_store": code_store,
                    "store": store,
                    "now": NOW,
                    **wrong,
                }
            )
        )

    assert {answer.error for answer in answers} == {tokens.INVALID_GRANT}
    assert len({answer.description for answer in answers}) == 1


@pytest.mark.asyncio
async def test_an_exchange_naming_another_resource_is_refused():
    """RFC 8707. A client that asked for a token for one resource and received
    one for another has been handed a credential it did not ask for."""
    store, _ = a_store()
    code_store = codes.CodeStore()
    code = code_store.issue(a_grant(), now=NOW.timestamp())

    denied = await tokens.exchange_code(
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        resource="https://elsewhere.example",
        code_store=code_store,
        store=store,
        now=NOW,
    )

    assert isinstance(denied, tokens.Denied)
    assert denied.error == tokens.INVALID_TARGET


@pytest.mark.asyncio
async def test_a_grant_carrying_a_foreign_resource_is_refused_at_the_exchange_too():
    """Checked here as well as at `/authorize`, because a token's audience is
    the one field the whole resource-server side turns on and it must not be
    able to arrive from a path that was checked once."""
    store, _ = a_store()
    code_store = codes.CodeStore()
    code = code_store.issue(
        a_grant(resource="https://elsewhere.example"), now=NOW.timestamp()
    )

    denied = await tokens.exchange_code(
        code=code,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT,
        verifier=VERIFIER,
        resource=None,
        code_store=code_store,
        store=store,
        now=NOW,
    )

    assert isinstance(denied, tokens.Denied)
    assert denied.error == tokens.INVALID_TARGET


@pytest.mark.asyncio
async def test_redeeming_a_refresh_token_issues_a_new_pair_and_kills_the_old_one():
    """OAuth 2.1's rotation requirement for public clients, which every client
    here is."""
    store, client = a_store()
    first = await a_pair(store)
    later = NOW + timedelta(minutes=30)

    second = await tokens.refresh(
        refresh_token=first.refresh_token, client_id=CLIENT_ID, store=store, now=later
    )

    assert isinstance(second, tokens.Issued)
    assert second.refresh_token != first.refresh_token
    assert second.access_token != first.access_token
    assert stored(client, first.refresh_token_id)["revoked_at"] == later.isoformat()
    assert await card_tokens.resolve(f"Bearer {first.refresh_token}", store) is (
        card_tokens.REVOKED
    )


@pytest.mark.asyncio
async def test_rotation_keeps_the_family_the_scope_and_the_audience():
    store, client = a_store()
    first = await a_pair(store)

    second = await tokens.refresh(
        refresh_token=first.refresh_token, client_id=CLIENT_ID, store=store, now=NOW
    )

    document = stored(client, second.access_token_id)
    assert second.family_id == first.family_id
    assert document["scope"] == "rooms:read rooms:write"
    assert document["audience"] == RESOURCE
    assert document["client_id"] == CLIENT_ID


@pytest.mark.asyncio
async def test_reusing_an_already_rotated_refresh_token_ends_the_whole_family():
    """Rotation alone denies the second presenter. What it cannot do is say
    WHICH of the two was the thief, since both hold something this server
    issued — so the family dies and both go back through consent. Refusing to
    guess is the only correct answer available."""
    store, client = a_store()
    first = await a_pair(store)
    second = await tokens.refresh(
        refresh_token=first.refresh_token, client_id=CLIENT_ID, store=store, now=NOW
    )
    later = NOW + timedelta(minutes=5)

    denied = await tokens.refresh(
        refresh_token=first.refresh_token, client_id=CLIENT_ID, store=store, now=later
    )

    assert isinstance(denied, tokens.Denied)
    assert stored(client, second.access_token_id)["revoked_at"] == later.isoformat()
    assert stored(client, second.refresh_token_id)["revoked_at"] == later.isoformat()


@pytest.mark.asyncio
async def test_an_expired_refresh_token_is_refused():
    store, _ = a_store()
    issued = await a_pair(store)

    denied = await tokens.refresh(
        refresh_token=issued.refresh_token,
        client_id=CLIENT_ID,
        store=store,
        now=NOW + timedelta(days=31),
    )

    assert isinstance(denied, tokens.Denied)


@pytest.mark.asyncio
async def test_an_access_token_cannot_be_exchanged_as_a_refresh_token():
    store, _ = a_store()
    issued = await a_pair(store)

    denied = await tokens.refresh(
        refresh_token=issued.access_token, client_id=CLIENT_ID, store=store, now=NOW
    )

    assert isinstance(denied, tokens.Denied)


@pytest.mark.asyncio
async def test_a_card_token_cannot_be_laundered_into_an_oauth_session():
    """A card token is long-lived by design and a reader issued it for a
    different purpose. Exchanging one for a rotating OAuth pair would turn a
    credential nobody scoped into a credential the scope model believes it
    checked."""
    store, _ = a_store()
    plaintext, _ = await card_tokens.issue(UID, "desktop agent", store, now=NOW)

    denied = await tokens.refresh(
        refresh_token=plaintext, client_id=CLIENT_ID, store=store, now=NOW
    )

    assert isinstance(denied, tokens.Denied)


@pytest.mark.asyncio
async def test_a_refresh_request_naming_the_wrong_client_is_refused():
    store, _ = a_store()
    issued = await a_pair(store)

    denied = await tokens.refresh(
        refresh_token=issued.refresh_token,
        client_id="star_client_" + "c" * 32,
        store=store,
        now=NOW,
    )
    allowed = await tokens.refresh(
        refresh_token=issued.refresh_token, client_id=None, store=store, now=NOW
    )

    assert isinstance(denied, tokens.Denied)
    # Omitted is accepted: a public client has no secret for the id to be
    # checked against, so the id is corroboration rather than authentication.
    assert isinstance(allowed, tokens.Issued)


@pytest.mark.asyncio
async def test_a_refresh_token_nobody_issued_is_refused_without_a_read():
    store, _ = a_store()

    with mock.patch.object(store, "get", side_effect=AssertionError("read")):
        denied = await tokens.refresh(
            refresh_token="not-a-star-token", client_id=None, store=store, now=NOW
        )

    assert isinstance(denied, tokens.Denied)


@pytest.mark.asyncio
async def test_a_write_that_fails_hands_back_no_credential():
    """star/tokens.py's `issue` posture: a caller holding a plaintext for a
    token that never landed holds a credential that will be refused forever."""
    store, _ = a_store()

    with (
        mock.patch.object(store, "save", side_effect=RuntimeError("firestore down")),
        pytest.raises(RuntimeError),
    ):
        await a_pair(store)


# === validate: the resource-server side =====================================


async def an_identity(store, **overrides):
    issued = await a_pair(store, **overrides)
    return await card_tokens.resolve(f"Bearer {issued.access_token}", store, now=NOW)


@pytest.mark.asyncio
async def test_a_card_token_with_neither_field_is_still_accepted_for_anything():
    """The constraint the whole epic is held to. `harness/runs/*.md` are
    committed transcripts of this credential working, and `claude mcp add
    --header` uses it."""
    store, _ = a_store()
    plaintext, _ = await card_tokens.issue(UID, "desktop agent", store, now=NOW)

    identity = await card_tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert identity.oauth is None
    for need in (None, *metadata.SCOPES_SUPPORTED):
        outcome = validate.check(identity, need=need, now=NOW + timedelta(days=400))
        assert isinstance(outcome, validate.Allowed), need


@pytest.mark.asyncio
async def test_a_live_oauth_token_is_accepted_for_the_scope_it_carries():
    store, _ = a_store()
    identity = await an_identity(store, scope="rooms:read")

    allowed = validate.check(identity, need="rooms:read", now=NOW)
    denied = validate.check(identity, need="rooms:write", now=NOW)

    assert isinstance(allowed, validate.Allowed)
    assert isinstance(denied, validate.Denied)
    assert denied.status == 403
    assert denied.error == validate.INSUFFICIENT_SCOPE
    assert denied.scope == "rooms:write"


@pytest.mark.asyncio
async def test_an_expired_access_token_is_refused_with_a_401():
    store, _ = a_store()
    identity = await an_identity(store)

    inside = validate.check(identity, need="rooms:read", now=NOW + timedelta(minutes=59))
    outside = validate.check(identity, need="rooms:read", now=NOW + timedelta(hours=2))

    assert isinstance(inside, validate.Allowed)
    assert isinstance(outside, validate.Denied)
    assert outside.status == 401
    assert outside.error == validate.INVALID_TOKEN
    assert outside.reason == "expired"


@pytest.mark.asyncio
async def test_a_token_whose_audience_is_another_resource_is_refused():
    """The MCP authorization spec's MUST, and the reason STAR cannot delegate
    the AS role: a token has to be validated as issued FOR this server."""
    store, _ = a_store()
    for audience in ("https://elsewhere.example", "https://star.626labs.dev/mcp", ""):
        identity = await an_identity(store, audience=audience)

        outcome = validate.check(identity, need="rooms:read", now=NOW)

        assert isinstance(outcome, validate.Denied), audience
        assert outcome.status == 401, audience
        assert outcome.reason == "audience", audience


@pytest.mark.asyncio
async def test_the_audience_check_tolerates_a_different_spelling_of_this_resource():
    store, _ = a_store()
    for audience in (RESOURCE, RESOURCE + "/", "HTTPS://STAR.626LABS.DEV"):
        identity = await an_identity(store, audience=audience)

        assert isinstance(validate.check(identity, now=NOW), validate.Allowed), audience


@pytest.mark.asyncio
async def test_a_refresh_token_presented_as_a_bearer_token_is_refused():
    """It resolves — it is a real, unrevoked credential — and it must still not
    open the door. The kind check is first for exactly this."""
    store, _ = a_store()
    issued = await a_pair(store)

    identity = await card_tokens.resolve(f"Bearer {issued.refresh_token}", store, now=NOW)
    outcome = validate.check(identity, need="rooms:read", now=NOW)

    assert isinstance(identity, card_tokens.TokenIdentity)
    assert isinstance(outcome, validate.Denied)
    assert outcome.status == 401
    assert outcome.reason == "wrong_kind"


def test_an_unreadable_expiry_counts_as_expired():
    """Fail closed. A wrong `last_used_at` shows a reader a stale date; a wrong
    `expires_at` read generously is a one-hour credential that never ends."""
    for stamp in ("", None, 17, "yesterday", "2026-13-45"):
        assert validate.expired(stamp, NOW) is True, stamp


def test_a_naive_expiry_stamp_is_read_as_utc():
    """Everything this project writes is `now(timezone.utc).isoformat()`, and a
    stamp that lost its offset in a round trip is still describing UTC."""
    assert validate.expired("2026-08-10T13:00:00", NOW) is False
    assert validate.expired("2026-08-10T11:00:00", NOW) is True


def test_a_token_carrying_only_some_oauth_fields_is_treated_as_oauth():
    """The fail-closed reading of a malformed document. Requiring `kind` would
    let one dropped field turn a one-hour token into a permanent one."""
    facts = card_tokens.oauth_facts({"expires_at": "2099-01-01T00:00:00+00:00"})

    assert facts is not None
    outcome = validate.check(
        card_tokens.TokenIdentity(uid=UID, token_id="t", oauth=facts), now=NOW
    )
    assert isinstance(outcome, validate.Denied)


def test_a_request_for_more_than_the_client_registered_is_narrowed_to_what_it_holds():
    """The ceiling on what the consent screen may offer. A reader approving a
    screen is approving what the screen said, so anything the screen can print
    has to already be true — and the way to keep that true is to print the
    intersection rather than to refuse the request."""
    assert validate.requested_scope("rooms:read", "rooms:read rooms:write") == "rooms:read"
    assert validate.requested_scope("rooms:write rooms:read", "rooms:read rooms:write") == (
        "rooms:read rooms:write"
    )
    # Absent gets everything the client registered for, which is RFC 6749's
    # default and is safe because the consent screen is the ceiling.
    assert validate.requested_scope(None, "rooms:read") == "rooms:read"
    assert validate.requested_scope("", "rooms:read") == "rooms:read"
    # THE CASE THAT COULD NOT ATTACH. A client registered for the two
    # non-destructive scopes, asking for all three this server advertises.
    assert validate.requested_scope(
        "rooms:read rooms:write rooms:delete", "rooms:read rooms:write"
    ) == "rooms:read rooms:write"
    assert validate.requested_scope("rooms:write", "rooms:read") is None, (
        "and an empty intersection is still a refusal: there is nothing to "
        "grant, and a screen offering nothing is not a question worth asking"
    )
    assert validate.requested_scope("rooms:publish", "rooms:read rooms:write") is None
    assert validate.requested_scope(17, "rooms:read") is None
    assert validate.requested_scope("rooms:read", "") is None


def test_a_client_registered_for_nothing_gets_nothing_rather_than_an_empty_grant():
    """Reachable, and it used to return "" rather than None.

    `clients._scope` maps an ABSENT scope field to SCOPES_DEFAULT, but a field
    holding only whitespace is a string with no unknown scopes in it, so it
    registers as the empty string. Asking for nothing against that registration
    returned "", which is not None — and `oauth_authorize` refuses only on
    None, so the flow went on to draw a consent screen for a grant authorising
    nothing and mint a token to match.
    """
    assert validate.requested_scope(None, "") is None
    assert validate.requested_scope("", "   ") is None
    assert validate.requested_scope("rooms:read", "   ") is None


def test_narrowing_can_only_ever_shrink():
    """The property the old outright refusal was protecting, and the one thing
    about this function that must not change. An intersection cannot introduce
    a scope a client's registration lacks — no ordering of the arguments, and
    no request, makes it grant something that was not already on both sides."""
    registered = "rooms:read"
    for asked in (
        "rooms:delete",
        "rooms:read rooms:delete",
        "rooms:read rooms:write rooms:delete",
        "rooms:write",
        "",
        None,
    ):
        granted = validate.requested_scope(asked, registered)
        if granted is None:
            continue
        assert set(granted.split()) <= set(registered.split()), asked


def test_each_tool_maps_to_the_scope_its_description_already_implies():
    """`spec-oauth-as.md`'s Decision 4: the free-versus-spends split every
    description in star/mcp/tools.py already states, so the consent screen can
    say something true and specific rather than asking for everything."""
    assert validate.scope_for("list_rooms") == "rooms:read"
    assert validate.scope_for("get_room") == "rooms:read"
    assert validate.scope_for("build_room") == "rooms:write"
    assert validate.scope_for("check_scene") == "rooms:write"
    assert validate.scope_for("something_new") is None


# --- authorize: resolve and check as one call -------------------------------


@pytest.mark.asyncio
async def test_authorize_composes_the_two_halves_so_the_wiring_cannot_get_one():
    """`resolve` deliberately does not enforce expiry or audience — it has no
    opinion about which HTTP status the answer becomes — so a transport that
    calls it and forgets validate.py accepts expired tokens forever."""
    store, _ = a_store()
    issued = await a_pair(store)
    header = f"Bearer {issued.access_token}"

    live = await validate.authorize(header, store, need="rooms:read", now=NOW)
    dead = await validate.authorize(
        header, store, need="rooms:read", now=NOW + timedelta(hours=2)
    )

    assert isinstance(live, validate.Allowed)
    assert isinstance(dead, validate.Denied)
    assert dead.status == 401


@pytest.mark.asyncio
async def test_the_three_refusals_travel_through_authorize_word_for_word():
    """Nothing is re-worded. star/tokens.py argues at length that a token of
    the wrong shape, an unknown id, and a wrong secret are ONE answer, and a
    second file paraphrasing them is how that stops being true."""
    store, _ = a_store()
    issued = await a_pair(store)

    missing = await validate.authorize(None, store, now=NOW)
    unknown = await validate.authorize("Bearer nonsense", store, now=NOW)
    await asyncio.to_thread(
        store.revoke, UID, issued.access_token_id, NOW.isoformat()
    )
    revoked = await validate.authorize(f"Bearer {issued.access_token}", store, now=NOW)

    assert missing.description == card_tokens.MISSING.message
    assert unknown.description == card_tokens.UNRECOGNISED.message
    assert revoked.description == card_tokens.REVOKED.message
    assert {one.status for one in (missing, unknown, revoked)} == {401}


@pytest.mark.asyncio
async def test_a_request_that_presented_nothing_gets_a_challenge_with_no_error_code():
    """RFC 6750, and the reason is behavioural rather than pedantic: a client
    told `invalid_token` before it has ever authenticated will try to refresh a
    token it does not have."""
    store, _ = a_store()

    missing = await validate.authorize(None, store, now=NOW)
    unknown = await validate.authorize("Bearer nonsense", store, now=NOW)

    assert missing.error is None
    assert "error=" not in missing.challenge()
    assert unknown.error == validate.INVALID_TOKEN
    assert 'error="invalid_token"' in unknown.challenge()
    assert "resource_metadata=" in missing.challenge()


@pytest.mark.asyncio
async def test_an_insufficient_scope_challenge_names_the_scope_to_ask_for():
    store, _ = a_store()
    identity = await an_identity(store, scope="rooms:read")

    denied = validate.check(identity, need="rooms:write", now=NOW)

    assert 'error="insufficient_scope"' in denied.challenge()
    assert 'scope="rooms:write"' in denied.challenge()


@pytest.mark.asyncio
async def test_authorize_takes_its_resolver_by_injection():
    """Matching how star/mcp/router.py already receives one, so a test can
    drive every outcome without a store."""

    async def resolver(header, store, now=None):
        return card_tokens.UNRECOGNISED

    outcome = await validate.authorize(None, None, resolve=resolver, now=NOW)

    assert isinstance(outcome, validate.Denied)
    assert outcome.description == card_tokens.UNRECOGNISED.message


# === the card, and what it no longer lists ==================================


@pytest.mark.asyncio
async def test_the_card_lists_card_tokens_and_not_the_hourly_oauth_ones():
    """A list that grows by 24 rows a day per connected client is a list nobody
    reads, and a card nobody reads is a revoke button nobody finds. The gap
    this leaves is named in star/tokens.py: nothing yet lists or revokes an
    OAuth grant from a screen."""
    store, _ = a_store()
    await card_tokens.issue(UID, "desktop agent", store, now=NOW)
    await a_pair(store)

    listed = await card_tokens.list_for(UID, store)

    assert [token.label for token in listed] == ["desktop agent"]
