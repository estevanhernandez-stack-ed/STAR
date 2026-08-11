"""The two discovery documents, as data.

A client that begins by asking "where is your authorization server?" reads
these two documents and nothing else, so what they contain IS the connection
handshake. Both are pure dicts built from one string, the canonical resource
URI, which means a test can assert the whole discovery surface without a server
and a redeploy to another hostname moves both documents at once.

The one field a client is entitled to hang up over is
`code_challenge_methods_supported`. OAuth 2.1 requires PKCE and the MCP
authorization spec says a client MUST refuse to proceed when the AS metadata
does not advertise it, so its absence is not a missing nicety, it is a
connection that never starts. It is a literal tuple here rather than a value
derived from anything, and star/oauth/pkce.py refuses every method not in it.

WHERE THE RESOURCE IDENTIFIER POINTS, AND THE AMBIGUITY THAT LEAVES. RFC 9728
derives the metadata URL from the resource identifier, so
`https://star.626labs.dev` puts this document at
`/.well-known/oauth-protected-resource` and `https://star.626labs.dev/mcp`
would put it at `/.well-known/oauth-protected-resource/mcp` instead.
`spec-oauth-as.md > Endpoints` names the first path and the 401 challenge it
quotes carries the first URL, so the resource identifier is the origin with no
path. The cost, stated because it is real: the MCP authorization spec's own
examples use the MCP endpoint's full URI as the resource, so a client that
builds the metadata URL by appending the resource's path will ask for
`/.well-known/oauth-protected-resource/mcp` and get a 404 from the static
mount. Registering that path as an alias of this one is a one-line change in
whoever wires the routes, and it is the change to make if a real client
misses.
"""

from urllib.parse import urlsplit, urlunsplit

from star import config

# The two scopes, and `spec-oauth-as.md`'s Decision 4 is what makes them two
# rather than one: `rooms:read` covers list_rooms and get_room, `rooms:write`
# covers build_room and check_scene, which is the free-versus-spends split
# every tool description in star/mcp/tools.py already states. A consent screen
# can then say something true and specific instead of asking for everything.
SCOPES_SUPPORTED = ("rooms:read", "rooms:write")

# Space-delimited, which is how a scope set travels in every OAuth message.
SCOPE_SEPARATOR = " "

PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"
AUTHORIZE_PATH = "/oauth/authorize"
TOKEN_PATH = "/oauth/token"
REGISTER_PATH = "/oauth/register"

# What a bearer token may arrive in. Header only: this server reads
# `Authorization` and nothing else, and advertising a form or query method it
# does not implement would send a client down a path that 401s. A token in a
# query string also lands in access logs and referrers, which is why RFC 6750
# discourages it and why it is absent here rather than merely unimplemented.
BEARER_METHODS_SUPPORTED = ("header",)


def _default_port(scheme: str) -> str:
    return {"https": "443", "http": "80"}.get(scheme, "")


def canonical(uri: object) -> str:
    """Fold a resource URI down to what an audience comparison turns on.

    RFC 8707 calls for the canonical URI of the resource, and three differences
    between two spellings of one resource are not differences a token should be
    refused over: the scheme and host are case-insensitive, an explicit default
    port means the same thing as no port, and a trailing slash on an empty path
    is not a path. Everything else is preserved, and that is the deliberate
    half: `https://star.626labs.dev/mcp` stays distinct from
    `https://star.626labs.dev`, because a resource identifier with a path is a
    different resource and folding them together would widen what a token is
    valid for.

    A fragment makes the whole value unusable rather than being stripped. RFC
    8707 forbids one outright, and a client that sent one is asking about a
    resource that does not exist; answering as though it had asked about the
    one without it is guessing on the caller's behalf.

    Returns "" for anything unparseable, which star/oauth/validate.py compares
    against nothing and refuses.
    """
    if not isinstance(uri, str) or not uri.strip():
        return ""
    parts = urlsplit(uri.strip())
    if parts.fragment or not parts.scheme or not parts.hostname:
        return ""
    host = parts.hostname.lower()
    port = parts.port
    scheme = parts.scheme.lower()
    if port is not None and str(port) != _default_port(scheme):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, host, path, parts.query, ""))


def resource() -> str:
    """The canonical resource identifier this deployment answers as."""
    return canonical(config.canonical_resource())


def issuer() -> str:
    """The authorization server's identifier.

    Identical to the resource identifier, because `spec-oauth-as.md` puts both
    roles on one deployment: STAR cannot delegate the AS role to Google, since
    the spec requires validating that a token was issued FOR STAR and Google
    will not mint a token carrying STAR's canonical URI as its audience. One
    string for both is not a shortcut, it is the deployment.
    """
    return resource()


def accepts_resource(requested: object) -> bool:
    """Is this `resource` parameter something this server can mint a token for?

    RFC 8707 binds a token to the resource the client named, and the MCP
    authorization spec makes sending it a MUST. There is exactly one resource
    here, so this is a comparison rather than a lookup.

    An ABSENT resource is accepted, which is looser than the MCP spec's MUST
    and is a deliberate call rather than an oversight. A client that omits it
    is asking for a token from a server that serves one resource, so there is
    no ambiguity to resolve and nothing to guess: it gets a token bound to the
    only thing the parameter could have said. Refusing it would turn a
    conformance detail into a connection that never starts, and the audience
    the token carries is identical either way.
    """
    if requested is None or requested == "":
        return True
    return canonical(requested) == resource()


def _url(path: str, base: str | None = None) -> str:
    return f"{base or resource()}{path}"


def resource_metadata_url(base: str | None = None) -> str:
    """The URL the 401 challenge points at. See this module's docstring."""
    return _url(PROTECTED_RESOURCE_PATH, base)


def protected_resource(base: str | None = None) -> dict:
    """RFC 9728. What this resource is, and who issues tokens for it.

    Four fields and no more. `authorization_servers` is a list carrying one
    entry, which is the shape the RFC defines even when the two roles are the
    same deployment; collapsing it to a string is the kind of helpful deviation
    a client's parser refuses.
    """
    here = canonical(base) if base else resource()
    return {
        "resource": here,
        "authorization_servers": [here],
        "scopes_supported": list(SCOPES_SUPPORTED),
        "bearer_methods_supported": list(BEARER_METHODS_SUPPORTED),
    }


def authorization_server(base: str | None = None) -> dict:
    """RFC 8414. Every endpoint and every capability, as one document.

    `token_endpoint_auth_methods_supported: ["none"]` is the whole client model
    stated in one field: every client here is public. A desktop MCP client
    cannot keep a secret — it ships to a laptop — so issuing one would be
    theatre, and OAuth 2.1 already answers the question a secret used to answer
    with PKCE plus refresh rotation. Advertising `client_secret_post` and then
    ignoring the secret would be worse than not offering it.

    `client_id_metadata_document_supported` is not in RFC 8414's registry; it
    is the flag the Client ID Metadata Documents draft defines, and the MCP
    authorization spec's client priority puts CIMD ahead of dynamic
    registration. Both are offered because `spec-oauth-as.md`'s Decision 3 says
    guessing which one a real desktop client reaches for is more expensive than
    building both.
    """
    here = canonical(base) if base else issuer()
    return {
        "issuer": here,
        "authorization_endpoint": _url(AUTHORIZE_PATH, here),
        "token_endpoint": _url(TOKEN_PATH, here),
        "registration_endpoint": _url(REGISTER_PATH, here),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        # Never "plain". See star/oauth/pkce.py, which refuses it at the
        # verification end so this list and the behaviour cannot drift.
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": list(SCOPES_SUPPORTED),
        "token_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
    }


def _quotable(value: object) -> str:
    """One `auth-param` value, safe to put between quotes in a header.

    Three things happen here and all three are required rather than tidy. A
    newline or carriage return in a response header is response splitting, so
    every control character is dropped. A bare `"` would end the quoted string
    early and a bare backslash would escape whatever followed it, so both are
    escaped. And the result is bounded, because one of the strings that reaches
    this is a refusal message and a header is not where a paragraph belongs.

    The values passed in today are this project's own constants, so none of
    this is reachable from a caller's bytes. It is here because that is a fact
    about today's call sites rather than a property of the function, and
    star/auth.py's `_failure_detail` records what it cost to learn the
    difference.
    """
    text = " ".join(str(value).split())
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text[:300]
    # The truncation can land in the middle of an escape pair and leave a lone
    # trailing backslash, which would then escape the closing quote and hand
    # the rest of the header to the parser as auth-params. An odd number of
    # trailing backslashes is exactly that case; dropping one costs a character
    # off a message that was already being cut.
    if (len(text) - len(text.rstrip("\\"))) % 2:
        text = text[:-1]
    return text


def www_authenticate(
    *,
    error: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    base: str | None = None,
) -> str:
    """The `WWW-Authenticate` header a refused MCP call carries.

    `resource_metadata` is the parameter this whole epic exists to add. RFC
    9728 §5.1 makes it one of the two ways a client discovers where to
    authenticate, and star/mcp/router.py's current bare `Bearer` challenge is
    why a discovery-first client has nothing to follow today.

    `error` is omitted when nothing was presented. RFC 6750 is explicit that a
    challenge answering a request that carried no credential SHOULD NOT carry
    an error code — the absence is what tells a client "you have not tried
    yet", where `invalid_token` tells it "what you sent is dead" and sends a
    client that has never authenticated into a token-refresh loop.
    """
    parts = [f'Bearer resource_metadata="{resource_metadata_url(base)}"']
    if error:
        parts.append(f'error="{_quotable(error)}"')
    if description:
        parts.append(f'error_description="{_quotable(description)}"')
    if scope:
        parts.append(f'scope="{_quotable(scope)}"')
    return ", ".join(parts)
