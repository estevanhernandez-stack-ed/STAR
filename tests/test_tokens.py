"""The token layer: what is minted, what is stored, and what a refusal says.

Everything here runs with no network. Firebase is faked at `star/auth.py`'s
`_verify` seam, exactly as `tests/test_auth.py` already fakes it, and Firestore
is the same hand-written fake `tests/test_store.py` drives — imported rather
than copied, so a path or query assertion here is against the shape that file
already pins against real Firestore behaviour.

Two properties get more attention than the rest, because both are one careless
edit away from being quietly untrue:

  · The generic refusal is genuinely generic. Three different failures produce
    one identical string, and the tests below compare the strings rather than
    reading them.
  · The federated-identity guard admits a linked account under BOTH claim
    shapes Firebase might produce after a link, because which one it actually
    produces has not been measured yet. See star/auth.py's linked_provider.
"""

import asyncio
import contextlib
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from star import server, tokens
from star.auth import linked_provider, verify_claims, verify_token
from star.store import TokenStore
from tests.test_store import _FakeClient

AUTH = {"Authorization": "Bearer good.token.here"}
UID = "uid-one"
OTHER = "uid-two"
NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)  # noqa: UP017


def a_store():
    client = _FakeClient()
    return TokenStore(client=client), client


async def issued(store, uid=UID, label="desktop agent", now=NOW):
    """Mint one token straight through the module, outside any request."""
    return await tokens.issue(uid, label, store, now=now)


def issue(store, uid=UID, label="desktop agent", now=NOW):
    """`issued`, for the tests that are not already inside a loop."""
    return asyncio.run(issued(store, uid=uid, label=label, now=now))


def stored(client, token_id):
    return client.data[f"mcp_tokens/{token_id}"]


class _ThreadRecordingStore:
    """Wraps a real TokenStore and remembers which thread each call ran on."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = []
        self.threads = []

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def recorded(*args, **kwargs):
            self.calls.append(name)
            self.threads.append(threading.get_ident())
            return attribute(*args, **kwargs)

        return recorded


# -- the claim shapes -------------------------------------------------------
#
# The one unmeasured thing in this item. An anonymous Firebase session that
# links a Google credential through `accounts:signInWithIdp` produces one of
# the two shapes below, and nobody has read a real one yet. The guard is built
# to be correct under either, so these are named for the possibilities they
# stand for rather than for what they contain.


def anonymous_claims(uid=UID):
    """A session that has never linked anything. The account the guard exists
    to refuse: its only proof of ownership is a `localStorage` entry."""
    return {
        "uid": uid,
        "firebase": {"sign_in_provider": "anonymous", "identities": {}},
    }


def shape_a_claims(uid=UID):
    """Possibility A: linking flips `sign_in_provider` to the provider.

    The shape `spec.md > The card` assumes. If Firebase behaves this way, a
    guard reading either field is correct and nothing is at stake in the
    choice.
    """
    return {
        "uid": uid,
        "email": "writer@example.com",
        "firebase": {
            "sign_in_provider": "google.com",
            "identities": {
                "google.com": ["108000000000000000000"],
                "email": ["writer@example.com"],
            },
        },
    }


def shape_b_claims(uid=UID):
    """Possibility B: `sign_in_provider` keeps describing how THIS session
    began and stays "anonymous"; only `identities` records the link.

    The expensive shape. A guard reading `sign_in_provider` alone refuses
    exactly the accounts it exists to admit, and does so silently until a
    reader clicks Issue and is told their linked account is not linked.
    """
    return {
        "uid": uid,
        "email": "writer@example.com",
        "firebase": {
            "sign_in_provider": "anonymous",
            "identities": {
                "google.com": ["108000000000000000000"],
                "email": ["writer@example.com"],
            },
        },
    }


@contextlib.contextmanager
def carded(store, claims=None):
    """Patch the three things the card's routes touch, and nothing else.

    Both verification seams are patched because the routes deliberately use
    two: `POST` needs the claim set to answer the linked question, and `GET` /
    `DELETE` need only a uid and go through the same `_require_uid` every other
    route in the project uses.
    """
    claims = anonymous_claims() if claims is None else claims
    with (
        mock.patch("star.server.verify_claims", return_value=claims),
        mock.patch("star.server.verify_token", return_value=claims.get("uid")),
        mock.patch("star.server._token_store", store),
    ):
        yield


# --- star/auth.py: verify_claims keeps verify_token's contract -------------


def test_verify_claims_returns_the_whole_verified_claim_set():
    claims = {"uid": "abc123", "firebase": {"sign_in_provider": "google.com"}}
    with mock.patch("star.auth._verify", return_value=claims):
        assert verify_claims("Bearer good.token.here") == claims


def test_verify_token_is_exactly_verify_claims_uid():
    """The refactor's whole contract, asserted rather than assumed.

    `tests/test_auth.py` pins verify_token's behaviour and passes unchanged;
    this pins the relationship between the two, so a later edit that gives
    verify_claims its own rules about what counts as a caller shows up here
    rather than in whichever route reads it next.
    """
    for returned in ({"uid": "abc123"}, {}, {"uid": ""}, None, "claims", 42):
        with mock.patch("star.auth._verify", return_value=returned):
            claims = verify_claims("Bearer good.token.here")
            assert verify_token("Bearer good.token.here") == (
                claims["uid"] if claims else None
            )

    for header in (None, "", "Basic nope", "Bearer "):
        with mock.patch("star.auth._verify", return_value={"uid": "abc123"}):
            assert verify_claims(header) is None
            assert verify_token(header) is None


def test_a_verification_failure_still_logs_one_line_and_returns_none(caplog):
    """The log line `tests/test_auth.py` exists for now lives one function
    further down. It has to still be exactly one line, and still say nothing
    the caller chose."""
    with (
        caplog.at_level("WARNING", logger="star.auth"),
        mock.patch("star.auth._verify", side_effect=ValueError("bad signature")),
    ):
        assert verify_claims("Bearer bad.token.here") is None

    assert len(caplog.records) == 1
    assert "ValueError" in caplog.records[0].getMessage()


# --- the guard: does this account have a federated identity? ---------------


def test_shape_a_a_link_that_flips_sign_in_provider_reads_as_linked():
    assert linked_provider(shape_a_claims()) == "google.com"


def test_shape_b_a_link_visible_only_in_identities_reads_as_linked():
    """The measurement this item was built around.

    If Firebase leaves `sign_in_provider` at "anonymous" after a link — because
    that field describes how the SESSION signed in, not what the ACCOUNT has
    attached — then the check `spec.md` names refuses every linked account, and
    silently. This is the test that fails if the guard is ever narrowed back to
    that field.
    """
    claims = shape_b_claims()
    assert claims["firebase"]["sign_in_provider"] == "anonymous"
    assert linked_provider(claims) == "google.com"


def test_a_session_that_never_linked_has_no_federated_identity():
    assert linked_provider(anonymous_claims()) is None


def test_sign_in_provider_alone_still_admits_when_identities_is_absent():
    """The corroborating signal, carrying the answer on its own.

    A claim set with no identities block at all is not a shape Firebase is
    expected to emit, but a provider that is neither empty nor "anonymous" is
    still an account somebody can sign back in to, which is the whole question.
    """
    assert linked_provider({"uid": UID, "firebase": {"sign_in_provider": "google.com"}})


def test_a_contact_detail_is_not_a_federated_identity():
    """Firebase keys federated providers by domain and the two non-federated
    ones as plain "email" and "phone". The dot is the whole rule, and it is
    `web/auth.js`'s rule verbatim — a browser drawing "attached" over a server
    refusing to issue is the failure both halves exist to avoid."""
    claims = {
        "uid": UID,
        "firebase": {
            "sign_in_provider": "anonymous",
            "identities": {"email": ["writer@example.com"], "phone": ["+15550100"]},
        },
    }
    assert linked_provider(claims) is None


def test_a_claim_set_with_no_firebase_block_is_not_linked():
    for claims in (None, {}, {"uid": UID}, {"uid": UID, "firebase": "google.com"}):
        assert linked_provider(claims) is None


# --- format and storage ----------------------------------------------------


def test_a_minted_token_carries_an_identifier_and_a_credential():
    """Two parts, with different entropy on purpose: the id appears in paths,
    logs, and on the card, and the secret appears nowhere."""
    token_id, secret, plaintext = tokens.mint()

    assert re.fullmatch(r"star_[0-9a-f]{12}\.[0-9a-f]{32}", plaintext)
    assert plaintext == f"star_{token_id}.{secret}"
    assert (len(token_id), len(secret)) == (12, 32)


def test_every_mint_is_distinct():
    assert len({tokens.mint()[2] for _ in range(50)}) == 50


def test_the_secret_is_stored_as_its_sha256_and_the_plaintext_is_not():
    store, client = a_store()

    plaintext, token = issue(store)
    _, secret = tokens.parse(plaintext)

    document = stored(client, token.token_id)
    assert document["secret_sha256"] == hashlib.sha256(secret.encode()).hexdigest()
    assert len(document["secret_sha256"]) == 64
    # Not "the field is absent" — the whole document, serialised, so a secret
    # smuggled into a label or a note would fail this too.
    written = json.dumps(document)
    assert secret not in written
    assert plaintext not in written


def test_a_stored_token_carries_the_fields_the_card_and_auth_need_and_no_others():
    store, client = a_store()

    _, token = issue(store)

    assert set(stored(client, token.token_id)) == {
        "token_id",
        "uid",
        "secret_sha256",
        "label",
        "created_at",
        "last_used_at",
        "revoked_at",
    }


def test_issue_hands_back_metadata_with_no_room_for_the_secret():
    store, _ = a_store()

    plaintext, token = issue(store)

    assert token.label == "desktop agent"
    assert token.created_at == NOW.isoformat()
    assert token.last_used_at is None
    assert token.revoked_at is None
    assert plaintext not in json.dumps(token.model_dump())


def test_a_write_that_fails_never_hands_back_a_plaintext():
    """Not best-effort, unlike every other Firestore call in the project. A
    caller holding a plaintext for a token that never landed holds a credential
    that will be refused forever, with a message naming nothing they can act
    on."""
    store, _ = a_store()

    with (
        mock.patch.object(store, "save", side_effect=RuntimeError("firestore down")),
        pytest.raises(RuntimeError),
    ):
        issue(store)


def test_to_metadata_drops_the_hash_rather_than_relying_on_the_model():
    """Field by field, not `McpToken(**document)`. Pydantic would ignore the
    extra key today; this ignores it on purpose, which is what stops a field
    added to the document later from arriving on the wire."""
    metadata = tokens.to_metadata(
        {
            "token_id": "abc",
            "uid": UID,
            "secret_sha256": "deadbeef",
            "label": "l",
            "created_at": "c",
            "some_field_added_later": "surprise",
        }
    )

    written = json.dumps(metadata.model_dump())
    assert "deadbeef" not in written
    assert "surprise" not in written
    assert UID not in written


# --- parsing ---------------------------------------------------------------


def test_parse_splits_a_well_formed_token():
    assert tokens.parse(f"star_{'a' * 12}.{'b' * 32}") == ("a" * 12, "b" * 32)


def test_parse_refuses_every_wrong_shape():
    wrong = [
        None,
        "",
        "star_",
        "star_abc",  # no separator
        f"{'a' * 12}.{'b' * 32}",  # no prefix
        f"STAR_{'a' * 12}.{'b' * 32}",  # the prefix is not case-insensitive
        f"star_{'a' * 11}.{'b' * 32}",  # id one short
        f"star_{'a' * 13}.{'b' * 32}",  # id one long
        f"star_{'a' * 12}.{'b' * 31}",  # secret one short
        f"star_{'a' * 12}.{'b' * 33}",  # secret one long
        f"star_{'z' * 12}.{'b' * 32}",  # id is not hex
        f"star_{'A' * 12}.{'b' * 32}",  # uppercase is not what mint emits
        f"star_{'a' * 12}.{'b' * 16}.{'c' * 15}",  # a second dot
    ]
    for token in wrong:
        assert tokens.parse(token) is None, token


@pytest.mark.asyncio
async def test_a_token_of_the_wrong_shape_never_costs_a_read():
    """A public endpoint that turns any string into a database read is a free
    way to make the department do work."""
    store, _ = a_store()

    with mock.patch.object(store, "get", side_effect=AssertionError("read")) as read:
        refusal = await tokens.resolve("Bearer nonsense", store)

    assert refusal is tokens.UNRECOGNISED
    read.assert_not_called()


# --- resolve: the refusals -------------------------------------------------


async def _refusals_with_a_credential_presented(store, plaintext):
    """Every refusal reachable when the caller presents SOMETHING."""
    token_id, _ = tokens.parse(plaintext)
    return {
        "wrong shape": await tokens.resolve("Bearer not-a-star-token", store),
        "unknown id": await tokens.resolve(f"Bearer star_{'0' * 12}.{'0' * 32}", store),
        "hash mismatch": await tokens.resolve(
            f"Bearer star_{token_id}.{'f' * 32}", store
        ),
    }


@pytest.mark.asyncio
async def test_the_generic_refusal_is_byte_identical_across_all_three_causes():
    """Wrong shape, unknown token id, and a secret that does not match: one
    answer, compared as strings rather than read as similar.

    `star/auth.py:119-145`'s posture, for the same reason. A well-formed token
    that matches nothing and a malformed one have to be indistinguishable, or
    the difference between them is a free scan for which token ids are real.
    """
    store, _ = a_store()
    plaintext, _ = await issued(store)

    refusals = await _refusals_with_a_credential_presented(store, plaintext)

    assert {refusal.message for refusal in refusals.values()} == {
        tokens.UNRECOGNISED.message
    }, refusals
    # The reason is collapsed too, not just the prose. A transport branching on
    # `reason` must not be able to reintroduce the distinction the string
    # refuses to draw.
    assert {refusal.reason for refusal in refusals.values()} == {
        tokens.UNRECOGNISED.reason
    }, refusals


@pytest.mark.asyncio
async def test_a_revoked_token_is_told_it_was_revoked():
    store, client = a_store()
    plaintext, token = await issued(store)
    await tokens.revoke(UID, token.token_id, store, now=NOW)

    refusal = await tokens.resolve(f"Bearer {plaintext}", store)

    assert refusal is tokens.REVOKED
    assert "revoked" in refusal.message
    assert stored(client, token.token_id)["revoked_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_the_revoked_refusal_is_the_only_one_that_differs():
    """One deliberate exception, and no accidental second one."""
    store, _ = a_store()
    plaintext, token = await issued(store)
    await tokens.revoke(UID, token.token_id, store, now=NOW)

    generic = await _refusals_with_a_credential_presented(store, plaintext)
    revoked = await tokens.resolve(f"Bearer {plaintext}", store)

    messages = {refusal.message for refusal in generic.values()} | {revoked.message}
    assert len(messages) == 2
    assert revoked.message != tokens.UNRECOGNISED.message


@pytest.mark.asyncio
async def test_a_revoked_token_with_the_wrong_secret_gets_the_generic_refusal():
    """The ordering that makes the distinct message safe.

    Step 5 sits after step 4 and never before it, so reaching the revoked
    answer required presenting the correct secret and tells the caller nothing
    they did not already hold. A revocation check that ran on the token id
    alone would tell anyone who guessed an id that the id was real.
    """
    store, _ = a_store()
    _, token = await issued(store)
    await tokens.revoke(UID, token.token_id, store, now=NOW)

    refusal = await tokens.resolve(f"Bearer star_{token.token_id}.{'f' * 32}", store)

    assert refusal is tokens.UNRECOGNISED


@pytest.mark.asyncio
async def test_a_missing_credential_is_answered_as_a_missing_credential():
    """Not an exception to the generic answer, because it is not an answer
    about a token: the caller sent none and already knows it. It is also the
    only refusal that can name a next step precisely, which is what the PRD
    asks every error to do."""
    store, _ = a_store()

    for header in (None, "", "Basic nope", "Bearer", "Bearer "):
        assert await tokens.resolve(header, store) is tokens.MISSING, header

    assert tokens.MISSING.message != tokens.UNRECOGNISED.message
    assert "Authorization header" in tokens.MISSING.message


@pytest.mark.asyncio
async def test_the_missing_answer_is_unreachable_once_anything_is_presented():
    """The bound on the paragraph above: a caller who sends a credential can
    never learn from the answer that it was even parsed."""
    store, _ = a_store()
    plaintext, _ = await issued(store)

    refusals = await _refusals_with_a_credential_presented(store, plaintext)

    assert all(refusal is not tokens.MISSING for refusal in refusals.values())


@pytest.mark.asyncio
async def test_a_valid_token_resolves_to_the_account_that_issued_it():
    store, _ = a_store()
    plaintext, token = await issued(store)

    identity = await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert isinstance(identity, tokens.TokenIdentity)
    assert identity.uid == UID
    assert identity.token_id == token.token_id


@pytest.mark.asyncio
async def test_a_document_with_no_owner_answers_generically():
    """A matching hash on a document with no uid is a defect in the store, not
    a fact about the caller, and the caller's position is exactly the generic
    one: this token buys nothing."""
    store, client = a_store()
    plaintext, token = await issued(store)
    del client.data[f"mcp_tokens/{token.token_id}"]["uid"]

    assert await tokens.resolve(f"Bearer {plaintext}", store) is tokens.UNRECOGNISED


# --- resolve: the comparison itself ----------------------------------------


@pytest.mark.asyncio
async def test_the_hash_comparison_is_delegated_to_compare_digest():
    """Not `==`, because a hash comparison's timing should not describe the
    hash. Proved by making compare_digest disagree with equality in both
    directions: if the branch were `==`, neither half below could move it.
    """
    store, client = a_store()
    plaintext, token = await issued(store)
    stored_hash = stored(client, token.token_id)["secret_sha256"]

    with mock.patch.object(tokens.hmac, "compare_digest", return_value=False) as never:
        refusal = await tokens.resolve(f"Bearer {plaintext}", store)
    assert refusal is tokens.UNRECOGNISED
    never.assert_called_once_with(stored_hash, stored_hash)

    with mock.patch.object(tokens.hmac, "compare_digest", return_value=True):
        identity = await tokens.resolve(
            f"Bearer star_{token.token_id}.{'f' * 32}", store, now=NOW
        )
    assert isinstance(identity, tokens.TokenIdentity)


@pytest.mark.asyncio
async def test_the_secret_itself_never_reaches_the_comparison():
    """Only hashes are compared, so a store that leaked its documents would
    still not leak anything replayable."""
    store, _ = a_store()
    plaintext, _ = await issued(store)
    _, secret = tokens.parse(plaintext)

    with mock.patch.object(
        tokens.hmac, "compare_digest", wraps=tokens.hmac.compare_digest
    ) as spy:
        await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert spy.call_args_list
    for call in spy.call_args_list:
        assert secret not in call.args


# --- last_used_at: at most one write per token per 60 seconds --------------


@pytest.mark.asyncio
async def test_the_first_use_stamps_last_used_at():
    store, client = a_store()
    plaintext, token = await issued(store)

    await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert stored(client, token.token_id)["last_used_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_a_second_use_inside_the_window_does_not_write():
    """`get_room` is a polling endpoint by design, so a write per call is a
    Firestore write per agent poll — a cost that scales with how well-behaved
    the agent is."""
    store, _ = a_store()
    plaintext, _ = await issued(store)
    await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    with mock.patch.object(store, "touch") as touch:
        for seconds in (1, 15, 59):
            await tokens.resolve(
                f"Bearer {plaintext}", store, now=NOW + timedelta(seconds=seconds)
            )

    touch.assert_not_called()


@pytest.mark.asyncio
async def test_a_use_past_the_window_writes_again():
    store, client = a_store()
    plaintext, token = await issued(store)
    await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    later = NOW + timedelta(seconds=60)
    await tokens.resolve(f"Bearer {plaintext}", store, now=later)

    assert stored(client, token.token_id)["last_used_at"] == later.isoformat()


@pytest.mark.asyncio
async def test_the_throttle_reads_the_stored_stamp_rather_than_process_memory():
    """No table of last-write times in memory: the document is already in hand
    from step 3, so the throttle costs no extra read and survives a restart an
    in-memory table would not."""
    store, client = a_store()
    plaintext, token = await issued(store)
    # A stamp this process never wrote, from a request served before a restart.
    client.data[f"mcp_tokens/{token.token_id}"]["last_used_at"] = NOW.isoformat()

    with mock.patch.object(store, "touch") as touch:
        await tokens.resolve(
            f"Bearer {plaintext}", store, now=NOW + timedelta(seconds=30)
        )

    touch.assert_not_called()


@pytest.mark.asyncio
async def test_a_stamp_from_the_future_is_rewritten_rather_than_frozen():
    """Two clocks that disagreed would otherwise park the value ahead of real
    time and freeze the field there, on a surface that reports "last used" to a
    reader deciding whether to revoke."""
    store, client = a_store()
    plaintext, token = await issued(store)
    ahead = (NOW + timedelta(days=2)).isoformat()
    client.data[f"mcp_tokens/{token.token_id}"]["last_used_at"] = ahead

    await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert stored(client, token.token_id)["last_used_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_an_unreadable_stamp_self_heals():
    store, client = a_store()
    plaintext, token = await issued(store)

    for junk in ("", "yesterday", 17, None):
        client.data[f"mcp_tokens/{token.token_id}"]["last_used_at"] = junk

        await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

        assert stored(client, token.token_id)["last_used_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_a_failed_stamp_never_costs_the_caller_the_call(caplog):
    """A lost stamp costs a reader one stale date on the card. A raised one
    would cost an agent the call it was making."""
    store, _ = a_store()
    plaintext, _ = await issued(store)

    with (
        caplog.at_level("ERROR", logger="star.tokens"),
        mock.patch.object(store, "touch", side_effect=RuntimeError("firestore down")),
    ):
        identity = await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert isinstance(identity, tokens.TokenIdentity)
    assert caplog.records


@pytest.mark.asyncio
async def test_every_store_call_resolve_makes_happens_off_the_event_loop():
    """The Firestore client is blocking and this loop is shared with every open
    SSE stream on the instance."""
    inner, _ = a_store()
    store = _ThreadRecordingStore(inner)
    plaintext, _ = await issued(store)
    store.calls.clear()
    store.threads.clear()
    loop_thread = threading.get_ident()

    await tokens.resolve(f"Bearer {plaintext}", store, now=NOW)

    assert store.calls == ["get", "touch"]
    assert loop_thread not in store.threads


# --- the store: one account's tokens, and nobody else's --------------------


def test_the_card_lists_only_this_accounts_tokens():
    store, _ = a_store()
    issue(store, uid=UID, label="mine")
    issue(store, uid=OTHER, label="theirs")

    listed = asyncio.run(tokens.list_for(UID, store))

    assert [token.label for token in listed] == ["mine"]


def test_the_list_is_newest_first():
    store, _ = a_store()
    issue(store, label="older", now=NOW - timedelta(days=1))
    issue(store, label="newer", now=NOW)

    listed = asyncio.run(tokens.list_for(UID, store))

    assert [token.label for token in listed] == ["newer", "older"]


def test_the_list_carries_neither_the_hash_nor_the_owner():
    store, _ = a_store()
    issue(store)

    listed = asyncio.run(tokens.list_for(UID, store))

    written = json.dumps([token.model_dump() for token in listed])
    assert "secret_sha256" not in written
    assert UID not in written


def test_revoking_another_accounts_token_answers_as_a_token_that_never_existed():
    store, client = a_store()
    _, token = issue(store, uid=OTHER)

    theirs = asyncio.run(tokens.revoke(UID, token.token_id, store, now=NOW))
    absent = asyncio.run(tokens.revoke(UID, "never-existed", store, now=NOW))

    assert theirs is absent is False
    assert stored(client, token.token_id)["revoked_at"] is None


def test_a_second_revoke_keeps_the_first_timestamp():
    """The first revocation is the fact worth keeping, and a second DELETE from
    a card that still lists the token is a plausible click, not an error."""
    store, client = a_store()
    _, token = issue(store)

    assert asyncio.run(tokens.revoke(UID, token.token_id, store, now=NOW)) is True
    later = NOW + timedelta(hours=1)
    assert asyncio.run(tokens.revoke(UID, token.token_id, store, now=later)) is True

    assert stored(client, token.token_id)["revoked_at"] == NOW.isoformat()


def test_a_revoked_token_stays_on_the_card():
    """Soft, not deleted, and the reader's half of that is seeing it. The next
    call with it has to be told it was revoked, which a deleted document could
    not do."""
    store, _ = a_store()
    _, token = issue(store)
    asyncio.run(tokens.revoke(UID, token.token_id, store, now=NOW))

    listed = asyncio.run(tokens.list_for(UID, store))

    assert [token.revoked_at for token in listed] == [NOW.isoformat()]


# --- the endpoints ---------------------------------------------------------


def test_an_anonymous_account_cannot_mint_a_token():
    """The coupling that put identity ahead of the agent door: an anonymous
    account's only proof of ownership is a `localStorage` entry, so a
    long-lived token pointing at one is a credential to an account nobody can
    recover."""
    store, client = a_store()

    with carded(store, anonymous_claims()):
        response = TestClient(server.app).post("/api/tokens", json={}, headers=AUTH)

    assert response.status_code == 403
    assert client.data == {}


def test_the_refusal_names_the_reason_rather_than_reading_as_a_bug():
    store, _ = a_store()

    with carded(store, anonymous_claims()):
        response = TestClient(server.app).post("/api/tokens", json={}, headers=AUTH)

    detail = response.json()["detail"]
    assert "no account attached" in detail
    assert "Attach a Google account" in detail
    assert "sign back in" in detail


def test_a_linked_account_can_mint_under_claim_shape_a():
    store, _ = a_store()

    with carded(store, shape_a_claims()):
        response = TestClient(server.app).post(
            "/api/tokens", json={"label": "desktop agent"}, headers=AUTH
        )

    assert response.status_code == 200
    assert re.fullmatch(r"star_[0-9a-f]{12}\.[0-9a-f]{32}", response.json()["token"])


def test_a_linked_account_can_mint_under_claim_shape_b():
    """The same account, one field different, and it is the field the spec's
    guard would have read. If Firebase turns out to behave this way, a check on
    `sign_in_provider` alone refuses every linked reader in the product, and
    this is the test that would have caught it."""
    store, _ = a_store()

    with carded(store, shape_b_claims()):
        response = TestClient(server.app).post(
            "/api/tokens", json={"label": "desktop agent"}, headers=AUTH
        )

    assert response.status_code == 200
    assert re.fullmatch(r"star_[0-9a-f]{12}\.[0-9a-f]{32}", response.json()["token"])


def test_the_issue_response_is_the_list_shape_plus_the_one_field_that_ends():
    store, _ = a_store()

    with carded(store, shape_b_claims()):
        http = TestClient(server.app)
        issued_body = http.post(
            "/api/tokens", json={"label": "desktop agent"}, headers=AUTH
        ).json()
        listed = http.get("/api/tokens", headers=AUTH).json()["tokens"]

    assert listed == [{k: v for k, v in issued_body.items() if k != "token"}]


def test_the_plaintext_exists_on_the_wire_once_and_is_never_recoverable():
    store, client = a_store()

    with carded(store, shape_b_claims()):
        http = TestClient(server.app)
        body = http.post("/api/tokens", json={"label": "agent"}, headers=AUTH).json()
        listed = http.get("/api/tokens", headers=AUTH)

    _, secret = tokens.parse(body["token"])
    assert body["token"] not in listed.text
    assert secret not in listed.text
    # Nor the hash. It is not a credential, but it is one offline guess away
    # from telling its holder whether a guessed secret is the right one.
    assert stored(client, body["token_id"])["secret_sha256"] not in listed.text
    assert listed.json() == {
        "tokens": [
            {
                "token_id": body["token_id"],
                "label": "agent",
                "created_at": body["created_at"],
                "last_used_at": None,
                "revoked_at": None,
            }
        ]
    }


def test_a_label_past_the_cap_is_refused_with_the_number():
    store, _ = a_store()

    with carded(store, shape_b_claims()):
        response = TestClient(server.app).post(
            "/api/tokens", json={"label": "x" * 200}, headers=AUTH
        )

    assert response.status_code == 400
    assert str(tokens.MAX_LABEL_CHARS) in response.json()["detail"]
    assert "200" in response.json()["detail"]


def test_an_empty_label_is_a_blank_rather_than_a_name_invented_for_the_reader():
    store, _ = a_store()

    with carded(store, shape_b_claims()):
        response = TestClient(server.app).post("/api/tokens", json={}, headers=AUTH)

    assert response.status_code == 200
    assert response.json()["label"] == ""


def test_the_card_shows_only_the_readers_own_tokens():
    store, _ = a_store()
    issue(store, uid=OTHER, label="theirs")

    with carded(store, shape_b_claims()):
        http = TestClient(server.app)
        http.post("/api/tokens", json={"label": "mine"}, headers=AUTH)
        listed = http.get("/api/tokens", headers=AUTH).json()["tokens"]

    assert [token["label"] for token in listed] == ["mine"]


def test_delete_revokes_and_the_next_call_with_that_token_is_told_so():
    store, _ = a_store()

    with carded(store, shape_b_claims()):
        http = TestClient(server.app)
        body = http.post("/api/tokens", json={"label": "agent"}, headers=AUTH).json()
        deleted = http.delete(f"/api/tokens/{body['token_id']}", headers=AUTH)

    refusal = asyncio.run(tokens.resolve(f"Bearer {body['token']}", store))

    assert deleted.status_code == 204
    assert refusal is tokens.REVOKED


def test_delete_on_another_accounts_token_answers_as_an_unknown_token():
    """No oracle, matching `get_room`. Not merely both 404 — the same answer
    down to the string, or the refusal itself confirms the token id is real."""
    store, _ = a_store()
    _, theirs = issue(store, uid=OTHER)

    with carded(store, shape_b_claims()):
        http = TestClient(server.app)
        mine = http.delete(f"/api/tokens/{theirs.token_id}", headers=AUTH)
        absent = http.delete("/api/tokens/never-existed", headers=AUTH)

    assert mine.status_code == absent.status_code == 404
    assert mine.json() == absent.json()


@pytest.mark.asyncio
async def test_every_firestore_call_the_card_makes_happens_off_the_event_loop():
    """Called through the handlers rather than a TestClient, because a
    TestClient runs the app on a thread of its own and every call would look
    off-loop whether it was or not."""
    inner, _ = a_store()
    store = _ThreadRecordingStore(inner)
    loop_thread = threading.get_ident()

    with carded(store, shape_b_claims()):
        body = await server.create_token(
            # The claim set rather than a header: `_claims` is a dependency
            # now (see server._uid for the ordering it buys), and calling a
            # handler directly runs none.
            server.TokenRequest(label="agent"),
            claims=shape_b_claims(),
        )
        await server.list_tokens(AUTH["Authorization"])
        await server.revoke_token(body["token_id"], AUTH["Authorization"])

    assert store.calls == ["save", "list_for_uid", "revoke"]
    assert loop_thread not in store.threads
