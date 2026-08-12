"""Client registration by both routes, and the guard that makes one of them safe.

`spec-oauth-as.md`'s Decision 3 builds both because guessing which one a real
desktop client reaches for is more expensive than building both and measuring
afterwards. Dynamic Client Registration is one endpoint and a validator. Client
ID Metadata Documents is an HTTPS fetch plus a check that the document's own
`client_id` matches the URL it was fetched from.

THE FETCH IS THE DANGEROUS PART OF THIS ENTIRE EPIC, AND IT IS DANGEROUS FOR
ONE REASON: a stranger with no credential picks the URL, and this server makes
the request. That is a server-side request forgery primitive by construction,
aimed from inside the deployment's own network at whatever answers there. On
Cloud Run the thing that answers there is the metadata server at
169.254.169.254, which hands out access tokens for the service account.

So `safe_https_url` below is a separate function with its own refusals and its
own tests, rather than a few lines inside the fetch. Everything it refuses:

  · a scheme that is not `https`
  · a port other than 443
  · credentials embedded in the URL, or a fragment
  · a hostname that resolves to nothing
  · ANY resolved address that is loopback, private, link-local, multicast,
    reserved, or unspecified, in IPv4 or IPv6
  · an IPv4-mapped, 6to4, or Teredo IPv6 address, which are three ways to
    write an IPv4 address that a naive v6 check waves through
  · every address a hostname resolves to, not just the first, because a
    round-robin answer carrying one public and one private address is one
    connection away from the private one

and the fetch on top of it caps the body, caps wall-clock time across all hops,
refuses to follow more than three redirects, and re-runs the whole guard on
every hop's target rather than trusting the first.

THE RESIDUAL RISK, NAMED RATHER THAN PAPERED OVER. Between this module
resolving a hostname and urllib resolving it again to open the socket, the
answer can change — DNS rebinding, and the attacker owns the TTL. Closing it
means pinning the checked address and carrying the hostname through TLS as
`server_hostname`, which is a hand-built `http.client` connection this file
deliberately does not have. What stands in the gap is that the scheme is
forced to https: a rebind target has to present a certificate valid for the
attacker's own hostname, and an internal service or a metadata endpoint does
not. That is a real barrier and it is not the same thing as a closed window.
"""

import asyncio
import ipaddress
import json
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from star.oauth import metadata

# --- Limits, deliberately not env vars --------------------------------------
#
# star/config.py holds the knobs an operator is meant to turn. These are not
# knobs. Every one of them is the ceiling on somebody else's ability to make
# this server do work, and a ceiling that can be raised by setting an
# environment variable is a ceiling that gets raised the first time a fetch
# fails for an unrelated reason.

# A client metadata document is a dozen fields. 64 KB is two orders of
# magnitude of headroom and still small enough that a hostile server streaming
# forever is cut off before it costs anything.
MAX_DOCUMENT_BYTES = 64 * 1024

# Per hop. A CIMD host that cannot answer in five seconds is a host this
# server should not be holding a thread for.
FETCH_TIMEOUT_SECONDS = 5.0

# Across every hop together, because three hops at the per-hop ceiling is
# fifteen seconds and a per-hop timeout alone bounds nothing that matters.
TOTAL_DEADLINE_SECONDS = 10.0

# Enough for a host that redirects apex to www and http-to-https once. Every
# hop is re-checked by the full guard.
MAX_REDIRECTS = 3

# 443 and nothing else. The address checks below already block the internal
# ranges, so this is the narrower thing it looks like: it removes the ability
# to point this server at an arbitrary port on a PUBLIC host and learn from the
# timing whether something was listening. The cost is that a client publishing
# its metadata document on a non-default port is refused, which is a shape
# nobody has been observed using and a one-line change if anybody is.
_ALLOWED_PORT = 443

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Named so a CIMD host's log says who called and why. No version: this string
# is stable and a version here would be a third place a release has to touch.
_USER_AGENT = "star-oauth-as (+https://star.626labs.dev)"

# --- Refusals ---------------------------------------------------------------

NOT_A_URL = "not_a_url"
BAD_SCHEME = "scheme"
BAD_PORT = "port"
USERINFO = "userinfo"
FRAGMENT = "fragment"
NO_HOST = "no_host"
UNRESOLVABLE = "unresolvable"
TOO_MANY_REDIRECTS = "too_many_redirects"
NO_LOCATION = "redirect_without_location"
TOO_LARGE = "too_large"
DEADLINE = "deadline"
TRANSPORT = "transport"
NOT_JSON = "not_json"

# RFC 7591's two registration error codes, which are also the two a CIMD
# document can fail with. One code per shape of failure, and the description
# carries the specifics — the client that reads this is a program being
# configured by a person, so the sentence has to be actionable.
INVALID_REDIRECT_URI = "invalid_redirect_uri"
INVALID_CLIENT_METADATA = "invalid_client_metadata"

# The hosts a loopback redirect URI may name. Compared exactly, never by
# suffix: `localhost.attacker.example` and `127.0.0.1.attacker.example` are
# ordinary public hostnames that a `endswith` check would admit.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_DCR_CLIENT_PREFIX = "star_client_"

SUPPORTED_GRANT_TYPES = frozenset({"authorization_code", "refresh_token"})
SUPPORTED_RESPONSE_TYPES = frozenset({"code"})


@dataclass(frozen=True)
class Unsafe:
    """A URL this server will not fetch, and the short reason for the log.

    The reason never reaches the caller who supplied the URL. A stranger who
    learns that their URL was refused for `address:private` rather than for
    `unresolvable` has been told something about this deployment's network,
    which is the reconnaissance the whole guard exists to prevent.
    """

    reason: str


@dataclass(frozen=True)
class Safe:
    """A URL that passed every check, with what it resolved to at the time."""

    url: str
    host: str
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class Fetched:
    """One client metadata document, and the URL it finally came from."""

    url: str
    document: dict


@dataclass(frozen=True)
class Client:
    """One client this server is willing to run a flow for.

    `source` is kept because the consent screen and the log both care which
    route produced this. A CIMD client's identity is a URL somebody else
    controls and is re-read on every authorization; a DCR client's identity is
    a row this server wrote once. Those are different trust stories and
    collapsing them into one type without a label would hide that.
    """

    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]
    scope: str
    source: str
    registered_at: str = ""


@dataclass(frozen=True)
class Rejected:
    """A registration or a lookup that produced no client. `error` is RFC 7591's."""

    error: str
    description: str


# --- Redirect URIs ----------------------------------------------------------


def redirect_uri_refusal(uri: object) -> str:
    """Why this redirect URI is not acceptable, or "" when it is.

    `spec-oauth-as.md`'s Communication Security line: HTTPS, or a loopback
    address. Both halves matter and the second is the one with a trap in it.

    LOOPBACK IS ALLOWED OVER HTTP BECAUSE IT HAS TO BE. A native client
    receives its redirect on `http://127.0.0.1:<ephemeral port>` — RFC 8252's
    loopback flow — and there is no certificate for 127.0.0.1 to serve. The
    port is deliberately not constrained for the same RFC's reason: the client
    binds whatever the operating system gives it, so a fixed port would refuse
    every second launch.

    AND THAT IS EXACTLY THE HOLE THE CONSENT SCREEN HAS TO COVER. Any client
    can claim another client's metadata URL and bind a loopback port, and the
    reader sees the legitimate client's name over an attacker's listener. The
    hostname is the only thing that distinguishes them, which is why
    `spec-oauth-as.md > The consent screen` requires it displayed plainly
    rather than summarised. Nothing this function can check would substitute
    for that.

    Refused in every case: a fragment, which RFC 6749 forbids on a redirect
    URI; credentials in the authority, which would be sent to whoever answers;
    a private-use scheme like `myapp://`, which RFC 8252 permits for native
    apps and the STAR spec's MUST does not. That last one is a real cost and it
    is a judgment call rather than a reading — a native client that only speaks
    private-use schemes cannot register here.
    """
    if not isinstance(uri, str) or not uri.strip():
        return "A redirect URI must be a non-empty string."
    parts = urllib.parse.urlsplit(uri.strip())
    if parts.fragment:
        return f"`{uri}` carries a fragment, which a redirect URI may not."
    if parts.username or parts.password:
        return f"`{uri}` carries credentials in the URL, which is not accepted."
    if not parts.hostname:
        return (
            f"`{uri}` names no host. A redirect URI must be an absolute "
            "https:// URL, or an http:// loopback URL."
        )
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    if scheme == "https":
        return ""
    if scheme == "http" and host in LOOPBACK_HOSTS:
        return ""
    if scheme == "http":
        return (
            f"`{uri}` is plain http on `{host}`. http is accepted only for a "
            "loopback redirect: localhost, 127.0.0.1, or [::1]. Everything "
            "else must be https."
        )
    return (
        f"`{uri}` uses the `{scheme}` scheme. This server accepts https, and "
        "http only for a loopback redirect on localhost, 127.0.0.1, or [::1]."
    )


def redirect_allowed(client: Client, redirect_uri: object) -> bool:
    """Is this the redirect URI the client registered? Exact string match.

    THE ONE CHECK AT `/authorize` THAT CANNOT BE SKIPPED. An authorization
    server that redirects a code to a URI the client never registered is an
    open redirector with credentials flowing through it: an attacker starts a
    flow under a legitimate client's id, names their own callback, and the
    reader approves a screen showing the legitimate client's name. Every other
    check in this epic assumes the code arrives at the client that asked for
    it.

    Exact, not prefix and not "same origin". A registered
    `https://client.example/cb` must not admit
    `https://client.example/cb/../../anything` or
    `https://client.example/cb?next=https://elsewhere`, and RFC 6749 §3.1.2.3
    says simple string comparison for exactly that reason.

    ONE EXCEPTION, AND IT IS THE RFC'S RATHER THAN A CONVENIENCE. A native
    client receives its redirect on a loopback port the operating system hands
    it at launch, so the port in a registered loopback URI is stale by the
    second run. RFC 8252 §7.3 says an authorization server MUST allow any port
    for a loopback redirect, and it costs nothing to obey: any program on that
    machine can bind any loopback port already, so pinning one buys no
    security and breaks every second launch. Everything else about the URI —
    scheme, host, path, query — still has to match exactly, and the exception
    applies only to the three loopback hosts.
    """
    if not isinstance(redirect_uri, str) or not redirect_uri:
        return False
    if redirect_uri in client.redirect_uris:
        return True
    presented = _loopback_parts(redirect_uri)
    if presented is None:
        return False
    return any(_loopback_parts(one) == presented for one in client.redirect_uris)


def _loopback_parts(uri: str) -> tuple | None:
    """One loopback redirect URI with its port dropped, or None if it is not one.

    None for every non-loopback URI, which is what confines RFC 8252's
    any-port rule to the case it was written for: two https URLs differing only
    in port are two different endpoints and stay that way.
    """
    try:
        parts = urllib.parse.urlsplit(uri.strip())
    except ValueError:
        return None
    if not parts.hostname or parts.hostname.lower() not in LOOPBACK_HOSTS:
        return None
    return (parts.scheme.lower(), parts.hostname.lower(), parts.path, parts.query)


def _redirect_uris(value: object) -> tuple[tuple[str, ...], str]:
    """Validate a whole `redirect_uris` list. Returns the URIs, or a refusal."""
    if not isinstance(value, list) or not value:
        return (), (
            "`redirect_uris` is required and must be a non-empty array of "
            "absolute URLs. This server accepts https, and http only for a "
            "loopback redirect on localhost, 127.0.0.1, or [::1]."
        )
    for one in value:
        refusal = redirect_uri_refusal(one)
        if refusal:
            return (), refusal
    return tuple(str(one).strip() for one in value), ""


# --- The SSRF guard ---------------------------------------------------------


def _address_refusal(ip) -> str:
    """Which category of "do not connect to this" an address falls into, or "".

    Ordered from most specific to least so the reason names the real thing. The
    three tunnelled forms are handled before anything else, because each of
    them is an IPv4 address wearing an IPv6 costume: `::ffff:127.0.0.1` is not
    loopback to `is_loopback`, `2002:7f00:1::` is not loopback to anything, and
    a Teredo address carries two embedded IPv4 addresses in one value. All
    three are refused whether or not what they wrap is private, because none of
    them is a shape a real client metadata document is published behind, and
    the cost of being wrong about that is one refused exotic host against a
    bypass of every check below.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return f"ipv4-mapped/{_address_refusal(mapped) or 'refused'}"
        sixtofour = ip.sixtofour
        if sixtofour is not None:
            return f"6to4/{_address_refusal(sixtofour) or 'refused'}"
        teredo = ip.teredo
        if teredo is not None:
            inner = _address_refusal(teredo[0]) or _address_refusal(teredo[1])
            return f"teredo/{inner or 'refused'}"
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        # 169.254.0.0/16, which is where a cloud metadata server lives. This is
        # the single most important line in the function.
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_private:
        return "private"
    if ip.is_reserved:
        return "reserved"
    if not ip.is_global:
        # The backstop, and it is here because the ladder above was measured
        # rather than assumed. `100.64.0.1` — RFC 6598 carrier-grade NAT, and
        # a range container networks sit in — answers False to `is_private` on
        # Python 3.12: the standard library treats shared address space as
        # neither private nor globally reachable, and a check built out of the
        # named categories alone lets it through. So does 198.18.0.0/15
        # (benchmarking) and the documentation ranges.
        #
        # `is_global` is IANA's own special-purpose registry, which is the
        # authority the named checks are each approximating one row of. Listing
        # the exceptions above it buys a precise reason for the log; this line
        # is what makes the answer correct when the list is incomplete, and the
        # list WAS incomplete.
        return "not-globally-routable"
    return ""


def _resolve(host: str) -> list[str]:
    """Every address this hostname resolves to. Seam for tests.

    The same shape star/auth.py's `_verify` takes, and for the same reason: the
    one call in this module that touches the network is one function, so every
    test in the suite runs with no network and the substitution is a single
    patch rather than a fake socket layer.

    Both families, because asking for one is how a host with a private AAAA and
    a public A gets through a v4-only check.
    """
    infos = socket.getaddrinfo(host, _ALLOWED_PORT, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def safe_https_url(url: object) -> Safe | Unsafe:
    """May this server fetch this URL? See this module's docstring for the list.

    Every resolved address is checked, not the first. A hostname answering with
    one public and one private address is a single connection attempt away from
    the private one, and which of the two urllib picks is not this function's to
    decide.

    An address that does not parse is refused rather than skipped. A resolver
    returning something `ipaddress` cannot read is a case nobody has seen, and
    "cannot evaluate" has exactly one safe answer.
    """
    if not isinstance(url, str) or not url.strip():
        return Unsafe(NOT_A_URL)
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return Unsafe(NOT_A_URL)
    if parts.scheme.lower() != "https":
        return Unsafe(BAD_SCHEME)
    if parts.fragment:
        return Unsafe(FRAGMENT)
    if parts.username or parts.password:
        return Unsafe(USERINFO)
    try:
        host, port = parts.hostname, parts.port
    except ValueError:
        # urlsplit defers parsing the port until it is read, and a non-numeric
        # one raises here rather than at the split above.
        return Unsafe(NOT_A_URL)
    if not host:
        return Unsafe(NO_HOST)
    if port is not None and port != _ALLOWED_PORT:
        return Unsafe(BAD_PORT)

    try:
        addresses = _resolve(host)
    except OSError:
        return Unsafe(UNRESOLVABLE)
    if not addresses:
        return Unsafe(UNRESOLVABLE)

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return Unsafe("unreadable_address")
        refusal = _address_refusal(ip)
        if refusal:
            return Unsafe(f"address:{refusal}")

    return Safe(url=url.strip(), host=host, addresses=tuple(addresses))


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """An opener that will not follow a redirect on its own.

    urllib follows redirects by default, which would take the fetch to a URL
    nothing checked. Returning None from `redirect_request` turns a 3xx into an
    HTTPError the caller sees, so following one is a decision `fetch_document`
    makes out loud, with the guard re-run on the target.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_once(url: str, *, timeout: float, limit: int) -> tuple[int, dict, bytes]:
    """One HTTPS GET, no redirect following, at most `limit` bytes. Seam for tests.

    `read(limit)` rather than `read()`, so a server streaming forever costs
    this thread the limit and not the disk. No `Accept-Encoding` is sent, which
    urllib's default already gives us: without it there is no compressed body
    to expand, so the byte cap is a cap on what arrives AND on what it becomes.

    Header names are lowercased on the way out. HTTP header names are
    case-insensitive and `Location` arrives spelled however the other server
    felt like spelling it; a plain dict is not case-insensitive, and a fake in
    a test should not have to guess the casing either.
    """
    opener = urllib.request.build_opener(_NoRedirects)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, headers, response.read(limit)
    except urllib.error.HTTPError as refused:
        with refused:
            headers = {k.lower(): v for k, v in refused.headers.items()}
            return refused.code, headers, refused.read(limit)


def fetch_document(url: str) -> Fetched | Unsafe:
    """Fetch and parse one client metadata document, or refuse.

    Blocking. Every caller crosses `asyncio.to_thread` — see `lookup` below —
    for the reason star/tokens.py states about the Firestore client: this runs
    on the same single-threaded loop as every open SSE stream on the instance,
    and a five-second fetch on that loop is a five-second stall for every
    reader watching a build.

    The deadline is wall-clock across all hops rather than per hop, because
    three hops at the per-hop timeout is fifteen seconds and a caller waiting
    on this has a request open the whole time.
    """
    deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    target = url
    for _ in range(MAX_REDIRECTS + 1):
        checked = safe_https_url(target)
        if isinstance(checked, Unsafe):
            return checked
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return Unsafe(DEADLINE)
        try:
            status, headers, body = _open_once(
                checked.url,
                timeout=min(FETCH_TIMEOUT_SECONDS, remaining),
                limit=MAX_DOCUMENT_BYTES + 1,
            )
        except Exception:  # noqa: BLE001
            # urllib raises URLError, socket.timeout, ssl.SSLError, and a
            # handful of others depending on where it failed. None of the
            # differences change the answer — this server is not fetching that
            # URL — and enumerating them would be a list that goes stale.
            return Unsafe(TRANSPORT)
        if status in _REDIRECT_STATUSES:
            location = headers.get("location")
            if not location:
                return Unsafe(NO_LOCATION)
            # Resolved against the hop that issued it, because a Location may
            # be relative. The result goes back through the whole guard at the
            # top of the next iteration, which is the point of the loop.
            target = urllib.parse.urljoin(checked.url, location)
            continue
        if status != 200:
            return Unsafe(f"status:{status}")
        if len(body) > MAX_DOCUMENT_BYTES:
            return Unsafe(TOO_LARGE)
        try:
            document = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Unsafe(NOT_JSON)
        if not isinstance(document, dict):
            return Unsafe(NOT_JSON)
        return Fetched(url=checked.url, document=document)
    return Unsafe(TOO_MANY_REDIRECTS)


# --- Client ID Metadata Documents -------------------------------------------

REQUIRED_CIMD_FIELDS = ("client_id", "client_name", "redirect_uris")

# One sentence for every way a metadata document can fail, and it is the same
# sentence. The reason follows star/tokens.py's generic refusal: the caller
# supplying the URL is unauthenticated, and telling them whether the failure
# was a DNS answer, a private address, a 404, or a mismatched `client_id` is a
# probe with this server's network position behind it. The specifics go to the
# log, which is where they are useful.
CIMD_REFUSED = (
    "That `client_id` did not resolve to a usable client metadata document. It "
    "must be an https:// URL that returns a JSON object carrying at least "
    "`client_id`, `client_name`, and `redirect_uris`, whose own `client_id` is "
    "exactly the URL it was fetched from."
)

UNREGISTERED = (
    "No client is registered under that `client_id`. Register one at "
    f"{metadata.REGISTER_PATH}, or use an https:// URL that serves a client "
    "metadata document as the `client_id`."
)


def looks_like_metadata_document(client_id: object) -> bool:
    """Is this client id a CIMD URL rather than a registered id?

    An https:// prefix and nothing cleverer. Ids this server issues start with
    `star_client_`, so the two cannot collide, and a client id that is neither
    reaches the store and is not found, which is the right answer for it.
    """
    return isinstance(client_id, str) and client_id.strip().lower().startswith("https://")


def from_metadata_document(client_id: str, fetched: Fetched | Unsafe) -> Client | Rejected:
    """Validate a fetched document against the URL it claims to be. Pure.

    THE EXACT MATCH IS THE WHOLE MECHANISM. A client id that is a URL is only
    an identity because the document at that URL says it is that URL: without
    the check, anybody who can host JSON can publish a document naming somebody
    else's client id, and the consent screen shows the victim's name. Compared
    against the id the caller presented rather than against the URL the fetch
    finished on, because a redirect must not be able to change which identity a
    document is allowed to claim.

    Exact means exact. No case folding, no trailing-slash tolerance, no
    normalisation of any kind — a document that names a different spelling of
    the same URL is a document that did not answer the question.
    """
    if isinstance(fetched, Unsafe):
        return Rejected(INVALID_CLIENT_METADATA, CIMD_REFUSED)
    document = fetched.document
    for field_name in REQUIRED_CIMD_FIELDS:
        if not document.get(field_name):
            return Rejected(INVALID_CLIENT_METADATA, CIMD_REFUSED)
    if document.get("client_id") != client_id:
        return Rejected(INVALID_CLIENT_METADATA, CIMD_REFUSED)

    uris, refusal = _redirect_uris(document.get("redirect_uris"))
    if refusal:
        # The one CIMD failure that IS told to the caller in detail, and the
        # asymmetry is deliberate: reaching here proved the document exists,
        # is reachable, and claims this client id, so the caller controls it
        # and the refusal describes their own file rather than this server's
        # network.
        return Rejected(INVALID_REDIRECT_URI, refusal)

    scope, scope_refusal = _scope(document.get("scope"))
    if scope_refusal:
        return Rejected(INVALID_CLIENT_METADATA, scope_refusal)

    return Client(
        client_id=client_id,
        client_name=str(document.get("client_name") or "").strip(),
        redirect_uris=uris,
        scope=scope,
        source="cimd",
    )


# --- Dynamic Client Registration (RFC 7591) ---------------------------------


def _scope(value: object) -> tuple[str, str]:
    """The scopes a client may ask for, or a refusal naming what is on offer.

    Absent means everything this server offers, which is RFC 7591's default and
    is safe here because the ceiling on what a client actually gets is the
    consent screen, not this field. An unknown scope is refused rather than
    dropped: silently narrowing a client's registration is how a client ends up
    asking for something it was told it had and being refused at `/authorize`
    with no explanation.
    """
    if value is None or value == "":
        # The non-destructive default, not everything on offer. See
        # metadata.SCOPES_DEFAULT: a blank field must not be how a client comes
        # to request the ability to delete a writer's rooms.
        return metadata.SCOPE_SEPARATOR.join(metadata.SCOPES_DEFAULT), ""
    if not isinstance(value, str):
        return "", "`scope` must be a space-delimited string."
    unknown = sorted(set(value.split()) - set(metadata.SCOPES_SUPPORTED))
    if unknown:
        offered = metadata.SCOPE_SEPARATOR.join(metadata.SCOPES_SUPPORTED)
        return "", (
            f"This server does not offer the scope{'' if len(unknown) == 1 else 's'} "
            f"{', '.join(unknown)}. It offers `{offered}`."
        )
    return metadata.SCOPE_SEPARATOR.join(value.split()), ""


def _subset(value: object, allowed: frozenset, name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
        return f"`{name}` must be an array of strings."
    unknown = sorted(set(value) - allowed)
    if unknown:
        return (
            f"This server does not support the {name} {', '.join(unknown)}. It "
            f"supports {', '.join(sorted(allowed))}."
        )
    return ""


def new_client_id() -> str:
    """A registered client's identifier.

    Prefixed so it can never be mistaken for a metadata document URL, which is
    what `looks_like_metadata_document` routes on. 128 bits because a client id
    is public and unguessable is still worth having: an id that can be guessed
    is an id somebody else can start a flow under, and the consent screen would
    show its name.
    """
    return f"{_DCR_CLIENT_PREFIX}{secrets.token_hex(16)}"


def register(document: object, now: datetime) -> Client | Rejected:
    """RFC 7591 dynamic registration, validated. Pure — no store, no clock call.

    Public clients only. A `token_endpoint_auth_method` other than `none` is
    refused rather than downgraded, because
    star/oauth/metadata.py advertises `none` alone and a client that believes
    it registered with a secret will send one and be confused when it changes
    nothing. Issuing a secret to a program that ships to a laptop is theatre in
    any case: OAuth 2.1 answers what a secret used to answer with PKCE and
    refresh rotation.

    `client_name` is accepted absent, which is RFC 7591's rule and is a
    judgment call this file loses something to. The consent screen has to name
    who is asking, and a client that registered without a name leaves it with
    nothing true to print. Refusing here would be stricter than the RFC and
    would break a conforming client; the screen showing "a client that did not
    give a name" alongside the redirect hostname is the honest alternative, and
    it is the screen's to make rather than this validator's.
    """
    if not isinstance(document, dict):
        return Rejected(
            INVALID_CLIENT_METADATA,
            "The registration body must be a JSON object of client metadata.",
        )

    uris, refusal = _redirect_uris(document.get("redirect_uris"))
    if refusal:
        return Rejected(INVALID_REDIRECT_URI, refusal)

    method = document.get("token_endpoint_auth_method")
    if method is not None and method != "none":
        return Rejected(
            INVALID_CLIENT_METADATA,
            f"`token_endpoint_auth_method` was `{method}`. This server "
            "registers public clients only and issues no client secret, so the "
            "only value it accepts is `none`.",
        )

    for value, allowed, name in (
        (document.get("grant_types"), SUPPORTED_GRANT_TYPES, "grant_types"),
        (document.get("response_types"), SUPPORTED_RESPONSE_TYPES, "response_types"),
    ):
        problem = _subset(value, allowed, name)
        if problem:
            return Rejected(INVALID_CLIENT_METADATA, problem)

    scope, scope_refusal = _scope(document.get("scope"))
    if scope_refusal:
        return Rejected(INVALID_CLIENT_METADATA, scope_refusal)

    name = document.get("client_name")
    return Client(
        client_id=new_client_id(),
        client_name=str(name or "").strip(),
        redirect_uris=uris,
        scope=scope,
        source="dcr",
        registered_at=now.isoformat(),
    )


def to_document(client: Client) -> dict:
    """One registered client as it is stored. Field by field, like to_metadata."""
    return {
        "client_id": client.client_id,
        "client_name": client.client_name,
        "redirect_uris": list(client.redirect_uris),
        "scope": client.scope,
        "source": client.source,
        "registered_at": client.registered_at,
    }


def from_document(document: dict | None) -> Client | None:
    """One stored client, back as a Client. None when there was nothing there."""
    if not isinstance(document, dict) or not document.get("client_id"):
        return None
    return Client(
        client_id=str(document.get("client_id") or ""),
        client_name=str(document.get("client_name") or ""),
        redirect_uris=tuple(str(one) for one in document.get("redirect_uris") or []),
        scope=str(document.get("scope") or ""),
        source=str(document.get("source") or "dcr"),
        registered_at=str(document.get("registered_at") or ""),
    )


def registration_response(client: Client, issued_at: int) -> dict:
    """RFC 7591's registration response.

    No `client_secret`, and therefore no `client_secret_expires_at` — the RFC
    requires that field only when a secret was issued, and including it set to
    zero would tell a client it holds a non-expiring secret it does not hold.
    """
    return {
        "client_id": client.client_id,
        "client_id_issued_at": issued_at,
        "client_name": client.client_name,
        "redirect_uris": list(client.redirect_uris),
        "grant_types": sorted(SUPPORTED_GRANT_TYPES),
        "response_types": sorted(SUPPORTED_RESPONSE_TYPES),
        "token_endpoint_auth_method": "none",
        "scope": client.scope,
    }


# --- Looking one up ---------------------------------------------------------


async def lookup(client_id: object, store) -> Client | Rejected:
    """The client behind a `client_id`, whichever route registered it.

    Routed on the shape of the id rather than on a flag, because the id IS the
    route: an https:// id is a metadata document and is re-read every time,
    where a `star_client_` id is a row this server wrote. Re-reading the CIMD
    on every authorization rather than caching it is the deliberate call — the
    document is the client's own current statement of its redirect URIs, and a
    cached copy is this server enforcing a version of somebody's identity they
    have already changed. It costs one HTTPS fetch per consent screen, which is
    a screen a human is already reading.

    Both branches cross `asyncio.to_thread`: the Firestore client is blocking
    and so is urllib, and this runs on the loop every open SSE stream shares.
    """
    if looks_like_metadata_document(client_id):
        url = str(client_id).strip()
        fetched = await asyncio.to_thread(fetch_document, url)
        return from_metadata_document(url, fetched)

    if not isinstance(client_id, str) or not client_id:
        return Rejected(INVALID_CLIENT_METADATA, UNREGISTERED)

    document = await asyncio.to_thread(store.get, client_id)
    client = from_document(document)
    if client is None:
        return Rejected(INVALID_CLIENT_METADATA, UNREGISTERED)
    return client
