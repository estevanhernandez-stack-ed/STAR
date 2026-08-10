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

The four tools are the next item's. `TOOLS` is empty here on purpose, so
`tools/list` returns an empty list and `tools/call` answers as an unknown
tool — both of which are real behaviours with real assertions, not stubs.
"""

import contextlib
import json
import tomllib
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from star import config, server, tokens
from star.guards import DailyCap, RateLimiter
from star.mcp import protocol, tools
from star.store import TokenStore
from tests.test_server import _FakeRequest
from tests.test_store import _FakeClient

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
async def test_tools_list_answers_with_the_surface_this_item_has_not_filled_yet():
    """Empty is a real answer, not a stub. The next item fills `TOOLS`; what
    this pins is that the envelope, the key, and the shape are already right,
    so the only thing that changes is the contents."""
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
    assert response.headers["www-authenticate"] == "Bearer"
    assert body["error"]["code"] == protocol.AUTHORIZATION_REQUIRED
    assert body["error"]["message"] == tokens.MISSING.message


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
