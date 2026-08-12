"""The agent door: the wire contract, the bearer check, and the ceilings.

Everything here runs with no network and no spend. There is no `mcp` package
to lean on — spec.md's Decision 1 argues that at length — so this file is what
stands in for a conformance suite, and it asserts against the transport spec
rather than against the implementation's own idea of itself.

Two things get more attention than the rest, because both are one careless
edit away from being quietly untrue:

  · Auth runs before the body is read at all. The tests below post garbage
    with no credential and assert the answer is 401 rather than a parse error,
    which is the only way to tell "checked first" from "checked eventually".
  · The two doors share one admission path. Nothing here asserts that a
    comment says so; the assertions are `is` comparisons against the function
    objects star/server.py hands the router, and a daily cap that counts to
    two after one build through each door.

The four tools arrived in the item after the transport, and the section at the
foot of this file is theirs. It asserts against the strings rather than around
them, because on a surface with no screen the strings ARE the product: a
refusal that does not say what to do next is the defect, not a cosmetic
shortfall next to one.
"""

import contextlib
import json
import re
import tomllib
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from star import config, server, tokens
from star.guards import DailyCap, RateLimiter
from star.mcp import protocol, tools
from star.models import Citation, ClaimResult, ScriptCheckResult, Verdict
from star.oauth import metadata
from star.store import TokenStore
from tests.test_server import _FakeRequest
from tests.test_store import _FakeClient

# Every icon this server names must be served BY this server. A declared icon
# pointing anywhere else is the guess it exists to replace.
SERVICE_ORIGIN = "https://star.626labs.dev"

UID = "uid-one"
OTHER = "uid-two"
BROWSER_AUTH = {"Authorization": "Bearer good.token.here"}
TREATMENT = "A period drama set in 1962 Memphis, with a session guitarist."

# A well-formed token that no store has ever heard of: the right prefix, the
# right two lengths, all hex. It exists to prove the refusal for this is
# byte-identical to the refusal for a token that is not even shaped like one.
UNKNOWN_TOKEN = "star_" + "a" * 12 + "." + "b" * 32
MALFORMED_TOKEN = "not-even-close"


def a_token_store():
    client = _FakeClient()
    return TokenStore(client=client), client


async def issue(store, uid=UID, label="desktop agent") -> str:
    """Mint one token straight through the module, and hand back the plaintext.

    Through `tokens.issue` rather than by writing a document by hand, so the
    hash the door compares against is the hash the issuing path actually
    writes. A fixture that hand-rolled the document would pass a test the
    product would fail.
    """
    plaintext, _ = await tokens.issue(uid, label, store)
    return plaintext


@contextlib.contextmanager
def door(store=None):
    """Point the agent door at a fake Firestore and nothing else."""
    store = a_token_store()[0] if store is None else store
    with mock.patch("star.server._token_store", store):
        yield store


def rpc(client, payload, token=None, **headers):
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/mcp", json=payload, headers=headers)


def call(method, identifier=1, **params):
    message = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params:
        message["params"] = params
    return message


# -- initialize --------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_answers_with_the_advertised_revision_and_a_tools_capability():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(TestClient(server.app), call("initialize"), token=token).json()

    result = body["result"]
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert result["protocolVersion"] == protocol.ADVERTISED_VERSION == "2025-11-25"
    # Tools and nothing else. A capability declared here that the server does
    # not serve is a client calling `resources/list` on the strength of the
    # handshake and getting -32601 for it.
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "star"
    assert result["instructions"]


@pytest.mark.asyncio
async def test_initialize_honours_a_supported_revision_the_client_asked_for():
    """The transport spec's MUST, and it does not fight spec.md's "advertises
    2025-11-25": the advertised revision is what this server names when IT is
    choosing. A client that asked for one this server speaks is answered with
    the one it asked for, because a client answered with a different revision
    is entitled to disconnect."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        client = TestClient(server.app)
        for revision in protocol.SUPPORTED_VERSIONS:
            body = rpc(
                client, call("initialize", protocolVersion=revision), token=token
            ).json()
            assert body["result"]["protocolVersion"] == revision


@pytest.mark.asyncio
async def test_initialize_falls_back_to_the_advertised_revision_for_one_it_cannot_speak():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(
            TestClient(server.app),
            call("initialize", protocolVersion="1999-01-01"),
            token=token,
        ).json()

    assert body["result"]["protocolVersion"] == protocol.ADVERTISED_VERSION


@pytest.mark.asyncio
async def test_no_session_id_is_issued_at_the_handshake_or_anywhere_after():
    """Sessions are optional in the transport spec and this server has none.
    Issuing a header it does not honour would make a client hold state that
    means nothing and, worse, expect a DELETE to do something."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        client = TestClient(server.app)
        handshake = rpc(client, call("initialize"), token=token)
        after = rpc(client, call("ping", identifier=2), token=token)

    for response in (handshake, after):
        assert not [h for h in response.headers if h.lower() == "mcp-session-id"]


# -- the other methods -------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_list_answers_with_the_whole_surface_and_asks_for_no_second_page():
    """The envelope, the key, and the shape. What is IN the list is asserted
    at the foot of this file, where the four tools are."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(
            TestClient(server.app), call("tools/list"), token=token
        ).json()

    assert body["result"] == {"tools": list(tools.TOOLS)}
    assert "nextCursor" not in body["result"]


@pytest.mark.asyncio
async def test_ping_answers_with_an_empty_result():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(TestClient(server.app), call("ping"), token=token).json()

    assert body["result"] == {}


@pytest.mark.asyncio
async def test_an_unknown_method_is_a_method_not_found_error():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app), call("resources/list"), token=token
        )

    body = response.json()
    # 200 with an error object, not an HTTP error. This one is addressed to a
    # specific request id and belongs in the JSON-RPC envelope, which is where
    # a client written against the protocol will look for it.
    assert response.status_code == 200
    assert body["id"] == 1
    assert body["error"]["code"] == -32601 == protocol.METHOD_NOT_FOUND
    assert "resources/list" in body["error"]["message"]


@pytest.mark.asyncio
async def test_an_unknown_tool_is_a_tool_result_rather_than_a_protocol_error():
    """The split the whole error posture turns on: a model that named a tool
    this department does not have can read this and try another, where a
    JSON-RPC error says the client is broken and gives the model nothing."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(
            TestClient(server.app),
            call("tools/call", name="build_a_bear", arguments={}),
            token=token,
        ).json()

    assert "error" not in body
    assert body["result"]["isError"] is True
    assert "build_a_bear" in body["result"]["content"][0]["text"]
    assert "tools/list" in body["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_a_tools_call_with_no_name_is_an_invalid_params_error():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(
            TestClient(server.app), call("tools/call", arguments={}), token=token
        ).json()

    assert body["error"]["code"] == protocol.INVALID_PARAMS


@pytest.mark.asyncio
async def test_a_tool_reaches_the_account_the_token_was_issued_to():
    """One ledger, two doors, at the only seam where it can be observed before
    the tools exist. The uid that arrives at a tool is the uid the browser
    issued the token against, and the callables the tool is handed are the
    server's own function objects."""
    store, _ = a_token_store()
    token = await issue(store, uid=OTHER)
    seen = {}

    async def _record(arguments, calls, identity):
        seen["uid"] = identity.uid
        seen["calls"] = calls
        return tools.text_result("ok")

    with door(store), mock.patch.dict(tools._RUNNERS, {"probe": _record}):
        body = rpc(
            TestClient(server.app),
            call("tools/call", name="probe", arguments={"a": 1}),
            token=token,
        ).json()

    assert body["result"]["isError"] is False
    assert seen["uid"] == OTHER
    assert seen["calls"].start_build is server._mcp_start_build
    assert seen["calls"].read_room is server._read_room
    assert seen["calls"].list_rooms_for is server._list_rooms_for
    assert seen["calls"].run_check is server._run_check


@pytest.mark.asyncio
async def test_a_tool_that_blows_up_says_nothing_about_our_internals(caplog):
    store, _ = a_token_store()
    token = await issue(store)

    async def _explode(arguments, calls, identity):
        raise RuntimeError(
            "psycopg2.OperationalError: password authentication failed for user 'star'"
        )

    with door(store), mock.patch.dict(tools._RUNNERS, {"probe": _explode}):
        body = rpc(
            TestClient(server.app),
            call("tools/call", name="probe", arguments={}),
            token=token,
        ).json()

    message = body["error"]["message"]
    assert body["error"]["code"] == protocol.INTERNAL_ERROR
    assert "psycopg2" not in message
    assert "password" not in message
    assert "RuntimeError" not in message
    assert "psycopg2" in caplog.text


# -- notifications and responses: 202, no body -------------------------------


@pytest.mark.asyncio
async def test_notifications_initialized_is_accepted_with_no_body():
    """The one notification every client sends, and the transport spec's
    answer to it. A 200 carrying a result would be answering a message that
    has no id to answer to."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            token=token,
        )

    assert response.status_code == 202
    assert response.content == b""


@pytest.mark.asyncio
async def test_a_notification_carrying_an_explicit_null_id_is_the_same_message():
    """MCP forbids a null id on a request, so `"id": null` is not a request
    with a strange id — it is a notification written differently."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app),
            {"jsonrpc": "2.0", "id": None, "method": "notifications/initialized"},
            token=token,
        )

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_a_posted_response_is_accepted_with_no_body():
    """This server sends no requests, so nothing can correlate a response —
    but it is a well-formed message and 202 is the spec's answer to it."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app), {"jsonrpc": "2.0", "id": 7, "result": {}}, token=token
        )

    assert response.status_code == 202
    assert response.content == b""


@pytest.mark.asyncio
async def test_a_batch_of_notifications_is_accepted_and_a_batch_with_a_request_is_not():
    """Batching was removed in the revision this server advertises. A batch
    that owes no answer is accepted anyway, because every member would get 202
    on its own and refusing it breaks an older client over a distinction it
    cannot observe."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        client = TestClient(server.app)
        quiet = rpc(
            client,
            [
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "notifications/cancelled"},
            ],
            token=token,
        )
        loud = rpc(client, [call("tools/list")], token=token)

    assert quiet.status_code == 202
    assert loud.status_code == 400
    assert loud.json()["error"]["code"] == protocol.INVALID_REQUEST
    assert "batching" in loud.json()["error"]["message"].lower()


# -- GET and DELETE ----------------------------------------------------------


def test_get_mcp_is_405_because_this_server_initiates_no_stream():
    """The spec's own answer for a server offering no server-initiated SSE.
    It has to be registered explicitly: the StaticFiles mount at `/` matches
    every path, so an unregistered method on /mcp would come back 404 from the
    static handler instead."""
    response = TestClient(server.app).get("/mcp")

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert response.json()["error"]["message"]


def test_delete_mcp_is_405_because_there_is_no_session_to_terminate():
    response = TestClient(server.app).delete("/mcp")

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert response.json()["error"]["message"]


# -- MCP-Protocol-Version ----------------------------------------------------


@pytest.mark.asyncio
async def test_an_absent_protocol_version_is_read_as_the_revision_that_predates_it():
    """The backwards-compatibility rule, and the case that matters most in
    practice: the header is not sent on `initialize`, because the version has
    not been agreed yet. Refusing its absence would refuse every client."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(TestClient(server.app), call("initialize"), token=token)

    assert response.status_code == 200
    assert protocol.negotiate_header(None) == "2025-03-26"


@pytest.mark.asyncio
async def test_every_supported_protocol_version_header_is_accepted():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        client = TestClient(server.app)
        for revision in protocol.SUPPORTED_VERSIONS:
            response = rpc(
                client,
                call("ping"),
                token=token,
                **{"MCP-Protocol-Version": revision},
            )
            assert response.status_code == 200, revision


@pytest.mark.asyncio
async def test_an_unsupported_protocol_version_is_refused_with_400():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app),
            call("ping"),
            token=token,
            **{"MCP-Protocol-Version": "2024-01-01"},
        )

    body = response.json()
    assert response.status_code == 400
    assert body["error"]["code"] == protocol.UNSUPPORTED_PROTOCOL_VERSION
    # Names what was sent and what is spoken. A bare 400 fails prd.md's bar.
    assert "2024-01-01" in body["error"]["message"]
    for revision in protocol.SUPPORTED_VERSIONS:
        assert revision in body["error"]["message"]


# -- Origin ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_origin_this_server_does_not_answer_to_is_refused_with_403():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app),
            call("initialize"),
            token=token,
            Origin="https://evil.example",
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == protocol.ORIGIN_REFUSED


@pytest.mark.asyncio
async def test_an_absent_origin_passes_because_non_browser_clients_send_none():
    """The load-bearing half. Origin validation exists to stop a page in a
    browser driving this endpoint through DNS rebinding; a desktop agent, a
    script, and curl all send no Origin at all, and refusing them would refuse
    every client this door was built for."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(TestClient(server.app), call("initialize"), token=token)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_the_services_own_origins_pass_and_case_and_a_trailing_slash_do_not_decide():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        client = TestClient(server.app)
        for origin in config.mcp_allowed_origins():
            assert rpc(
                client, call("ping"), token=token, Origin=origin
            ).status_code == 200
            assert rpc(
                client, call("ping"), token=token, Origin=origin.upper() + "/"
            ).status_code == 200


@pytest.mark.asyncio
async def test_an_opaque_origin_is_refused():
    """A sandboxed iframe or a data: URL sends the literal string "null". It
    matches nothing in the allow list, which is the answer it should get."""
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(
            TestClient(server.app), call("ping"), token=token, Origin="null"
        )

    assert response.status_code == 403


def test_an_empty_allowed_origins_variable_falls_back_rather_than_refusing_everything():
    with mock.patch.dict("os.environ", {"STAR_MCP_ALLOWED_ORIGINS": "   "}):
        assert config.mcp_allowed_origins()
    with mock.patch.dict(
        "os.environ", {"STAR_MCP_ALLOWED_ORIGINS": "https://a.example, https://b.example"}
    ):
        assert config.mcp_allowed_origins() == (
            "https://a.example",
            "https://b.example",
        )


# -- the five auth cases -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_call_with_no_authorization_header_is_refused_with_a_challenge():
    with door():
        response = rpc(TestClient(server.app), call("initialize"))

    body = response.json()
    assert response.status_code == 401
    assert body["error"]["code"] == protocol.AUTHORIZATION_REQUIRED
    assert body["error"]["message"] == tokens.MISSING.message

    # This used to assert the challenge was the bare string "Bearer", and that
    # was right while it was true: with no authorization server, a
    # `resource_metadata` pointer would have named a 404 and sent a client
    # somewhere worse than nowhere.
    #
    # Now the pointer is the whole value of the header, because it is what
    # turns a refusal into the first step of a flow rather than a dead end. So
    # the assertion is not that some parameter is present, it is that the URL
    # the challenge names IS SERVED — which is the property the old comment
    # said could not be had, checked rather than asserted.
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer ")

    named = re.search(r'resource_metadata="([^"]+)"', challenge)
    assert named, f"no resource_metadata in {challenge!r}"

    served = TestClient(server.app).get(urlsplit(named.group(1)).path)
    assert served.status_code == 200
    assert served.json()["resource"]


@pytest.mark.asyncio
async def test_a_malformed_token_is_refused():
    with door():
        response = rpc(TestClient(server.app), call("initialize"), token=MALFORMED_TOKEN)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == tokens.UNRECOGNISED.message


@pytest.mark.asyncio
async def test_a_well_formed_token_that_matches_nothing_is_refused_identically():
    """The edge prd.md names. A token of the right shape matching no document
    and a token of the wrong shape are the same answer, down to the bytes —
    telling a stranger which one they sent is free reconnaissance into which
    token ids are real."""
    with door():
        client = TestClient(server.app)
        unknown = rpc(client, call("initialize"), token=UNKNOWN_TOKEN)
        malformed = rpc(client, call("initialize"), token=MALFORMED_TOKEN)

    assert unknown.status_code == malformed.status_code == 401
    assert unknown.content == malformed.content


@pytest.mark.asyncio
async def test_a_revoked_token_is_told_it_was_revoked():
    """The one deliberate exception to the generic refusal, and it is safe
    because reaching it required presenting the correct secret. An agent
    configured months ago and revoked yesterday would otherwise spend its
    operator's afternoon debugging a malformed header."""
    store, _ = a_token_store()
    plaintext, token = await tokens.issue(UID, "desktop agent", store)
    await tokens.revoke(UID, token.token_id, store)

    with door(store):
        response = rpc(TestClient(server.app), call("initialize"), token=plaintext)

    body = response.json()
    assert response.status_code == 401
    assert body["error"]["message"] == tokens.REVOKED.message
    assert body["error"]["message"] != tokens.UNRECOGNISED.message


@pytest.mark.asyncio
async def test_a_valid_token_reaches_the_method():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(TestClient(server.app), call("initialize"), token=token)

    assert response.status_code == 200
    assert "error" not in response.json()


@pytest.mark.asyncio
async def test_auth_runs_before_the_body_is_read_at_all():
    """The rule the whole file exists to hold. A body that is not JSON, and a
    body that is a well-formed `initialize`, both come back 401 with no token
    — so the credential is checked before parsing rather than eventually, and
    there is no unauthenticated handshake."""
    with door():
        client = TestClient(server.app)
        garbage = client.post(
            "/mcp", content=b"{not json at all", headers={"Content-Type": "application/json"}
        )
        handshake = rpc(client, call("initialize"))

    assert garbage.status_code == 401
    assert garbage.json()["error"]["code"] == protocol.AUTHORIZATION_REQUIRED
    assert handshake.status_code == 401


@pytest.mark.asyncio
async def test_a_body_that_is_not_json_is_a_parse_error_once_the_caller_is_known():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = TestClient(server.app).post(
            "/mcp",
            content=b"{not json at all",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == protocol.PARSE_ERROR


# -- one budget, one ceiling, one kill switch --------------------------------


async def _noop_execute(run_id, treatment):
    return None


@contextlib.contextmanager
def building(daily_cap=None, ip_limiter=None):
    """Everything a build touches, faked, and nothing else."""
    with (
        mock.patch("star.server.verify_token", return_value=UID),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._execute", _noop_execute),
        mock.patch(
            "star.server._ip_limiter",
            ip_limiter or RateLimiter(max_per_window=99, window_seconds=3600),
        ),
        mock.patch("star.server._daily_cap", daily_cap or DailyCap(max_per_day=1000)),
        mock.patch.dict(server._runs, {}, clear=True),
    ):
        yield


def test_the_agent_doors_build_is_the_browsers_build():
    """Not "calls the same code" — IS the same function object. The partial
    binds the gate and nothing else, so `.func` is the function `POST
    /api/rooms` calls directly."""
    assert server._mcp_start_build.func is server._start_build
    assert server._mcp_start_build.keywords == {"gate": server._uid_gate}


@pytest.mark.asyncio
async def test_both_doors_decrement_one_daily_cap():
    cap = DailyCap(max_per_day=100)

    with building(daily_cap=cap):
        await server.create_room(
            server.RoomRequest(treatment=TREATMENT),
            request=_FakeRequest(),
            authorization=BROWSER_AUTH["Authorization"],
        )
        await server._mcp_start_build(UID, TREATMENT)

    assert cap.count_for() == 2, "the two doors are not counting into one budget"


@pytest.mark.asyncio
async def test_the_daily_cap_the_browser_spent_refuses_the_agent_door():
    """One kill switch. A budget the browser exhausted is exhausted for an
    agent too, and the refusal names the shared limit rather than reading as a
    per-caller one."""
    cap = DailyCap(max_per_day=1)

    with building(daily_cap=cap):
        await server.create_room(
            server.RoomRequest(treatment=TREATMENT),
            request=_FakeRequest(),
            authorization=BROWSER_AUTH["Authorization"],
        )
        with pytest.raises(server.HTTPException) as refused:
            await server._mcp_start_build(UID, TREATMENT)

    assert refused.value.status_code == 429
    assert "daily research limit" in refused.value.detail


@pytest.mark.asyncio
async def test_the_agent_door_is_limited_per_account_at_the_browsers_ceiling():
    ceiling = config.max_rooms_per_ip_per_hour()

    with building():
        for _ in range(ceiling):
            await server._mcp_start_build(UID, TREATMENT)
        with pytest.raises(server.HTTPException) as refused:
            await server._mcp_start_build(UID, TREATMENT)

    assert refused.value.status_code == 429
    # Names the ceiling, the window, and that reads are still free. A bare 429
    # fails prd.md's bar for a refusal an agent will actually hit.
    assert str(ceiling) in refused.value.detail
    assert "hour" in refused.value.detail
    assert "not limited" in refused.value.detail


@pytest.mark.asyncio
async def test_one_account_at_its_ceiling_does_not_throttle_another():
    """The whole reason the agent door does not key on the address: a desktop
    agent behind CGNAT shares one address with strangers, and a stranger's
    traffic must not spend its budget."""
    with building():
        for _ in range(config.max_rooms_per_ip_per_hour()):
            await server._mcp_start_build(UID, TREATMENT)
        await server._mcp_start_build(OTHER, TREATMENT)  # must not raise


@pytest.mark.asyncio
async def test_the_agent_doors_builds_never_touch_the_browsers_address_limiter():
    """The other half of the same argument: one address must not buy an
    unlimited budget, and it must not spend somebody else's either."""
    ip_limiter = RateLimiter(max_per_window=1, window_seconds=3600)

    with building(ip_limiter=ip_limiter):
        for _ in range(config.max_rooms_per_ip_per_hour()):
            await server._mcp_start_build(UID, TREATMENT)

    assert len(ip_limiter) == 0


@pytest.mark.asyncio
async def test_a_build_the_account_limiter_refuses_does_not_spend_a_daily_slot():
    """Finding 3's ordering, carried onto the second door. DailyCap.check()
    increments on the allow path — it is a spend, not a peek — so a request
    the free per-caller check is going to refuse must never reach it."""
    cap = DailyCap(max_per_day=100)
    ceiling = config.max_rooms_per_ip_per_hour()

    with building(daily_cap=cap):
        for _ in range(ceiling):
            await server._mcp_start_build(UID, TREATMENT)
        for _ in range(10):
            with pytest.raises(server.HTTPException):
                await server._mcp_start_build(UID, TREATMENT)

    assert cap.count_for() == ceiling


@pytest.mark.asyncio
async def test_reads_are_not_build_rate_limited():
    """`list_rooms` and `get_room` cost one Firestore call and no searches.
    Rationing them would ration the one call an agent makes to find out what
    it already owns — and would do it at exactly the moment the agent is
    trying to poll a build it just started."""
    fake_store = mock.Mock()
    fake_store.list_rooms.return_value = [{"run_id": "abc"}]
    fake_store.get.return_value = None

    with building():
        for _ in range(config.max_rooms_per_ip_per_hour()):
            await server._mcp_start_build(UID, TREATMENT)
        with pytest.raises(server.HTTPException):
            await server._mcp_start_build(UID, TREATMENT)

        with mock.patch("star.server._store", fake_store):
            for _ in range(20):
                assert await server._list_rooms_for(UID) == [{"run_id": "abc"}]
                with pytest.raises(server.HTTPException) as unknown:
                    await server._read_room(UID, "no-such-room")
                assert unknown.value.status_code == 404


def test_the_per_account_limiter_carries_a_key_bound():
    """star/guards.py:31-54 is the argument. The stale-key sweep is O(n) on
    every check() and runs on the single-threaded loop every open SSE stream
    shares, so an unbounded key set is a cost every caller pays. The agent
    door uses two key spaces per account rather than one, which makes the
    bound matter more here and not less."""
    limiter = RateLimiter(max_per_window=5, window_seconds=3600, max_keys=2)

    assert limiter.check("build:a") is True
    assert limiter.check("build:b") is True
    assert limiter.check("build:c") is False

    with mock.patch.object(
        server, "_uid_limiter", RateLimiter(max_per_window=1, window_seconds=1, max_keys=3)
    ):
        assert server._uid_limiter._max_keys == 3
    assert server._uid_limiter._max_keys == config.max_rate_limiter_keys()


def test_the_agent_doors_build_key_is_namespaced_away_from_its_check_key():
    """One limiter, two windows. Five builds an hour must not cost a writer
    their scene checks, and five checks must not cost them a build."""
    with mock.patch.object(
        server, "_uid_limiter", RateLimiter(max_per_window=1, window_seconds=3600)
    ):
        assert server._uid_gate(UID) is None
        assert server._uid_gate(UID) is not None
        # The check key is untouched by a build that exhausted the build key.
        assert server._uid_limiter.check(f"check:{UID}") is True


# -- the packaging line ------------------------------------------------------


def test_the_mcp_package_is_named_in_the_explicit_package_list():
    """spec.md calls this the highest-value line in the document per
    character, and the failure it prevents is invisible locally: the list is
    explicit rather than `find`, so a missing entry keeps a source checkout
    working and makes the deployed image 500 on import. A test is the only
    thing that fails on a laptop."""
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    packages = pyproject["tool"]["setuptools"]["packages"]

    assert "star.mcp" in packages
    # Every star.* package that exists on disk, not just this one. The next
    # subpackage anyone adds trips this instead of shipping a broken image.
    star = Path(__file__).resolve().parent.parent / "star"
    on_disk = {
        f"star.{child.name}" for child in star.iterdir() if (child / "__init__.py").is_file()
    }
    assert on_disk <= set(packages), f"missing from pyproject: {on_disk - set(packages)}"


def test_the_harness_is_excluded_from_the_source_upload():
    """.gcloudignore is what governs `gcloud run deploy --source .`;
    .dockerignore is not read by it. The harness drives the deployed service
    from outside and has no business in the upload."""
    ignored = (
        Path(__file__).resolve().parent.parent / ".gcloudignore"
    ).read_text(encoding="utf-8")

    assert "harness/" in ignored.split()


# -- pure protocol shaping ---------------------------------------------------


def test_a_message_without_the_jsonrpc_member_is_refused_by_name():
    outcome = protocol.classify({"id": 1, "method": "ping"})

    assert isinstance(outcome, protocol.Malformed)
    assert outcome.code == protocol.INVALID_REQUEST
    assert "jsonrpc" in outcome.message


def test_a_boolean_is_not_a_json_rpc_id():
    """`isinstance(True, int)` is True in Python, so the check has to say so
    explicitly or `"id": true` arrives as a request with an id of 1."""
    outcome = protocol.classify({"jsonrpc": "2.0", "id": True, "method": "ping"})

    assert isinstance(outcome, protocol.Malformed)


def test_positional_params_are_refused_rather_than_guessed_at():
    outcome = protocol.classify(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": ["build_room"]}
    )

    assert isinstance(outcome, protocol.Malformed)
    assert outcome.code == protocol.INVALID_PARAMS
    assert outcome.id == 1, "an error a client cannot join back to its call"


def test_absent_params_arrive_as_an_empty_object():
    outcome = protocol.classify({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert isinstance(outcome, protocol.Call)
    assert outcome.params == {}


def test_a_message_that_is_neither_a_call_nor_a_reply_is_refused():
    outcome = protocol.classify({"jsonrpc": "2.0", "id": 1})

    assert isinstance(outcome, protocol.Malformed)


def test_an_error_object_carries_the_json_rpc_envelope():
    assert protocol.error(3, -32601, "no") == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32601, "message": "no"},
    }


def test_the_refusal_bodies_are_json_rpc_objects_a_client_can_parse():
    """Both an HTTP status and a JSON-RPC error object, on every refusal this
    door hands out. A client that only reads statuses gets a number; one that
    only reads bodies gets a sentence naming what failed."""
    client = TestClient(server.app)
    with door():
        bodies = [
            client.get("/mcp"),
            client.delete("/mcp"),
            rpc(client, call("initialize")),
            rpc(client, call("initialize"), token=UNKNOWN_TOKEN, Origin="https://evil.example"),
        ]

    for response in bodies:
        parsed = json.loads(response.content)
        assert parsed["jsonrpc"] == "2.0"
        assert isinstance(parsed["error"]["code"], int)
        assert parsed["error"]["message"].strip()


# ============================================================================
# The four tools, and the strings an agent reads as the product
# ============================================================================
#
# Everything below asserts against copy. That is not a category error on this
# surface: an agent has no screen, so the descriptions and the refusals are
# the entire interface, and `prd.md > The Department Over MCP` fails the
# criterion outright for a bare status code, a bare "invalid request", or a
# stack trace. A test that only checked `isError` would pass on all three.

IDENTITY = tokens.TokenIdentity(uid=UID, token_id="a1b2c3d4e5f6")


def _unreachable(name):
    """A callable that fails the test if a tool reaches it.

    Every refusal below is supposed to happen BEFORE the server is asked to
    spend anything, and "before" is only observable as "the callable was never
    invoked". An AssertionError raised here also proves the second half:
    `tools.call` catches refusals and nothing else, so a defect still leaves
    this file rather than being flattened into a tool result.
    """

    async def _refuse(*args, **kwargs):
        raise AssertionError(f"{name} should not have been reached")

    return _refuse


def calls_for(**handlers) -> tools.Calls:
    """A `Calls` with only the callable under test wired up."""
    return tools.Calls(
        start_build=handlers.get("start_build") or _unreachable("start_build"),
        read_room=handlers.get("read_room") or _unreachable("read_room"),
        list_rooms_for=(
            handlers.get("list_rooms_for") or _unreachable("list_rooms_for")
        ),
        run_check=handlers.get("run_check") or _unreachable("run_check"),
        delete_room=handlers.get("delete_room") or _unreachable("delete_room"),
    )


async def invoke(name, arguments=None, **handlers) -> dict:
    return await tools.call(name, arguments or {}, calls_for(**handlers), IDENTITY)


def said(result: dict) -> str:
    """The one piece of text a calling model actually reads."""
    return result["content"][0]["text"]


def spoken(result: dict) -> str:
    """The prose half only — what a model actually READS before the payload.

    said() returns both halves, so an assertion about the warning passes when
    the number it looks for survives only in the JSON. Two mutations that
    stripped the department's sentence and left the payload intact were caught
    by nothing until this existed.
    """
    return said(result).rsplit("\n\n", 1)[0]


def carried(result: dict) -> dict:
    """The JSON half of a tool result, which is always the last block."""
    return json.loads(said(result).rsplit("\n\n", 1)[-1])


# -- the surface itself ------------------------------------------------------


def test_no_tool_is_a_second_name_for_another_tools_answer():
    """The rule this file has always enforced, stated as the rule rather than
    as a count.

    `get_room` IS `build_room`'s poll. A separate run-status tool would be a
    second name for one answer, and an agent would have to learn which of two
    calls tells the truth about a room. That is still refused.

    `ask_room` joined in 2026-08 and is not that. The three readers are
    distinguished by what they SELECT, not by what they know: `list_rooms`
    selects across rooms, `get_room` selects a whole room or a named part of
    one, and `ask_room` selects the findings that overlap a question. No two of
    them answer the same question with different words, which is the property
    the count was standing in for.
    """
    assert [tool["name"] for tool in tools.TOOLS] == [
        "list_rooms",
        "get_room",
        "ask_room",
        "delete_room",
        "build_room",
        "check_scene",
    ]
    assert set(tools._RUNNERS) == {tool["name"] for tool in tools.TOOLS}


def test_every_tool_carries_a_description_and_a_schema_a_client_can_read():
    for tool in tools.TOOLS:
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        # Declared closed, and enforced closed — see the unknown-argument test
        # below. A schema that says `additionalProperties: false` while the
        # implementation shrugs at extra keys teaches an agent the wrong thing
        # about its own mistakes.
        assert schema["additionalProperties"] is False
        assert set(schema.get("required") or []) <= set(schema["properties"])
        for prop in schema["properties"].values():
            assert prop["type"] == "string"
            assert prop["description"].strip()

        description = tool["description"]
        assert len(description) > 300, tool["name"]
        # What it costs, before the call is made. The one thing a person reads
        # off a screen and an agent has no way to find out.
        assert "cost" in description.lower(), tool["name"]
        # And where to go next, named as a tool rather than described.
        others = {t["name"] for t in tools.TOOLS} - {tool["name"]}
        assert any(other in description for other in others), tool["name"]

    # It goes on the wire exactly as written.
    json.dumps(list(tools.TOOLS))


def test_build_room_names_a_poll_interval_rather_than_leaving_it_to_guesswork():
    """An agent with no interval picks one of two bad ones: immediately and
    forever, or once in five minutes."""
    description = tools._TOOLS_BY_NAME["build_room"]["description"]

    assert f"{tools.POLL_SECONDS} seconds" in description
    assert "get_room" in description
    assert "several minutes" in description
    # Never a duration promise (obligation 6). "several minutes" is honest;
    # "about 90 seconds" is not, and the build has run 146s to 420s+.
    assert "minutes" not in description.replace("several minutes", "")


def test_get_room_names_all_five_statuses_it_can_answer_with():
    description = tools._TOOLS_BY_NAME["get_room"]["description"]

    for status in ("running", "complete", "partial", "error", "interrupted"):
        assert f"`{status}`" in description
    assert "no separate status tool" in description


def test_check_scenes_description_states_that_the_scene_is_stored():
    """Obligation 5's agent-facing form. The browser discloses retention above
    the paste box; this description is the only place the same disclosure can
    live for a caller that never sees one."""
    description = tools._TOOLS_BY_NAME["check_scene"]["description"]

    assert "The scene text is stored with the room" in description
    assert "deleted" in description


def test_the_instructions_explain_the_department_rather_than_padding_the_handshake():
    """`initialize` is the only place a client is told anything before it
    starts guessing, and spec.md names three facts it owes: minutes and a
    run_id to poll, citations hydrated from what search returned, and a scene
    stored with its room."""
    instructions = tools.INSTRUCTIONS

    assert "run_id" in instructions
    assert f"{tools.POLL_SECONDS} seconds" in instructions
    assert "several minutes" in instructions
    assert "live web search actually returned" in instructions
    assert "stored with its room" in instructions
    assert "six tools" in instructions
    # The cheapest way in is named in the handshake, because an agent that
    # only reads INSTRUCTIONS should not have to discover it from tools/list.
    assert "ask_room" in instructions


@pytest.mark.asyncio
async def test_tools_list_puts_them_all_on_the_wire_with_their_descriptions():
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        body = rpc(TestClient(server.app), call("tools/list"), token=token).json()

    listed = body["result"]["tools"]
    assert [tool["name"] for tool in listed] == [
        "list_rooms",
        "get_room",
        "ask_room",
        "delete_room",
        "build_room",
        "check_scene",
    ]
    for tool in listed:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"


# -- what a call actually answers with ---------------------------------------


@pytest.mark.asyncio
async def test_an_empty_account_is_told_it_is_empty_rather_than_handed_an_empty_list():
    """The first thing a fresh agent sees, and `[]` cannot tell it whether the
    account is wrong, the call is broken, or the writer simply has not started
    yet."""

    async def _none(uid):
        assert uid == UID
        return []

    result = await invoke("list_rooms", list_rooms_for=_none)

    assert result["isError"] is False
    assert "No rooms are filed under this account yet" in said(result)
    assert "not an error" in said(result)
    assert "build_room" in said(result)


@pytest.mark.asyncio
async def test_list_rooms_names_the_count_and_what_the_ids_are_for():
    async def _two(uid):
        return [{"run_id": "aaa"}, {"run_id": "bbb"}]

    result = await invoke("list_rooms", list_rooms_for=_two)

    assert result["isError"] is False
    assert said(result).startswith("2 rooms filed under this account")
    assert carried(result) == {"rooms": [{"run_id": "aaa"}, {"run_id": "bbb"}]}


@pytest.mark.asyncio
async def test_polling_a_room_still_being_built_answers_running_and_is_not_an_error():
    """`prd.md`'s edge, stated as an edge: never an error, never a blocking
    wait. The run registry holds no partial result while a build is in flight
    (star/server.py sets `run["result"]` only at the end), so the honest
    answer is the status plus what to do with it — and saying "nothing is
    filed yet" beats an empty payload with no explanation."""

    async def _running(uid, run_id):
        return {"status": "running", "result": None}

    result = await invoke("get_room", {"run_id": "abc"}, read_room=_running)

    assert result["isError"] is False
    # `shape` joined this payload when get_room learned to return less than the
    # whole room. It is always present, including on the default, so an agent
    # can tell what it was handed from the JSON alone rather than by parsing the
    # sentence above it — and so a room that came back small never has to be
    # guessed at. Additive: `run_id`, `status` and `room` are unchanged.
    assert carried(result) == {
        "run_id": "abc",
        "status": "running",
        "shape": "full",
        "room": None,
    }
    assert "still being built" in said(result)
    assert f"{tools.POLL_SECONDS} seconds" in said(result)
    assert "not an error" in said(result)


@pytest.mark.asyncio
async def test_a_run_that_died_with_the_process_reports_interrupted_verbatim():
    """Not translated into a failure. A run that did not survive a restart is
    a distinct outcome: nothing more is coming, and whatever it filed is still
    good. An agent told "error" would reasonably poll again waiting for it to
    resolve into something."""
    filed = {"categories": {"setting": {"findings": [{"fact": "x"}]}}}

    async def _interrupted(uid, run_id):
        return {"status": "interrupted", "result": filed}

    result = await invoke("get_room", {"run_id": "abc"}, read_room=_interrupted)

    assert result["isError"] is False
    assert carried(result)["status"] == "interrupted"
    assert "interrupted" in said(result)
    assert "will never finish" in said(result)
    assert "will not change" in said(result)


@pytest.mark.asyncio
async def test_an_interrupted_room_that_filed_nothing_promises_no_findings():
    """A build persists its document the moment it starts, so an interrupted
    room usually carries the shape of a room with nothing in it. "What it
    filed is below" sends an agent to read an empty payload."""

    async def _empty(uid, run_id):
        return {"status": "interrupted", "result": {"categories": {}}}

    result = await invoke("get_room", {"run_id": "abc"}, read_room=_empty)

    assert "the room below is empty" in said(result)
    assert "is below and will not change" not in said(result)


def test_each_terminal_status_gets_its_own_sentence():
    """Five statuses, five answers. A shared "the build is done" would leave
    an agent unable to tell a finished room from a failed one without parsing
    the payload it was just handed."""
    reports = {
        status: tools._room_report(status, {"categories": {}})
        for status in ("running", "complete", "partial", "error", "interrupted")
    }

    assert len(set(reports.values())) == 5
    # And an unfamiliar one says it is unfamiliar rather than guessing.
    assert "no description for" in tools._room_report("quarantined", None)


@pytest.mark.asyncio
async def test_build_room_hands_back_a_run_id_and_never_the_streams_capability():
    """`stream_key` guards a run's SSE stream, and this door has no stream:
    GET /mcp is a 405 by design. Returning it would be exposure bought for
    nothing."""

    async def _started(uid, treatment):
        assert uid == UID
        return {"run_id": "3f2a91c4b0de", "stream_key": "s" * 32}

    result = await invoke("build_room", {"treatment": TREATMENT}, start_build=_started)

    assert result["isError"] is False
    assert carried(result) == {"run_id": "3f2a91c4b0de", "status": "running"}
    assert "s" * 32 not in said(result)
    assert f"{tools.POLL_SECONDS} seconds" in said(result)
    assert "get_room" in said(result)


@pytest.mark.asyncio
async def test_check_scene_reports_the_tally_the_cost_and_the_retention():
    async def _checked(uid, run_id, scene):
        assert scene == "INT. STUDIO - NIGHT"
        return ScriptCheckResult(
            scene_id="sc0001",
            created_at="2026-08-10T00:00:00+00:00",
            claims=[
                ClaimResult(
                    text="a 1961 Impala",
                    claim_type="object",
                    verdict=Verdict.CONFIRMED,
                    citations=[
                        Citation(url="https://e.example", title="T", excerpt="E")
                    ],
                    citation_sources=["room"],
                ),
                ClaimResult(
                    text="a fax machine",
                    claim_type="technology",
                    verdict=Verdict.ANACHRONISM,
                    citations=[
                        Citation(url="https://f.example", title="U", excerpt="F")
                    ],
                    citation_sources=["search"],
                ),
            ],
            search_count=3,
            unsourced_count=1,
        )

    result = await invoke(
        "check_scene",
        {"run_id": "abc", "scene": "  INT. STUDIO - NIGHT  "},
        run_check=_checked,
    )

    text = said(result)
    assert result["isError"] is False
    assert "2 claims" in text
    assert "1 confirmed, 1 anachronism, 0 unverifiable" in text
    assert "spent 3 live web searches" in text
    assert "1 cited URL turned up in neither" in text
    # Obligation 5 again, at the moment it becomes true rather than only in
    # the description that was read before the call.
    assert "scene text is now stored with this room" in text
    # The enum arrives as a string, not as a Python repr.
    assert [claim["verdict"] for claim in carried(result)["claims"]] == [
        "confirmed",
        "anachronism",
    ]


@pytest.mark.asyncio
async def test_a_thin_check_carries_the_departments_own_cover_note():
    """A scene that asserts nothing about the world is a result, and an empty
    claim list reaches a reader with no screen as a failure unless something
    says otherwise."""

    async def _nothing(uid, run_id, scene):
        return ScriptCheckResult(
            scene_id="sc0002",
            created_at="2026-08-10T00:00:00+00:00",
            claims=[],
            cover_note=(
                "Nothing in this scene made a claim about the world, so there "
                "was nothing for the department to check."
            ),
        )

    result = await invoke(
        "check_scene", {"run_id": "abc", "scene": "She is afraid."}, run_check=_nothing
    )

    assert result["isError"] is False
    assert "0 claims" in said(result)
    assert "nothing for the department to check" in said(result)
    # And not a paragraph describing what each claim below carries, printed
    # over no claims at all. That reads as a payload the reader lost.
    assert "Each claim below" not in said(result)
    # The retention disclosure still stands, because the scene was still kept.
    assert "now stored with this room" in said(result)


# -- the eleven refusals -----------------------------------------------------


async def _the_two_ceilings() -> dict[str, str]:
    """The hourly and daily refusals, read off the server rather than restated.

    Both are the server's own sentences and the tool layer passes them through
    untouched, so a test that hard-coded them here would be asserting against
    a copy and would keep passing after the original changed.
    """
    with mock.patch.object(
        server, "_uid_limiter", RateLimiter(max_per_window=1, window_seconds=3600)
    ):
        server._uid_gate(UID)
        hourly = server._uid_gate(UID)

    with (
        building(daily_cap=DailyCap(max_per_day=0)),
        pytest.raises(server.HTTPException) as daily,
    ):
        await server._mcp_start_build(UID, TREATMENT)

    return {
        "per-account hourly ceiling": hourly,
        "shared daily budget": daily.value.detail,
    }


async def delivered(status: int, detail: str) -> str:
    """One of the server's refusals, as the agent door actually hands it over."""

    async def _raise(uid, treatment):
        raise server.HTTPException(status, detail)

    return said(
        await invoke("build_room", {"treatment": TREATMENT}, start_build=_raise)
    )


@pytest.mark.asyncio
async def test_every_row_of_the_error_table_has_a_message_of_its_own():
    """spec.md's eleven rows, compared as a set rather than read by eye.

    Two of them are not errors and are here anyway: a room still building and
    a room whose build was interrupted are answers, and the reason they need
    their own words is exactly the reason the nine refusals do.
    """
    rows = {
        "no token": tokens.MISSING.message,
        "bad or unknown token": tokens.UNRECOGNISED.message,
        "revoked token": tokens.REVOKED.message,
        "room not found": tools.ROOM_NOT_FOUND,
        "treatment too short": tools.treatment_too_short(12),
        "treatment too long": tools.treatment_too_long(9001, 8000),
        "scene too long": tools.scene_too_long(9001, 8000),
        "run still building": tools.STILL_BUILDING,
        "run interrupted": tools._room_report("interrupted", None),
    }
    # As delivered, not as raised. The tool layer adds the half a screen would
    # have carried, and what an agent reads is what this row has to be.
    for label, detail in (await _the_two_ceilings()).items():
        rows[label] = await delivered(429, detail)

    assert len(rows) == 11
    assert len(set(rows.values())) == 11, "two rows are sharing one message"
    for label, message in rows.items():
        # A sentence, not a code. Eight words is the floor because the
        # shortest legitimate row — the revoked token — needs ten to name
        # what failed and where to get a new one.
        assert len(message.split()) >= 8, label
        assert message.strip().endswith("."), label


@pytest.mark.asyncio
async def test_an_unknown_room_is_told_how_to_get_an_id_that_works():
    """"Room not found" on its own fails the criterion. On screen that answer
    lands beside a rail listing every room the reader owns; here there is no
    rail."""

    async def _missing(uid, run_id):
        raise server.HTTPException(404, "Unknown run")

    result = await invoke("get_room", {"run_id": "nope"}, read_room=_missing)

    assert result["isError"] is True
    assert said(result) == tools.ROOM_NOT_FOUND
    assert "list_rooms" in said(result)
    assert "Unknown run" not in said(result)


@pytest.mark.asyncio
async def test_check_scene_gets_the_same_answer_for_a_room_it_cannot_reach():
    async def _missing(uid, run_id, scene):
        raise server.HTTPException(404, "Unknown run")

    result = await invoke(
        "check_scene", {"run_id": "nope", "scene": "INT. BAR"}, run_check=_missing
    )

    assert result["isError"] is True
    assert said(result) == tools.ROOM_NOT_FOUND


@pytest.mark.asyncio
async def test_a_short_treatment_is_refused_before_anything_is_spent():
    """`_unreachable` is the assertion that matters here: the refusal happens
    ahead of `_start_build`, so no hourly slot and no daily slot is charged
    for a treatment the department was never going to plan from."""
    result = await invoke("build_room", {"treatment": "A movie about a car."})

    text = said(result)
    assert result["isError"] is True
    assert str(tools.MIN_TREATMENT_CHARS) in text
    assert "20 characters" in text
    # The three things the planner actually needs, asked for by name.
    assert "when the story is set" in text
    assert "where it happens" in text
    assert "what the characters actually do" in text


@pytest.mark.asyncio
async def test_a_long_treatment_names_the_cap_and_the_count_that_was_sent():
    cap = config.max_treatment_chars()
    result = await invoke("build_room", {"treatment": "x" * (cap + 1)})

    text = said(result)
    assert result["isError"] is True
    assert str(cap) in text
    assert str(cap + 1) in text
    assert "Nothing was spent" in text


@pytest.mark.asyncio
async def test_a_long_scene_names_the_cap_and_the_count_that_was_sent():
    cap = config.max_scene_chars()
    result = await invoke("check_scene", {"run_id": "abc", "scene": "x" * (cap + 1)})

    text = said(result)
    assert result["isError"] is True
    assert str(cap) in text
    assert str(cap + 1) in text
    assert "nothing was stored" in text


@pytest.mark.asyncio
async def test_the_floor_this_module_names_is_the_floor_the_server_enforces():
    """The one number written down twice. star/server.py:693 is the authority;
    this module refuses ahead of it only so the message can name the floor and
    say what a treatment needs to contain. Drift fails here rather than
    shipping a refusal that names a number nothing enforces."""
    with building():
        await server._mcp_start_build(UID, "e" * tools.MIN_TREATMENT_CHARS)
        with pytest.raises(server.HTTPException) as refused:
            await server._mcp_start_build(UID, "e" * (tools.MIN_TREATMENT_CHARS - 1))

    assert refused.value.status_code == 400


@pytest.mark.asyncio
async def test_a_ceiling_the_server_refuses_reaches_the_agent_in_its_own_words():
    """Passed through rather than re-worded. The hourly refusal already names
    the ceiling, the window, and that reads are still free; a second copy here
    is a second thing to keep in step."""
    ceilings = await _the_two_ceilings()

    async def _refused(uid, treatment):
        raise server.HTTPException(429, ceilings["per-account hourly ceiling"])

    result = await invoke("build_room", {"treatment": TREATMENT}, start_build=_refused)

    assert result["isError"] is True
    assert said(result) == ceilings["per-account hourly ceiling"]
    assert str(config.max_rooms_per_ip_per_hour()) in said(result)
    assert "hour" in said(result)
    assert "not limited" in said(result)
    # Nothing bolted on, because the server's sentence already carries it.
    assert tools.READS_ARE_FREE not in said(result)


@pytest.mark.asyncio
async def test_the_daily_budget_refusal_is_told_that_reading_still_works():
    """The one refusal on this surface that could stop an agent cold. On
    screen the rail keeps listing rooms while the daily cap is spent, so the
    browser never has to say it; an agent reads "STAR has hit its daily
    research limit" and can reasonably conclude the whole department is shut,
    reads included. It is not."""
    ceilings = await _the_two_ceilings()
    text = await delivered(429, ceilings["shared daily budget"])

    assert ceilings["shared daily budget"] in text
    assert "daily" in text
    assert "tomorrow" in text
    assert tools.READS_ARE_FREE in text
    assert "list_rooms" in text


@pytest.mark.asyncio
async def test_a_room_that_is_not_ready_is_told_how_to_find_out_when_it_is():
    """"Give the department a moment" is a browser sentence: on screen there
    is a live timeline saying when the moment is over. Here there is not."""

    async def _building(uid, run_id, scene):
        raise server.HTTPException(
            409,
            "This room is still being built. Give the department a moment to "
            "finish filing, then check the scene against it.",
        )

    result = await invoke(
        "check_scene", {"run_id": "abc", "scene": "INT. BAR"}, run_check=_building
    )

    assert result["isError"] is True
    assert "still being built" in said(result)
    assert tools.WAIT_FOR_THE_ROOM in said(result)
    assert f"{tools.POLL_SECONDS} seconds" in said(result)


# -- arguments an agent got wrong --------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_argument_is_named_along_with_what_it_is_for():
    result = await invoke("get_room", {})

    text = said(result)
    assert result["isError"] is True
    assert "`get_room` needs `run_id`" in text
    # The property's own description, so the sentence an agent reads in
    # tools/list and the sentence it gets back cannot disagree.
    assert tools._ROOM_ID in text
    assert "tools/list" in text


@pytest.mark.asyncio
async def test_an_argument_of_the_wrong_type_is_told_what_it_sent():
    result = await invoke("get_room", {"run_id": 12})

    text = said(result)
    assert result["isError"] is True
    assert "must be a string" in text
    assert "a number" in text


@pytest.mark.asyncio
async def test_an_empty_argument_is_not_treated_as_an_id():
    result = await invoke("check_scene", {"run_id": "abc", "scene": "   "})

    assert result["isError"] is True
    assert "`scene` arrived empty" in said(result)


@pytest.mark.asyncio
async def test_an_argument_this_tool_does_not_take_is_named_rather_than_ignored():
    """The failure this prevents is a loop, not a wasted call. Ignore `roomId`
    and the tool sees no `run_id`, so the refusal talks about a missing
    argument the agent is certain it supplied."""
    result = await invoke("get_room", {"roomId": "abc"})

    text = said(result)
    assert result["isError"] is True
    assert "does not take an argument called `roomId`" in text
    assert "`run_id`" in text


@pytest.mark.asyncio
async def test_list_rooms_says_it_takes_nothing_when_it_is_handed_something():
    result = await invoke("list_rooms", {"limit": "5"})

    assert result["isError"] is True
    assert "no arguments at all" in said(result)


@pytest.mark.asyncio
async def test_check_scene_names_both_of_its_arguments_when_one_is_wrong():
    result = await invoke("check_scene", {"room": "abc", "scene": "INT. BAR"})

    assert "`run_id`" in said(result)
    assert "`scene`" in said(result)


# -- the split: tool failures vs protocol failures ---------------------------


@pytest.mark.asyncio
async def test_a_refused_tool_call_is_a_tool_result_and_not_a_json_rpc_error():
    """The whole error posture, end to end on the wire. A model can read this
    and act on it; a JSON-RPC error would tell it the client is broken, which
    is not a thing a model can fix."""
    store, _ = a_token_store()
    token = await issue(store)
    fake_store = mock.Mock()
    fake_store.get.return_value = None

    with (
        door(store),
        mock.patch("star.server._store", fake_store),
        mock.patch.dict(server._runs, {}, clear=True),
    ):
        body = rpc(
            TestClient(server.app),
            call("tools/call", name="get_room", arguments={"run_id": "nope"}),
            token=token,
        ).json()

    assert "error" not in body
    assert body["result"]["isError"] is True
    assert body["result"]["content"][0]["text"] == tools.ROOM_NOT_FOUND


@pytest.mark.asyncio
async def test_a_tool_that_does_not_exist_is_told_the_four_that_do():
    result = await invoke("build_a_bear", {})

    text = said(result)
    assert result["isError"] is True
    for name in ("list_rooms", "get_room", "build_room", "check_scene"):
        assert name in text


# -- the copy rule that binds every surface ----------------------------------


async def every_string_an_agent_reads() -> dict[str, str]:
    """Everything this door can put in front of a model, gathered in one place.

    Assembled by driving the refusals rather than by listing constants, so a
    string added later without a test of its own is still swept by the two
    checks below.
    """
    strings = {"instructions": tools.INSTRUCTIONS}
    for tool in tools.TOOLS:
        strings[f"{tool['name']} description"] = tool["description"]
        for name, prop in tool["inputSchema"]["properties"].items():
            strings[f"{tool['name']}.{name}"] = prop["description"]

    strings["room not found"] = tools.ROOM_NOT_FOUND
    strings["still building"] = tools.STILL_BUILDING
    strings["treatment too short"] = tools.treatment_too_short(12)
    strings["treatment too long"] = tools.treatment_too_long(9001, 8000)
    strings["scene too long"] = tools.scene_too_long(9001, 8000)
    for status in ("running", "complete", "partial", "error", "interrupted"):
        empty = {"categories": {}}
        full = {"categories": {"setting": {"findings": [{"fact": "x"}]}}}
        strings[f"room report {status} empty"] = tools._room_report(status, empty)
        strings[f"room report {status} filed"] = tools._room_report(status, full)

    async def _none(uid):
        return []

    strings["reads are free"] = tools.READS_ARE_FREE
    strings["wait for the room"] = tools.WAIT_FOR_THE_ROOM
    strings["empty account"] = said(await invoke("list_rooms", list_rooms_for=_none))
    strings["unknown tool"] = said(await invoke("no_such_tool", {}))
    strings["missing argument"] = said(await invoke("get_room", {}))
    strings["wrong type"] = said(await invoke("get_room", {"run_id": 1}))
    strings["blank argument"] = said(await invoke("get_room", {"run_id": " "}))
    strings["unknown argument"] = said(await invoke("get_room", {"roomId": "a"}))
    return strings


@pytest.mark.asyncio
async def test_nothing_an_agent_reads_calls_a_source_verified():
    """The rule that binds every other surface in this project, applied to the
    one surface with no pixels. What the department can honestly say is which
    ledger a citation came out of, and it says that instead."""
    for label, text in (await every_string_an_agent_reads()).items():
        assert "verified" not in text.lower(), label


@pytest.mark.asyncio
async def test_nothing_an_agent_reads_is_a_bare_code_or_our_own_vocabulary():
    """The three shapes `prd.md` fails a refusal for, plus the leak
    star/server.py's `_execute` was rewritten to close."""
    banned = ("traceback", "exception", "http 4", "http 5", "status code")
    for label, text in (await every_string_an_agent_reads()).items():
        lowered = text.lower()
        assert len(text.split()) >= 8, label
        for word in banned:
            assert word not in lowered, f"{label} carries {word!r}"


@pytest.mark.asyncio
async def test_initialize_tells_a_client_what_to_draw_on_its_own_card():
    """serverInfo is `Implementation`, which extends BaseMetadata and Icons.

    STAR sent two of its seven fields for a while, and the cost was visible in
    a client's chrome rather than theoretical: with no icon to use, a connector
    card fell back to guessing from the registrable domain and rendered a
    different product's mark. Serving /favicon.ico on this origin cannot fix
    that, because a client taking that fallback never asks this origin.

    So the assertion is not that the fields exist, it is that every icon URL
    points at THIS service and is actually served by it. A declared icon that
    404s is the same failure with an extra step.
    """
    store, _ = a_token_store()
    token = await issue(store)

    with door(store):
        response = rpc(TestClient(server.app), call("initialize"), token=token)

    info = response.json()["result"]["serverInfo"]
    assert info["name"] == "star", "the identifier a client keys on"
    assert info["title"], "the display name, distinct from the identifier"
    assert info["description"], "one sentence, because a card has one line"
    assert info["icons"], "without this a client guesses from the domain"

    client = TestClient(server.app)
    for icon in info["icons"]:
        assert icon["src"].startswith(SERVICE_ORIGIN), (
            f"{icon['src']} is not served by this department"
        )
        served = client.get(urlsplit(icon["src"]).path)
        assert served.status_code == 200, f"{icon['src']} is declared but not served"
        assert served.headers["content-type"].startswith(
            icon["mimeType"].split(";")[0]
        ), f"{icon['src']} is served as something other than what it claims"


# -- get_room's shape argument -----------------------------------------------
#
# The biggest defect on this surface before it existed: one shape, no way to ask
# for less, and about 30,000 tokens on a complete room. Measured against the two
# stored rooms on 2026-08-11 at 31,047 and 29,536 tokens, of which 72.3% was the
# quoted excerpt under each source and 4.4% was the research facts themselves.
# An agent polling a finished build paid the whole room to learn one thing.


def _full_room() -> dict:
    """A room shaped like a real one, small enough to assert against.

    The proportions are what matter: the excerpts dwarf the facts, which is the
    property the `findings` shape exists to exploit.
    """
    return {
        "created_at": "2026-08-10T12:00:00+00:00",
        "story_profile": {"title": "Gdansk 1978", "era": "Autumn 1978"},
        "research_plan": {"questions": [{"q": "what did the gate look like"}]},
        "research_bible": "THE BIBLE. " * 20,
        "search_count": 17,
        "source_count": 110,
        "categories": {
            "setting": {
                "findings": [
                    {
                        "fact": "Gate No. 2 is the shipyard's main gate.",
                        "citations": [
                            {
                                "url": "https://example.org/gate",
                                "title": "Gate No. 2",
                                "excerpt": "A very long quoted passage. " * 40,
                            }
                        ],
                        "unverified_urls": ["https://example.org/never-returned"],
                    }
                ]
            },
            "logistics": {"findings": []},
        },
    }


async def _read_full(uid, run_id):
    return {"status": "complete", "result": _full_room()}


@pytest.mark.asyncio
async def test_get_room_defaults_to_the_whole_room_and_says_so():
    """An agent written before `shape` existed is unaffected."""
    result = await invoke("get_room", {"run_id": "abc"}, read_room=_read_full)
    body = carried(result)
    assert body["shape"] == "full"
    assert body["room"] == _full_room(), "the default returns the room untouched"
    # No shape note on the default: there is nothing to warn about.
    assert "left out" not in said(result)


@pytest.mark.asyncio
async def test_findings_keeps_every_fact_and_source_and_drops_the_quotes():
    """The 72% cut. Nothing an agent needs to reason or to re-fetch is lost."""
    result = await invoke(
        "get_room", {"run_id": "abc", "shape": "findings"}, read_room=_read_full
    )
    body = carried(result)
    finding = body["room"]["categories"]["setting"]["findings"][0]

    assert finding["fact"] == "Gate No. 2 is the shipyard's main gate."
    citation = finding["citations"][0]
    assert citation["url"] == "https://example.org/gate", "the source stays fetchable"
    assert citation["title"] == "Gate No. 2"
    assert "excerpt" not in citation, "the quote is the part that goes"
    assert finding["unverified_urls"] == ["https://example.org/never-returned"], (
        "an unsourced warning is a finding about the research and is never a "
        "quote — dropping it would hide the thing the ledger check exists for"
    )
    assert "research_bible" not in body["room"], "the bible is not findings"

    # And it is genuinely smaller, measured rather than asserted in prose.
    full = await invoke("get_room", {"run_id": "abc"}, read_room=_read_full)
    assert len(said(result)) < len(said(full)) / 2


@pytest.mark.asyncio
async def test_bible_and_plan_and_summary_each_return_only_their_part():
    bible = carried(
        await invoke("get_room", {"run_id": "abc", "shape": "bible"}, read_room=_read_full)
    )["room"]
    assert bible["research_bible"].startswith("THE BIBLE.")
    assert "categories" not in bible

    plan = carried(
        await invoke("get_room", {"run_id": "abc", "shape": "plan"}, read_room=_read_full)
    )["room"]
    assert plan["research_plan"]["questions"], "the plan is what was set out to find"
    assert "categories" not in plan, "and not what was found"

    summary = carried(
        await invoke("get_room", {"run_id": "abc", "shape": "summary"}, read_room=_read_full)
    )["room"]
    assert summary["drawers"]["setting"] == {"findings": 1, "citations": 1}
    assert summary["drawers"]["logistics"] == {"findings": 0, "citations": 0}
    assert summary["research_bible_chars"] == len(_full_room()["research_bible"])
    assert "categories" not in summary and "research_bible" not in summary


@pytest.mark.asyncio
async def test_every_cut_announces_itself():
    """A shape must never be mistakable for an empty room.

    This is the whole risk of the argument: an agent reads a `findings` room,
    sees no excerpts, and concludes the sources have none.
    """
    for shape, expected in (
        ("summary", "no findings, no sources and no bible"),
        ("bible", "were not returned"),
        ("plan", "not what it found"),
        ("findings", "left out"),
    ):
        result = await invoke(
            "get_room", {"run_id": "abc", "shape": shape}, read_room=_read_full
        )
        text = said(result)
        assert expected in text, f"{shape}: the reply must say what it left out"
        assert "`shape`" in text, f"{shape}: and how to ask for the rest"


@pytest.mark.asyncio
async def test_category_narrows_to_one_drawer():
    result = await invoke(
        "get_room",
        {"run_id": "abc", "shape": "findings", "category": "setting"},
        read_room=_read_full,
    )
    body = carried(result)
    assert list(body["room"]["categories"]) == ["setting"]
    assert "`setting` drawer" in said(result)


@pytest.mark.asyncio
async def test_an_unknown_shape_is_refused_by_name_with_the_list():
    """The refusal rule this file exists for: say what failed and what works."""
    result = await invoke(
        "get_room", {"run_id": "abc", "shape": "everything"}, read_room=_read_full
    )
    assert result["isError"] is True
    text = said(result)
    assert "`everything`" in text, "name what was sent"
    for shape in tools._SHAPES:
        assert f"`{shape}`" in text, f"and list `{shape}` as an option"


@pytest.mark.asyncio
async def test_a_running_room_is_unaffected_by_shape():
    """Nothing is filed yet, so every shape is the same answer."""

    async def _running(uid, run_id):
        return {"status": "running", "result": None}

    body = carried(
        await invoke("get_room", {"run_id": "abc", "shape": "bible"}, read_room=_running)
    )
    assert body == {"run_id": "abc", "status": "running", "shape": "bible", "room": None}


# -- ask_room ----------------------------------------------------------------
#
# The adoption tool: an agent that knows nothing about a room's structure can
# ask it a question. Its whole discipline is that it RETRIEVES and never
# SYNTHESISES — it returns the department's own findings, ranked by overlap
# with the question, and writes no answer of its own. That keeps it inside the
# door's cost model (reads are free, and a model call would not be) and inside
# the app's epistemology: nothing on this surface asserts what was not checked.


@pytest.mark.asyncio
async def test_ask_room_returns_the_findings_that_overlap_the_question():
    result = await invoke(
        "ask_room",
        {"run_id": "abc", "question": "what did the shipyard gate look like"},
        read_room=_read_full,
    )
    body = carried(result)

    assert body["matches"], "the setting finding shares 'gate' and 'shipyard'"
    match = body["matches"][0]
    assert match["fact"] == "Gate No. 2 is the shipyard's main gate."
    assert match["category"] == "setting"
    assert match["citations"][0]["url"] == "https://example.org/gate"
    assert "excerpt" not in match["citations"][0], "quotes are 72% of a room"
    assert body["searched"] == 1, "one finding was in scope"


@pytest.mark.asyncio
async def test_ask_room_says_plainly_when_a_room_does_not_answer():
    """The honesty case, and the reason this tool does not call a model.

    A room researched for one thing does not contain another, and the useful
    answer is to say so and point at `build_room` — not to stretch the closest
    finding into a response.
    """
    result = await invoke(
        "ask_room",
        {"run_id": "abc", "question": "what were the tram timetables in Lisbon"},
        read_room=_read_full,
    )
    body = carried(result)
    text = said(result)

    assert body["matches"] == []
    assert body["matched"] == 0
    assert "does not answer it" in text
    assert "not a failure of the search" in text, (
        "an empty result is a fact about the research, and saying so is the "
        "difference between a useful answer and a shrug"
    )
    assert "`build_room`" in text, "and it says how to get research that would"


@pytest.mark.asyncio
async def test_ask_room_never_writes_an_answer_of_its_own():
    """Every fact returned is verbatim from the room.

    This is the property that keeps the tool inside the app's epistemology. If
    it ever paraphrases, the surface starts asserting things no ledger backs.
    """
    room = _full_room()
    result = await invoke(
        "ask_room",
        {"run_id": "abc", "question": "shipyard gate"},
        read_room=_read_full,
    )
    filed = {
        f["fact"] for doc in room["categories"].values() for f in doc["findings"]
    }
    for match in carried(result)["matches"]:
        assert match["fact"] in filed, "a returned fact must be one the room filed"
    assert "not a model reading the room" in tools._TOOLS_BY_NAME["ask_room"]["description"]


@pytest.mark.asyncio
async def test_ask_room_ranks_by_overlap_and_says_when_it_is_showing_a_slice():
    """Best first, and honest about the cut when more matched than fit."""

    async def _many(uid, run_id):
        # Twelve, written out, NOT _ASK_LIMIT + 4. Deriving the fixture from
        # the constant makes the assertions below follow the constant, and a
        # mutation that raised the cap to 400 passed this test unchanged.
        findings = [
            {"fact": f"The gate had {n} guards posted overnight.", "citations": [], "unverified_urls": []}
            for n in range(12)
        ]
        # One finding overlaps far more of the question than the rest.
        findings[3]["fact"] = "The shipyard gate carried strike decorations overnight."
        return {"status": "complete", "result": {"categories": {"setting": {"findings": findings}}}}

    result = await invoke(
        "ask_room",
        {"run_id": "abc", "question": "shipyard gate strike decorations"},
        read_room=_many,
    )
    body = carried(result)
    assert body["matches"][0]["fact"].startswith("The shipyard gate carried strike")
    assert len(body["matches"]) == 8, "capped at eight, stated as a number"
    assert body["matched"] == 12, "and the true total is reported, not the cap"
    assert len(body["matches"]) < body["matched"], "so an agent knows it has a slice"
    assert "closest" in said(result)


@pytest.mark.asyncio
async def test_ask_room_can_be_narrowed_to_one_drawer():
    result = await invoke(
        "ask_room",
        {"run_id": "abc", "question": "gate", "category": "logistics"},
        read_room=_read_full,
    )
    body = carried(result)
    assert body["matches"] == [], "the gate finding is in setting, not logistics"
    assert "`logistics` drawer" in said(result)


@pytest.mark.asyncio
async def test_ask_room_on_a_running_room_says_to_wait_rather_than_answering():
    async def _running(uid, run_id):
        return {"status": "running", "result": None}

    result = await invoke(
        "ask_room", {"run_id": "abc", "question": "anything"}, read_room=_running
    )
    assert result["isError"] is False
    assert "still being built" in said(result)
    body = carried(result)
    assert body["matches"] == []
    assert body["question"] == "anything", (
        "the question comes back even when there is nothing to match it "
        "against — an agent correlating replies should not have to remember "
        "which call this was"
    )


@pytest.mark.asyncio
async def test_ask_room_needs_a_question_and_says_so():
    result = await invoke("ask_room", {"run_id": "abc"}, read_room=_read_full)
    assert result["isError"] is True
    text = said(result)
    assert "`question`" in text
    assert "did not send it" in text


@pytest.mark.asyncio
async def test_ask_room_costs_nothing_and_its_description_says_which_calls_do():
    """The door's second rule: every description names what a call costs."""
    description = tools._TOOLS_BY_NAME["ask_room"]["description"]
    assert "Costs nothing" in description
    assert "spends no searches" in description


@pytest.mark.asyncio
async def test_ask_room_does_not_rank_on_url_text():
    """Urls are matched-on noise: every wikipedia source shares tokens with
    every other, so scoring them would float whichever finding happens to cite
    the most encyclopaedia pages above the one that answers the question."""

    async def _rooms(uid, run_id):
        return {"status": "complete", "result": {"categories": {"setting": {"findings": [
            {
                "fact": "Nothing to do with the subject at hand.",
                "citations": [{"url": "https://en.wikipedia.org/wiki/Falowiec_mimeograph_duplicator",
                               "title": "Unrelated page", "excerpt": ""}],
                "unverified_urls": [],
            },
            {
                "fact": "The mimeograph duplicator was hand-cranked.",
                "citations": [{"url": "https://example.org/x", "title": "Printing", "excerpt": ""}],
                "unverified_urls": [],
            },
        ]}}}}

    body = carried(await invoke(
        "ask_room",
        {"run_id": "abc", "question": "mimeograph duplicator"},
        read_room=_rooms,
    ))
    assert body["matches"][0]["fact"].startswith("The mimeograph duplicator"), (
        "the finding whose FACT answers the question outranks the one whose "
        "url merely contains the words"
    )


@pytest.mark.asyncio
async def test_the_unknown_tool_refusal_counts_the_tools_it_lists():
    """It said "offers four:" and then listed five, in one sentence.

    The list was generated from the runner map and the number beside it was
    typed, so adding `ask_room` made the refusal contradict itself. Deriving
    both from the same object is the fix; asserting it here is what stops the
    next tool doing it again.
    """
    result = await invoke("nonesuch", {})
    text = said(result)
    assert result["isError"] is True
    assert f"offers {len(tools.TOOLS)}:" in text
    for tool in tools.TOOLS:
        assert f"`{tool['name']}`" in text, f"{tool['name']} should be listed"


def test_the_consent_screen_states_no_tool_count_it_would_have_to_chase():
    """web/consent.js is a different language reading a list defined in Python.

    It used to say "offers four calls here, and none of them deletes...". The
    promise is the load-bearing half; the count was decoration that went stale
    the moment a fifth tool shipped, and no test could have caught it because
    nothing connects the two files. So the number is gone rather than
    corrected — the same call the design campaign made about marks that carry
    a quantifier a payload can contradict.
    """
    repo = Path(__file__).resolve().parent.parent
    consent = (repo / "web" / "consent.js").read_text(encoding="utf-8")
    # Matched within one literal: the sentence is split across a JS `+`, so a
    # pattern spanning the join fails on formatting rather than on meaning.
    #
    # The claim narrowed when delete shipped. "Nothing at this door removes
    # anything" was true of the whole surface and stopped being true; what is
    # true now is scope-shaped — this REQUEST removes nothing, and removing is
    # asked for separately. A promise that outlives the thing it described is
    # worse than no promise, which is why the sentence changed rather than the
    # tool being quietly excused from it.
    assert "Nothing in this request removes anything" in consent
    assert "separate permission" in consent
    for stale in ("offers four", "offers five", "four calls", "five calls"):
        assert stale not in consent, (
            f"'{stale}' is a count of a list that lives in star/mcp/tools.py, "
            "in a file that cannot see it"
        )


# -- delete_room -------------------------------------------------------------
#
# The only call at this door that destroys anything, and the reason it takes two
# is that the web app's arming does not survive translation. A person gets two
# presses and a warning on the page; an agent has no eyes and no pause, so
# "press twice" is just "call twice" and protects nothing. What survives is the
# WARNING: the first call puts what is about to be lost into the agent's
# context, in the department's voice, before it can agree to lose it.


async def _one_room(uid):
    """The account, for delete's first call.

    It now reads the room list to say what continues from the room being
    deleted. One standalone room is what these tests have always assumed, and
    saying so explicitly beats a double that answers whatever it is asked.
    """
    return [{"run_id": "abc", "continues": ""}]


@pytest.mark.asyncio
async def test_the_first_call_destroys_nothing_and_says_what_would_go():
    deleted = []

    async def _delete(uid, run_id):
        deleted.append(run_id)
        return {}

    result = await invoke(
        "delete_room", {"run_id": "abc"}, read_room=_read_full, delete_room=_delete, list_rooms_for=_one_room
    )
    body = carried(result)
    text = said(result)

    assert deleted == [], "the first call must not delete"
    assert body["deleted"] is False
    assert body["confirm"], "and it hands back a token"
    assert "deleted nothing yet" in text
    # What goes, in counts, before agreeing to lose it.
    prose = spoken(result)
    assert "1 findings" in prose and "110 sources" in prose and "17 searches" in prose
    assert str(config.room_retention_days()) in prose, (
        "and when it becomes permanent — in the SENTENCE, not only the payload"
    )


@pytest.mark.asyncio
async def test_the_second_call_with_the_token_deletes():
    calls = []

    async def _delete(uid, run_id):
        calls.append(run_id)
        return {"deleted_at": "2026-08-11T00:00:00+00:00"}

    first = carried(await invoke(
        "delete_room", {"run_id": "abc"}, read_room=_read_full, delete_room=_delete, list_rooms_for=_one_room
    ))
    result = await invoke(
        "delete_room",
        {"run_id": "abc", "confirm": first["confirm"]},
        read_room=_read_full,
        delete_room=_delete,
    )

    assert calls == ["abc"]
    assert carried(result)["deleted"] is True
    assert "recoverable in the web app" in said(result)
    assert "Nothing at this door can bring it back" in said(result), (
        "an agent must be told the restore is not its to make"
    )


@pytest.mark.asyncio
async def test_a_token_works_once():
    async def _delete(uid, run_id):
        return {"deleted_at": "x"}

    first = carried(await invoke(
        "delete_room", {"run_id": "abc"}, read_room=_read_full, delete_room=_delete, list_rooms_for=_one_room
    ))
    args = {"run_id": "abc", "confirm": first["confirm"]}
    await invoke("delete_room", args, read_room=_read_full, delete_room=_delete, list_rooms_for=_one_room)
    replayed = await invoke("delete_room", args, read_room=_read_full, delete_room=_delete, list_rooms_for=_one_room)

    assert replayed["isError"] is True
    assert "works once" in said(replayed)


@pytest.mark.asyncio
async def test_a_token_cannot_be_spent_on_a_different_room():
    """The trap this key shape exists to close: an agent holding a confirmation
    for one room must not be one argument away from deleting another."""
    async def _delete(uid, run_id):
        return {"deleted_at": "x"}

    first = carried(await invoke(
        "delete_room", {"run_id": "abc"}, read_room=_read_full, delete_room=_delete, list_rooms_for=_one_room
    ))
    wrong = await invoke(
        "delete_room",
        {"run_id": "other-room", "confirm": first["confirm"]},
        read_room=_read_full,
        delete_room=_delete,
    )

    assert wrong["isError"] is True
    assert "for the room it was issued against" in said(wrong)


@pytest.mark.asyncio
async def test_an_invented_token_is_refused_with_how_to_get_a_real_one():
    result = await invoke(
        "delete_room",
        {"run_id": "abc", "confirm": "made-up"},
        read_room=_read_full,
        delete_room=_unreachable("delete_room"),
    )
    assert result["isError"] is True
    text = said(result)
    assert "no `confirm`" in text, "say how to start the handshake properly"
    assert "restarts" in text, (
        "and that a restart drops pending confirmations, so an agent retries "
        "the first call rather than hammering the second"
    )


@pytest.mark.asyncio
async def test_deleting_a_room_that_is_not_there_says_so_without_a_token():
    async def _missing(uid, run_id):
        return {"status": "unknown", "result": None}

    result = await invoke(
        "delete_room", {"run_id": "nope"}, read_room=_missing,
        list_rooms_for=_one_room,
        delete_room=_unreachable("delete_room"),
    )
    assert carried(result)["deleted"] is False
    assert "list_rooms" in said(result), "and points at how to get an id that works"


def test_every_tool_is_mapped_to_a_scope():
    """A tool missing from SCOPE_BY_TOOL is not scope-free, it is unfinished.

    star/mcp/router.py skips the check when `scope_for` returns None, so an
    unmapped tool is callable by ANY valid token whatever it was granted.
    `ask_room` shipped that way and nothing noticed until `delete_room` made
    the same omission dangerous. This is the same completeness assertion the
    runner map already gets, for the same reason.
    """
    from star.oauth import validate

    assert set(validate.SCOPE_BY_TOOL) == {tool["name"] for tool in tools.TOOLS}
    assert set(validate.SCOPE_BY_TOOL.values()) <= set(metadata.SCOPES_SUPPORTED)


def test_deleting_needs_its_own_scope_and_writing_does_not_grant_it():
    """Building and deleting are opposite risks. A reader who let an agent
    research for them has said nothing about whether it may clear their
    workspace, and folding delete into rooms:write would infer the second
    consent from the first."""
    from star.oauth import validate

    assert validate.SCOPE_BY_TOOL["delete_room"] == "rooms:delete"
    assert validate.SCOPE_BY_TOOL["build_room"] == "rooms:write"
    assert "rooms:delete" not in metadata.SCOPES_DEFAULT, (
        "and a client that names no scope is not registered for it"
    )


# --- Rooms that follow other rooms -------------------------------------------
#
# THE BUG this closes half of. A story spanning five eras was five unrelated
# rooms, and nothing at either door said they belonged together. The web app now
# lets a writer say which room a room follows; this door reports that link and,
# before a delete, says what leans on the room about to go.
#
# Rooms that follow are NOT deleted with their parent. A room's delete already
# takes its scenes, and extending that to a story's later rooms would let one
# confirmation destroy work the caller never named.


async def _story(uid):
    """Four rooms: a standalone one, and a three-room story."""
    return [
        {"run_id": "alone", "continues": ""},
        {"run_id": "first", "continues": ""},
        {"run_id": "second", "continues": "first"},
        {"run_id": "third", "continues": "second"},
    ]


@pytest.mark.asyncio
async def test_the_delete_warning_counts_the_whole_chain_not_the_first_hop():
    async def _delete(uid, run_id):
        return {}

    result = await invoke(
        "delete_room", {"run_id": "first"}, read_room=_read_full,
        delete_room=_delete, list_rooms_for=_story,
    )

    assert carried(result)["followed_by"] == ["second", "third"]
    assert "2 rooms" in spoken(result)


@pytest.mark.asyncio
async def test_the_warning_says_the_followers_stay():
    """Without that, "2 rooms continue from this one" one call before spending
    a token reads as a warning that two more rooms are about to go."""

    async def _delete(uid, run_id):
        return {}

    result = await invoke(
        "delete_room", {"run_id": "first"}, read_room=_read_full,
        delete_room=_delete, list_rooms_for=_story,
    )
    prose = spoken(result)

    assert "They stay and keep their research" in prose
    assert "no longer filed" in prose


@pytest.mark.asyncio
async def test_one_follower_is_spoken_of_in_the_singular():
    async def _delete(uid, run_id):
        return {}

    result = await invoke(
        "delete_room", {"run_id": "second"}, read_room=_read_full,
        delete_room=_delete, list_rooms_for=_story,
    )
    prose = spoken(result)

    assert "1 room in this account continues" in prose
    assert "It stays and keeps its research" in prose
    assert "What it loses" in prose, "the whole sentence agrees, not half of it"


@pytest.mark.asyncio
async def test_a_room_nothing_follows_says_nothing_about_followers():
    """No empty clause on the common case. A standalone room's delete warning
    should read exactly as it did before this feature existed."""

    async def _delete(uid, run_id):
        return {}

    result = await invoke(
        "delete_room", {"run_id": "alone"}, read_room=_read_full,
        delete_room=_delete, list_rooms_for=_story,
    )

    assert carried(result)["followed_by"] == []
    assert "continue from this one" not in spoken(result)


@pytest.mark.asyncio
async def test_a_ring_in_the_data_does_not_spin_the_delete_warning():
    """The web door refuses to create one and so does nothing else, but data
    written before that guard existed must not hang a delete. A room is also
    never among its own followers, which in a ring it would otherwise reach."""

    async def _ring(uid):
        return [
            {"run_id": "x", "continues": "y"},
            {"run_id": "y", "continues": "x"},
        ]

    async def _delete(uid, run_id):
        return {}

    result = await invoke(
        "delete_room", {"run_id": "x"}, read_room=_read_full,
        delete_room=_delete, list_rooms_for=_ring,
    )

    assert carried(result)["followed_by"] == ["y"]


@pytest.mark.asyncio
async def test_list_rooms_carries_the_link_so_an_agent_can_see_the_shape():
    result = await invoke("list_rooms", list_rooms_for=_story)
    rooms = carried(result)["rooms"]

    assert [room["continues"] for room in rooms] == ["", "", "first", "second"]


def test_the_list_rooms_description_names_the_field_it_returns():
    """A tool description that omits a returned field is a field an agent never
    asks about. The same discipline the README's tool list is pinned under."""
    listed = tools._TOOLS_BY_NAME["list_rooms"]["description"]

    assert "`continues`" in listed
