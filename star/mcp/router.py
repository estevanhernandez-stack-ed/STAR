"""The HTTP edge of the agent door.

One endpoint, `/mcp`, on the app that already serves the browser. Not a second
service: `_runs`, `_ip_limiter`, `_uid_limiter`, and `_daily_cap` are
module-level in-memory state in star/server.py, and star/guards.py's module
docstring records exactly what a second process does to all four. A router is
the whole of what this needs to be.

Everything transport-shaped lives here and everything else is injected.
`build_mcp_router` takes five callables and holds no state of its own beyond
them, so a test can drive the wire contract without a store, a runner, or a
token, and the tools reach the same function objects the browser's handlers do.

The order of the checks below is the argument this file is really making, and
it runs free-to-answer first:

  1. Origin, a header comparison against a list held in memory.
  2. Bearer auth, which costs one Firestore read.
  3. MCP-Protocol-Version, a set membership test.
  4. Reading the body at all.

Auth sits ahead of every line that touches the body, which is the rule that
binds: no JSON-RPC is parsed for an unauthenticated caller, `initialize`
included, and there is no unauthenticated handshake. It sits BEHIND the Origin
check on purpose, for the reason star/tokens.py's `parse` gives for checking a
token's shape before asking the store anything — a caller this endpoint is
never going to answer should not be able to make it do database work on the
way to being refused.
"""

import json
import logging
from collections.abc import Callable
from importlib import metadata
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from star import config
from star.mcp import protocol, tools

# Aliased on purpose. `metadata` is already taken at the top of this file by
# `importlib.metadata`, which is what reads the package version for serverInfo,
# and a second unqualified `metadata` here would silently shadow it.
from star.oauth import metadata as oauth_metadata
from star.oauth import validate as oauth_validate
from star.tokens import TokenIdentity

logger = logging.getLogger(__name__)

SERVER_NAME = "star"

try:
    SERVER_VERSION = metadata.version("star")
except metadata.PackageNotFoundError:  # a source checkout with nothing installed
    # Not "0.1.0". Guessing the version from a checkout that cannot report one
    # would put a number on the wire that nothing behind it supports, and an
    # agent reading serverInfo to decide what it is talking to deserves the
    # honest answer instead.
    SERVER_VERSION = "unknown"

# What the department looks like in a client's own chrome.
#
# `Implementation` extends `BaseMetadata` and `Icons` in the 2025-11-25 schema,
# so `serverInfo` carries `title`, `description`, `websiteUrl` and `icons` — and
# STAR was sending two of the seven fields, a bare name and a version.
#
# The cost of that silence was visible rather than theoretical. A connector card
# for `star.626labs.dev` showed 626 Labs' own mark, because a client with no
# icon to use falls back to guessing from the registrable domain: it resolves
# `626labs.dev`, reads that site's `<link rel="icon">`, and renders
# `favicon-626.png`. Serving `/favicon.ico` on this origin does not reach that
# path at all, since the client never asks this origin. The protocol has a field
# for exactly this, and filling it is the only standards-shaped answer available.
#
# Both formats are offered, widest support first. `sizes: ["any"]` on the SVG is
# how a scalable icon declares itself under the same rules a web app manifest
# uses; the ICO enumerates what it actually contains rather than claiming more.
_ICON_BASE = "https://star.626labs.dev"
SERVER_ICONS = (
    {
        "src": f"{_ICON_BASE}/favicon.svg",
        "mimeType": "image/svg+xml",
        "sizes": ["any"],
    },
    {
        "src": f"{_ICON_BASE}/favicon.ico",
        "mimeType": "image/vnd.microsoft.icon",
        "sizes": ["16x16", "32x32", "48x48", "64x64", "128x128", "256x256"],
    },
)

# `title` is the display name, distinct from `name`, which is the identifier a
# client keys on. The description is one sentence because a card has one line.
SERVER_TITLE = "STAR"
SERVER_DESCRIPTION = (
    "A research department for screenwriters. Builds cited research rooms from "
    "a treatment, and checks a scene's real-world claims against one."
)
SERVER_WEBSITE = _ICON_BASE

# The methods a tools-only server owes an answer to. `notifications/initialized`
# is absent because it is a notification: it carries no id, so it never reaches
# dispatch at all — it is answered with 202 several steps earlier.
_HANDLED = ("initialize", "ping", "tools/list", "tools/call")


def _error_response(
    status: int, identifier: object, code: int, message: str, headers: dict | None = None
) -> JSONResponse:
    """A refusal that is both an HTTP status and a JSON-RPC error object.

    Both, not one or the other. A client that only reads statuses gets a
    number it can act on; a client that only reads bodies gets a sentence
    naming what failed and what to do next, which is the bar `prd.md` sets for
    every refusal on this surface.
    """
    return JSONResponse(
        protocol.error(identifier, code, message),
        status_code=status,
        headers=headers or {},
    )


def build_mcp_router(
    *,
    start_build: Callable[..., Any],
    read_room: Callable[..., Any],
    list_rooms_for: Callable[..., Any],
    run_check: Callable[..., Any],
    delete_room: Callable[..., Any],
    run_requisition: Callable[..., Any],
    run_sweep: Callable[..., Any],
    read_sweeps: Callable[..., Any],
    read_sweep: Callable[..., Any],
    export_room: Callable[..., Any],
    import_rooms: Callable[..., Any],
    write_bible: Callable[..., Any],
    link_room: Callable[..., Any],
    resolve_token: Callable[..., Any],
) -> APIRouter:
    """Wire the agent door onto the server's own functions and a token resolver.

    Called from star/server.py BEFORE `app.mount("/")`. The StaticFiles mount
    matches every path under `/`, so a router included after it never sees a
    request — `/mcp` would come back as a 404 from the static handler with
    nothing in the log to say why.
    """
    router = APIRouter()
    calls = tools.Calls(
        start_build=start_build,
        read_room=read_room,
        list_rooms_for=list_rooms_for,
        run_check=run_check,
        delete_room=delete_room,
        run_requisition=run_requisition,
        run_sweep=run_sweep,
        read_sweeps=read_sweeps,
        read_sweep=read_sweep,
        export_room=export_room,
        import_rooms=import_rooms,
        write_bible=write_bible,
        link_room=link_room,
    )

    async def _dispatch(message: protocol.Call, identity: TokenIdentity) -> dict:
        """Answer one JSON-RPC request. Never raises past its own except."""
        if message.method == "initialize":
            return protocol.result(
                message.id,
                {
                    "protocolVersion": protocol.negotiate_initialize(
                        message.params.get("protocolVersion")
                    ),
                    # Tools and nothing else. Declaring a capability this
                    # server does not serve is how a client ends up calling
                    # `resources/list` and getting -32601 for a method its
                    # handshake was told to expect.
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "title": SERVER_TITLE,
                        "version": SERVER_VERSION,
                        "description": SERVER_DESCRIPTION,
                        "websiteUrl": SERVER_WEBSITE,
                        "icons": list(SERVER_ICONS),
                    },
                    "instructions": tools.INSTRUCTIONS,
                },
            )
        if message.method == "ping":
            return protocol.result(message.id, {})
        if message.method == "tools/list":
            # No `nextCursor`. Pagination is optional and this surface is one
            # page; omitting the field is what tells a client there is no
            # second page, where an empty string would ask it for one.
            return protocol.result(message.id, {"tools": list(tools.TOOLS)})
        if message.method == "tools/call":
            name = message.params.get("name")
            if not isinstance(name, str) or not name:
                return protocol.error(
                    message.id,
                    protocol.INVALID_PARAMS,
                    "tools/call needs a `name`. Call tools/list for the names "
                    "this department answers to.",
                )
            arguments = message.params.get("arguments")
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                return protocol.error(
                    message.id,
                    protocol.INVALID_PARAMS,
                    "`arguments` must be a JSON object of named values.",
                )
            try:
                return protocol.result(
                    message.id, await tools.call(name, arguments, calls, identity)
                )
            except Exception:
                # Same posture as star/server.py's `_execute` and `_run_check`:
                # the detail goes to the server log and the caller gets plain
                # language with none of our vocabulary in it. This endpoint is
                # public, and an exception string has already handed a stranger
                # library names, table names, and a stray credential once in
                # this project's life.
                logger.exception("MCP tool %s failed", name)
                return protocol.error(
                    message.id,
                    protocol.INTERNAL_ERROR,
                    "The department hit an unexpected problem running that "
                    "tool. The details are in the server log.",
                )
        return protocol.error(
            message.id,
            protocol.METHOD_NOT_FOUND,
            f"This server does not implement {message.method!r}. It offers "
            f"{', '.join(_HANDLED)}, and notifications/initialized.",
        )

    @router.post("/mcp", include_in_schema=False)
    async def mcp_post(
        request: Request,
        authorization: str | None = Header(None),
        origin: str | None = Header(None),
        mcp_protocol_version: str | None = Header(None, alias="MCP-Protocol-Version"),
    ) -> Response:
        """The whole agent door. See this module's docstring for the order."""
        if not protocol.origin_allowed(origin, config.mcp_allowed_origins()):
            return _error_response(
                403,
                None,
                protocol.ORIGIN_REFUSED,
                "This server does not answer requests from that origin. A "
                "non-browser client should send no Origin header at all.",
            )

        identity = await resolve_token(authorization)
        if not isinstance(identity, TokenIdentity):
            # `identity` is one of star/tokens.py's three Refusals, and only
            # its message is read. Branching on `.reason` here would let the
            # router draw a distinction the strings deliberately refuse to
            # draw: a token of the wrong shape, an unknown id, and a wrong
            # secret are one answer, because telling a stranger which of them
            # they sent is free reconnaissance into which token ids are real.
            #
            # The challenge now carries `resource_metadata`. It used to be a
            # bare `Bearer`, and the comment here said pointing at metadata
            # that did not exist would be worse than saying nothing. That was
            # true and it is not any more: RFC 9728 metadata is served, so the
            # parameter is the one thing that turns this refusal from a dead
            # end into the first step of a flow a client can actually finish.
            return _error_response(
                401,
                None,
                protocol.AUTHORIZATION_REQUIRED,
                identity.message,
                headers={"WWW-Authenticate": oauth_metadata.www_authenticate()},
            )

        # A resolved credential is not yet an admitted one. `resolve_token`
        # answers "is this real and unrevoked", which is all a card token has
        # ever needed. An OAuth access token additionally has to be unexpired,
        # issued for THIS resource, and not a refresh token wearing a bearer
        # header. `validate.check` is where those three are asked, and it is
        # deliberately a second call rather than folded into resolution: the
        # card path must keep answering exactly as it did, and it does, because
        # a token carrying no OAuth facts passes every one of these by
        # construction.
        #
        # Scope is NOT checked here. The scope a call needs depends on which
        # tool it names, and the door has not read the body yet — reading it to
        # find out would put parsing ahead of authentication, which is the one
        # ordering this router exists to hold. `tools/call` asks below.
        admitted = oauth_validate.check(identity)
        if isinstance(admitted, oauth_validate.Denied):
            return _error_response(
                admitted.status,
                None,
                protocol.AUTHORIZATION_REQUIRED,
                admitted.description,
                headers={"WWW-Authenticate": admitted.challenge()},
            )

        version = protocol.negotiate_header(mcp_protocol_version)
        if version is None:
            return _error_response(
                400,
                None,
                protocol.UNSUPPORTED_PROTOCOL_VERSION,
                f"This server does not speak MCP revision "
                f"{mcp_protocol_version!r}. It speaks "
                f"{', '.join(protocol.SUPPORTED_VERSIONS)}.",
            )

        try:
            payload = json.loads(await request.body())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error_response(
                400,
                None,
                protocol.PARSE_ERROR,
                "The request body was not JSON.",
            )

        message = protocol.classify(payload)
        if isinstance(message, protocol.Acknowledged):
            # 202 with NO body, which is what the transport spec requires for
            # a POSTed notification or response and what
            # `notifications/initialized` gets. A 200 carrying a result would
            # be answering a message that has no id to answer to.
            return Response(status_code=202)
        if isinstance(message, protocol.Malformed):
            return _error_response(400, message.id, message.code, message.message)

        # Scope, and only now, because only now is the tool name known. The
        # door admitted this credential; this asks whether the grant behind it
        # covers what is being asked for.
        #
        # It is an HTTP 403 with a challenge rather than a CallToolResult, and
        # that is the whole point of putting it here. `isError: true` is the
        # right shape for a failure the calling MODEL should read and act on;
        # insufficient scope is a failure the CLIENT acts on, by running a
        # step-up authorization for the scope named in the challenge. A model
        # cannot do that, and a tool result carries no `WWW-Authenticate` to
        # tell it what to ask for. Getting this shape wrong would leave a
        # client re-reading an apology instead of upgrading its grant.
        if message.method == "tools/call":
            asked = message.params.get("name")
            need = oauth_validate.scope_for(asked) if isinstance(asked, str) else None
            if need is not None:
                scoped = oauth_validate.check(identity, need=need)
                if isinstance(scoped, oauth_validate.Denied):
                    return _error_response(
                        scoped.status,
                        message.id,
                        protocol.AUTHORIZATION_REQUIRED,
                        scoped.description,
                        headers={"WWW-Authenticate": scoped.challenge()},
                    )

        return JSONResponse(await _dispatch(message, identity))

    @router.get("/mcp", include_in_schema=False)
    async def mcp_get() -> Response:
        """405, which the transport spec names as correct here.

        The GET is how a client opens a server-initiated SSE stream. This
        server initiates nothing: every answer it has belongs to the POST that
        asked for it, and the one long operation it offers is polled through
        `get_room` rather than pushed. The spec's words for a server that does
        not offer the stream are that it MUST return 405, so this is
        conformance rather than an unimplemented corner.
        """
        return _error_response(
            405,
            None,
            protocol.INVALID_REQUEST,
            "This server offers no server-initiated event stream, so GET /mcp "
            "has nothing to open. Send JSON-RPC requests as POST /mcp.",
            headers={"Allow": "POST"},
        )

    @router.delete("/mcp", include_in_schema=False)
    async def mcp_delete() -> Response:
        """405, for the same reason and by the same rule.

        DELETE is how a client ends a session. This server issues no
        `Mcp-Session-Id` and requires none — it is stateless per request,
        which the transport spec makes explicitly optional and which the
        2026-07-28 release candidate assumes outright. There is no session to
        terminate, and the spec names 405 as the answer.
        """
        return _error_response(
            405,
            None,
            protocol.INVALID_REQUEST,
            "This server issues no session id and holds no session, so there "
            "is nothing to terminate. Send JSON-RPC requests as POST /mcp.",
            headers={"Allow": "POST"},
        )

    return router
