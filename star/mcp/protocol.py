"""The MCP wire, and nothing else.

Pure by design: no FastAPI, no store, no clock, no network. Every function
here maps a parsed JSON payload or a header string onto a decision, which is
what lets the conformance surface be tested with no server running and no
token issued. `star/findings.py` and `star/verdicts.py` already take this
shape for the same reason.

Two things this module is deliberately strict about, because a transport that
guesses is a transport whose failures arrive as someone else's bug report:

  · `"jsonrpc": "2.0"` is required, and a message without it is refused by
    name rather than assumed. JSON-RPC 2.0 requires the member and every MCP
    client sends it.
  · A request `id` may be a string or an integer and nothing else. MCP adds
    that it MUST NOT be null, which is exactly what separates a request from
    a notification below.

`bool` is a subclass of `int` in Python, so `isinstance(True, int)` is True.
An id of `true` is not a valid JSON-RPC id and the check below says so
explicitly rather than accepting it through that hole.
"""

from dataclasses import dataclass

# The revisions this server will speak. Read from the transport spec rather
# than recalled: 2025-03-26 introduced Streamable HTTP, 2025-06-18 and
# 2025-11-25 are the two revisions after it, and 2026-07-28 is the release
# candidate that removes the handshake altogether. A tools-only server with no
# resources, prompts, sampling, roots, or logging satisfies all four.
SUPPORTED_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")

# What the server names when it is the one choosing: an `initialize` that asks
# for nothing, or one that asks for a revision this server does not speak.
ADVERTISED_VERSION = "2025-11-25"

# What an absent `MCP-Protocol-Version` header means. The transport spec's
# backwards-compatibility rule is explicit that a server SHOULD assume
# 2025-03-26 when the header is missing, because that revision predates the
# header existing at all. Refusing the header's absence would refuse every
# client written against the revision that introduced this transport.
ASSUMED_VERSION = "2025-03-26"

# JSON-RPC 2.0's own codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# JSON-RPC reserves -32000 to -32099 for implementation-defined server errors,
# and MCP defines no code for a transport-level refusal. These three are that
# range used for the three ways this server turns a caller away before any
# method runs. They exist so a client can branch on a number rather than on
# prose, and the HTTP status carries the same fact for a client that cannot.
AUTHORIZATION_REQUIRED = -32001
ORIGIN_REFUSED = -32002
UNSUPPORTED_PROTOCOL_VERSION = -32003


@dataclass(frozen=True)
class Call:
    """A JSON-RPC request: something with an id, which owes an answer."""

    id: object
    method: str
    params: dict


@dataclass(frozen=True)
class Acknowledged:
    """A notification or a response: nothing to answer, and no id to answer to.

    The transport spec is explicit about what this gets — HTTP 202 with no
    body — and it is what `notifications/initialized` receives. Returning a
    JSON-RPC result to a message carrying no id would be a protocol violation
    dressed up as helpfulness.
    """


@dataclass(frozen=True)
class Malformed:
    """A message this server will not try to interpret.

    `id` is echoed when the payload carried a usable one, so a client can join
    the error back to the call it sent. It is None when the payload was too
    broken to have one, which JSON-RPC requires be rendered as a null id.
    """

    code: int
    message: str
    id: object = None


def negotiate_header(header: str | None) -> str | None:
    """The revision an HTTP request is speaking, or None if this server cannot.

    Absent means 2025-03-26, per the backwards-compatibility rule above, and
    that is also the case that matters most in practice: the header is not
    sent on `initialize` itself, because the version has not been agreed yet.
    """
    if header is None:
        return ASSUMED_VERSION
    header = header.strip()
    if not header:
        return ASSUMED_VERSION
    return header if header in SUPPORTED_VERSIONS else None


def negotiate_initialize(requested: object) -> str:
    """The revision the InitializeResult reports.

    spec.md says STAR advertises 2025-11-25, and the transport spec says a
    server MUST answer with the requested revision when it supports it. Both
    hold here and they are not in tension: 2025-11-25 is what this server
    names whenever it is the one choosing — no `protocolVersion` in the
    params, or one this server does not speak — and a supported request is
    honoured because a client that asked for 2025-06-18 and was answered
    2025-11-25 is entitled to disconnect.
    """
    if isinstance(requested, str) and requested in SUPPORTED_VERSIONS:
        return requested
    return ADVERTISED_VERSION


def result(identifier: object, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": identifier, "result": payload}


def error(identifier: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _is_identifier(value: object) -> bool:
    """A JSON-RPC id: a string or an integer, and `true` is neither."""
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _echoable_id(payload: dict) -> object:
    identifier = payload.get("id")
    return identifier if _is_identifier(identifier) else None


def classify(payload: object) -> Call | Acknowledged | Malformed:
    """Decide what a POSTed body is: a call, an acknowledgement, or garbage.

    The three outcomes map onto three HTTP answers and the router does no
    further reading of the body, so every rule about the shape of a JSON-RPC
    message lives here rather than being spread across the edge.
    """
    if isinstance(payload, list):
        return _classify_batch(payload)
    return _classify_one(payload)


def _classify_one(payload: object) -> Call | Acknowledged | Malformed:
    if not isinstance(payload, dict):
        return Malformed(
            INVALID_REQUEST,
            "A JSON-RPC message must be a JSON object. Send "
            '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"} or similar.',
        )
    if payload.get("jsonrpc") != "2.0":
        return Malformed(
            INVALID_REQUEST,
            'Every message must carry "jsonrpc": "2.0". This one did not.',
            _echoable_id(payload),
        )

    method = payload.get("method")
    if method is None:
        # No method and one of the two members a response must carry is a
        # response to something this server sent. It sends nothing, so there
        # is nothing to correlate — but it is a well-formed message and the
        # transport spec's answer to it is 202, not an error.
        if "result" in payload or "error" in payload:
            return Acknowledged()
        return Malformed(
            INVALID_REQUEST,
            "A JSON-RPC message must carry either a method, or a result or "
            "error in reply to one. This one carried neither.",
            _echoable_id(payload),
        )
    if not isinstance(method, str) or not method:
        return Malformed(
            INVALID_REQUEST,
            "`method` must be a non-empty string.",
            _echoable_id(payload),
        )

    identifier = payload.get("id")
    if identifier is None:
        # A notification. MCP forbids a null id on a request, so an explicit
        # null and an absent id are the same message and get the same answer.
        return Acknowledged()
    if not _is_identifier(identifier):
        return Malformed(
            INVALID_REQUEST,
            "`id` must be a string or an integer.",
        )

    params = payload.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        # JSON-RPC 2.0 allows positional params as an array; MCP does not, and
        # every tool argument in this server is named. Refusing is honest,
        # because accepting an array would mean guessing an order.
        return Malformed(
            INVALID_PARAMS,
            "`params` must be a JSON object. This server takes named "
            "arguments only.",
            identifier,
        )
    return Call(identifier, method, params)


def _classify_batch(payload: list) -> Acknowledged | Malformed:
    """A JSON-RPC batch, which this server answers in exactly one case.

    Batching was removed in 2025-11-25, the revision this server advertises,
    so a batch carrying anything that owes an answer is refused with the
    reason named. A batch made entirely of notifications or responses is
    accepted anyway: it owes no answer either way, a client written against
    2025-03-26 may legitimately send one, and 202 is already the answer each
    of its members would get on its own. Accepting it costs nothing and
    refusing it would break a client over a distinction it cannot observe.
    """
    if not payload:
        return Malformed(INVALID_REQUEST, "An empty batch carries no message.")
    if all(isinstance(_classify_one(item), Acknowledged) for item in payload):
        return Acknowledged()
    return Malformed(
        INVALID_REQUEST,
        "JSON-RPC batching was removed in the 2025-11-25 revision this server "
        "speaks. Send one request per POST.",
    )


def normalise_origin(origin: str) -> str:
    """Fold an Origin down to what a comparison should turn on.

    Scheme and host are case-insensitive per RFC 6454, and a trailing slash is
    not part of an origin at all, so neither may decide whether a caller is
    refused. Nothing else is normalised: a port is part of the origin, and
    http:// and https:// are different origins.
    """
    return origin.strip().rstrip("/").lower()


def origin_allowed(origin: str | None, allowed) -> bool:
    """Is this Origin one this server answers to?

    An ABSENT header passes, and that is the load-bearing case rather than a
    loophole. Origin validation exists to stop a page in a browser from
    driving a local MCP server through DNS rebinding; a browser always sends
    the header, and a desktop agent, a script, or curl never does. Refusing an
    absent Origin would refuse every non-browser client, which is every client
    this door was built for.

    `Origin: null` is what a browser sends from an opaque origin — a sandboxed
    iframe, a data: URL. It arrives here as the literal string "null", matches
    nothing in the allow list, and is refused, which is correct.
    """
    if origin is None:
        return True
    return normalise_origin(origin) in {normalise_origin(one) for one in allowed}
