"""The SSRF guard, on its own, because it is the dangerous part of this epic.

Client ID Metadata Documents make this server fetch a URL an unauthenticated
stranger chose. That is a request-forgery primitive by construction, pointed
from inside the deployment at whatever answers there — on Cloud Run, the
metadata server at 169.254.169.254, which hands out access tokens for the
service account.

So the guard is a separate function and this is a separate file. Every refusal
star/oauth/clients.py's docstring lists has a test here, named for the thing it
refuses rather than for the branch it covers.

NO NETWORK, ANYWHERE IN THIS FILE. Two module-level seams do it, both in
star/auth.py's `_verify` shape: `_resolve` is the only DNS call and `_open_once`
is the only HTTP call. Patching them is the whole substitution, which is also
the argument for them existing — a guard whose network calls are scattered
across a function cannot be tested at all, and one that is only tested against a
live server is only tested when somebody remembers to point it at something
hostile.
"""

import json
import urllib.request
from unittest import mock

import pytest

from star.oauth import clients

METADATA_SERVER = "169.254.169.254"


def resolving(*addresses):
    """Patch DNS to answer with exactly these addresses, for every hostname."""
    return mock.patch.object(clients, "_resolve", return_value=list(addresses))


def refusal_for(url, *addresses):
    """Run the guard against one URL with a fixed DNS answer."""
    with resolving(*addresses):
        return clients.safe_https_url(url)


def responder(pages):
    """A fake `_open_once` driven by a {url: (status, headers, body)} table.

    A dict rather than a single canned answer, because the redirect tests are
    about what happens on the SECOND hop and a fake that cannot tell the hops
    apart could not express them.
    """

    def _open_once(url, *, timeout, limit):
        if url not in pages:
            raise AssertionError(f"unexpected fetch of {url}")
        status, headers, body = pages[url]
        return status, headers, body[: limit]

    return _open_once


def as_json(document) -> bytes:
    return json.dumps(document).encode()


# --- the scheme -------------------------------------------------------------


def test_a_non_https_scheme_is_refused_before_anything_is_resolved():
    """First check in the function, and it has to be: http to a private host
    is the shortest path to the metadata server, and `http://` is also what a
    caller reaches for by accident."""
    for url in (
        f"http://{METADATA_SERVER}/computeMetadata/v1/",
        "http://example.com/client.json",
        "file:///etc/passwd",
        "gopher://example.com:70/",
        "ftp://example.com/client.json",
        "HTTP://example.com/client.json",
    ):
        with mock.patch.object(clients, "_resolve", side_effect=AssertionError("dns")):
            outcome = clients.safe_https_url(url)
        assert isinstance(outcome, clients.Unsafe), url
        assert outcome.reason == clients.BAD_SCHEME, url


def test_a_url_that_is_not_a_url_is_refused_rather_than_guessed_at():
    for url in (None, "", "   ", 17, [], "not a url at all"):
        outcome = clients.safe_https_url(url)
        assert isinstance(outcome, clients.Unsafe), url


# --- the address ------------------------------------------------------------


def test_loopback_is_refused_by_literal_and_by_name():
    """Both spellings, because the second is the one that arrives in practice:
    `https://localhost/client.json` is a URL somebody writes, and the address
    behind it is only visible after resolution."""
    literal = refusal_for("https://127.0.0.1/client.json", "127.0.0.1")
    named = refusal_for("https://localhost/client.json", "127.0.0.1")
    six = refusal_for("https://[::1]/client.json", "::1")

    for outcome in (literal, named, six):
        assert isinstance(outcome, clients.Unsafe)
        assert outcome.reason == "address:loopback"


def test_every_private_ipv4_range_is_refused():
    for address in (
        "10.0.0.1",
        "10.255.255.254",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.1.1",
        "192.0.0.1",
    ):
        outcome = refusal_for("https://host.example/client.json", address)
        assert isinstance(outcome, clients.Unsafe), address
        assert outcome.reason == "address:private", address


def test_the_ranges_the_standard_library_calls_neither_private_nor_global():
    """The hole this test found rather than covered.

    `ipaddress.IPv4Address("100.64.0.1").is_private` is False on Python 3.12 —
    RFC 6598 carrier-grade NAT is shared address space, which the standard
    library treats as neither private nor globally reachable. A guard built out
    of the named categories alone admitted it, and a container network sitting
    in that range is exactly what an SSRF is aimed at. Same for the
    benchmarking and documentation ranges.
    """
    for address in ("100.64.0.1", "198.18.0.1", "203.0.113.9", "192.0.2.1"):
        outcome = refusal_for("https://host.example/client.json", address)
        assert isinstance(outcome, clients.Unsafe), address
        assert outcome.reason.startswith("address:"), address


def test_every_private_ipv6_range_is_refused():
    for address, expected in (
        ("fd00::1", "address:private"),  # unique local
        ("fc00::1", "address:private"),
        ("fe80::1", "address:link-local"),
        ("::", "address:unspecified"),
        ("ff02::1", "address:multicast"),
    ):
        outcome = refusal_for("https://host.example/client.json", address)
        assert isinstance(outcome, clients.Unsafe), address
        assert outcome.reason == expected, address


def test_an_ipv4_mapped_ipv6_address_is_refused_and_names_what_it_wraps():
    """`::ffff:127.0.0.1` is loopback and `is_loopback` says False about it.

    That is the whole reason the mapped check runs before every other test in
    `_address_refusal`: a guard that reached `is_loopback` first would wave
    this through while believing it had checked for loopback.
    """
    for address, inner in (
        ("::ffff:127.0.0.1", "loopback"),
        ("::ffff:10.0.0.1", "private"),
        ("::ffff:169.254.169.254", "link-local"),
    ):
        outcome = refusal_for("https://host.example/client.json", address)
        assert isinstance(outcome, clients.Unsafe), address
        assert outcome.reason == f"address:ipv4-mapped/{inner}", address


def test_a_mapped_address_wrapping_a_public_one_is_still_refused():
    """Strict on purpose. Nobody publishes a client metadata document behind an
    IPv4-mapped IPv6 address, and the alternative is deciding which costumes
    are innocent."""
    outcome = refusal_for("https://host.example/client.json", "::ffff:93.184.216.34")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason.startswith("address:")


def test_the_two_other_ipv4_in_ipv6_costumes_are_refused_too():
    """6to4 wraps an IPv4 address in the address itself; Teredo wraps two."""
    sixtofour = refusal_for("https://host.example/client.json", "2002:7f00:0001::")
    teredo = refusal_for("https://host.example/client.json", "2001:0:4136:e378::1")

    assert isinstance(sixtofour, clients.Unsafe)
    assert sixtofour.reason.startswith("address:6to4/")
    assert isinstance(teredo, clients.Unsafe)
    assert teredo.reason.startswith("address:teredo/")


def test_the_cloud_metadata_server_is_refused_by_the_link_local_check():
    """The single address this whole file exists for."""
    outcome = refusal_for("https://evil.example/client.json", METADATA_SERVER)

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == "address:link-local"


def test_one_private_address_among_public_ones_refuses_the_whole_name():
    """A round-robin answer carrying a public and a private address is one
    connection attempt away from the private one, and which of them urllib
    picks is not this function's to decide."""
    outcome = refusal_for("https://host.example/client.json", "93.184.216.34", "10.0.0.7")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == "address:private"


def test_a_hostname_that_resolves_to_nothing_is_refused():
    with mock.patch.object(clients, "_resolve", return_value=[]):
        empty = clients.safe_https_url("https://host.example/client.json")
    with mock.patch.object(clients, "_resolve", side_effect=OSError("NXDOMAIN")):
        failed = clients.safe_https_url("https://host.example/client.json")

    assert isinstance(empty, clients.Unsafe)
    assert empty.reason == clients.UNRESOLVABLE
    assert isinstance(failed, clients.Unsafe)
    assert failed.reason == clients.UNRESOLVABLE


def test_an_address_the_parser_cannot_read_is_refused_rather_than_skipped():
    """"Cannot evaluate" has exactly one safe answer."""
    outcome = refusal_for("https://host.example/client.json", "not-an-address")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == "unreadable_address"


# --- the rest of the URL ----------------------------------------------------


def test_a_port_other_than_443_is_refused():
    """Removes the ability to point this server at an arbitrary port on a
    public host and read the timing. Named as a cost in the module: a client
    publishing on a non-default port cannot register."""
    with mock.patch.object(clients, "_resolve", side_effect=AssertionError("dns")):
        odd = clients.safe_https_url("https://host.example:8443/client.json")
    explicit = refusal_for("https://host.example:443/client.json", "93.184.216.34")

    assert isinstance(odd, clients.Unsafe)
    assert odd.reason == clients.BAD_PORT
    assert isinstance(explicit, clients.Safe)


def test_credentials_in_the_url_and_a_fragment_are_both_refused():
    with mock.patch.object(clients, "_resolve", side_effect=AssertionError("dns")):
        userinfo = clients.safe_https_url("https://user:pw@host.example/client.json")
        fragment = clients.safe_https_url("https://host.example/client.json#x")

    assert isinstance(userinfo, clients.Unsafe)
    assert userinfo.reason == clients.USERINFO
    assert isinstance(fragment, clients.Unsafe)
    assert fragment.reason == clients.FRAGMENT


def test_a_public_https_url_passes_and_reports_what_it_resolved_to():
    outcome = refusal_for("https://host.example/client.json", "93.184.216.34")

    assert isinstance(outcome, clients.Safe)
    assert outcome.host == "host.example"
    assert outcome.addresses == ("93.184.216.34",)


# --- the fetch on top of the guard ------------------------------------------

_DOCUMENT = {
    "client_id": "https://host.example/client.json",
    "client_name": "A desktop client",
    "redirect_uris": ["http://127.0.0.1:9876/callback"],
}


def test_a_redirect_into_a_private_range_is_refused_on_the_second_hop():
    """The reason redirects are not left to urllib.

    The first hop is a perfectly ordinary public host. The second is where the
    attack lives, and it only exists as a `Location` header — nothing about the
    URL the caller supplied says anything about it. urllib would follow it
    without asking, which is why `_NoRedirects` exists and why the loop re-runs
    the whole guard on every hop's target.
    """
    pages = {
        "https://host.example/client.json": (
            302,
            {"location": "https://internal.example/secret"},
            b"",
        ),
        "https://internal.example/secret": (200, {}, as_json(_DOCUMENT)),
    }

    def _resolve(host):
        return {"host.example": ["93.184.216.34"], "internal.example": ["10.0.0.7"]}[host]

    with (
        mock.patch.object(clients, "_resolve", side_effect=_resolve),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
    ):
        outcome = clients.fetch_document("https://host.example/client.json")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == "address:private"


def test_a_redirect_to_a_non_https_scheme_is_refused_on_the_second_hop():
    pages = {
        "https://host.example/client.json": (
            302,
            {"location": f"http://{METADATA_SERVER}/computeMetadata/v1/"},
            b"",
        )
    }

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
    ):
        outcome = clients.fetch_document("https://host.example/client.json")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == clients.BAD_SCHEME


def test_a_relative_location_is_resolved_against_the_hop_that_sent_it():
    pages = {
        "https://host.example/client.json": (301, {"location": "/moved.json"}, b""),
        "https://host.example/moved.json": (200, {}, as_json(_DOCUMENT)),
    }

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
    ):
        outcome = clients.fetch_document("https://host.example/client.json")

    assert isinstance(outcome, clients.Fetched)
    assert outcome.url == "https://host.example/moved.json"


def test_a_redirect_chain_past_the_cap_stops_rather_than_looping():
    pages = {
        f"https://host.example/{n}": (302, {"location": f"/{n + 1}"}, b"")
        for n in range(12)
    }

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
    ):
        outcome = clients.fetch_document("https://host.example/0")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == clients.TOO_MANY_REDIRECTS


def test_a_redirect_with_no_location_is_refused():
    pages = {"https://host.example/client.json": (302, {}, b"")}

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
    ):
        outcome = clients.fetch_document("https://host.example/client.json")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == clients.NO_LOCATION


def test_a_body_past_the_cap_is_refused_rather_than_parsed():
    """The read itself is capped at the limit plus one byte, so the refusal
    costs the limit and not the disk. Asserted on the limit passed to the
    opener as well as on the answer, because a cap the caller never applies is
    a cap that is not there."""
    seen = {}

    def _open_once(url, *, timeout, limit):
        seen["limit"] = limit
        return 200, {}, b"x" * limit

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=_open_once),
    ):
        outcome = clients.fetch_document("https://host.example/client.json")

    assert seen["limit"] == clients.MAX_DOCUMENT_BYTES + 1
    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == clients.TOO_LARGE


def test_a_body_that_is_not_a_json_object_is_refused():
    for body in (b"not json", b"[1, 2, 3]", b'"a string"', b"", b"\xff\xfe"):
        pages = {"https://host.example/client.json": (200, {}, body)}
        with (
            resolving("93.184.216.34"),
            mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
        ):
            outcome = clients.fetch_document("https://host.example/client.json")
        assert isinstance(outcome, clients.Unsafe), body
        assert outcome.reason == clients.NOT_JSON, body


def test_a_non_200_status_is_refused_and_names_the_status_in_the_log_reason():
    for status in (400, 401, 403, 404, 500, 503):
        pages = {"https://host.example/client.json": (status, {}, b"{}")}
        with (
            resolving("93.184.216.34"),
            mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
        ):
            outcome = clients.fetch_document("https://host.example/client.json")
        assert isinstance(outcome, clients.Unsafe), status
        assert outcome.reason == f"status:{status}", status


def test_any_transport_failure_becomes_one_refusal_rather_than_an_exception():
    """urllib raises half a dozen different things depending on where it
    failed, and none of the differences change the answer."""
    for boom in (OSError("connection reset"), ValueError("nonsense"), TimeoutError()):
        with (
            resolving("93.184.216.34"),
            mock.patch.object(clients, "_open_once", side_effect=boom),
        ):
            outcome = clients.fetch_document("https://host.example/client.json")
        assert isinstance(outcome, clients.Unsafe), boom
        assert outcome.reason == clients.TRANSPORT, boom


def test_the_wall_clock_deadline_stops_a_chain_of_slow_hops():
    """A per-hop timeout bounds one hop. Four hops at the per-hop ceiling is
    four times the number anybody agreed to, and the caller has a request open
    the whole time."""
    pages = {
        f"https://host.example/{n}": (302, {"location": f"/{n + 1}"}, b"")
        for n in range(12)
    }
    ticks = iter([0.0] + [clients.TOTAL_DEADLINE_SECONDS + 1] * 20)

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
        mock.patch.object(clients.time, "monotonic", side_effect=lambda: next(ticks)),
    ):
        outcome = clients.fetch_document("https://host.example/0")

    assert isinstance(outcome, clients.Unsafe)
    assert outcome.reason == clients.DEADLINE


def test_a_good_document_comes_back_parsed():
    pages = {"https://host.example/client.json": (200, {}, as_json(_DOCUMENT))}

    with (
        resolving("93.184.216.34"),
        mock.patch.object(clients, "_open_once", side_effect=responder(pages)),
    ):
        outcome = clients.fetch_document("https://host.example/client.json")

    assert isinstance(outcome, clients.Fetched)
    assert outcome.document == _DOCUMENT


def test_the_opener_is_built_to_refuse_to_follow_a_redirect_by_itself():
    """The mechanism the redirect tests above depend on.

    urllib follows redirects by default, which would take the fetch to a URL
    nothing checked. `redirect_request` returning None is what makes urllib
    raise the 3xx as an HTTPError instead, so following one becomes a decision
    `fetch_document` makes out loud with the guard re-run on the target.
    """
    handler = clients._NoRedirects()

    assert (
        handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere") is None
    )
    # And it has to REPLACE urllib's own handler rather than sit beside it.
    # `build_opener` drops a default class when a passed handler subclasses it,
    # which is why _NoRedirects subclasses rather than reimplements.
    assert issubclass(clients._NoRedirects, urllib.request.HTTPRedirectHandler)
    installed = urllib.request.build_opener(clients._NoRedirects).handlers
    redirectors = [
        one
        for one in installed
        if isinstance(one, urllib.request.HTTPRedirectHandler)
    ]
    assert len(redirectors) == 1
    assert isinstance(redirectors[0], clients._NoRedirects)


def test_the_default_resolver_is_the_only_dns_call_in_the_module():
    """The seam's own contract. If a second call site appeared, patching
    `_resolve` would stop being the whole substitution and every test above
    would start reaching the network without failing."""
    with mock.patch.object(clients.socket, "getaddrinfo", return_value=[]) as looked_up:
        assert clients._resolve("host.example") == []

    looked_up.assert_called_once()


@pytest.mark.parametrize(
    "hostile",
    [
        f"https://{METADATA_SERVER}/computeMetadata/v1/instance/service-accounts/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://localhost:443/admin",
        "https://[::ffff:169.254.169.254]/latest/meta-data/",
    ],
)
def test_the_shapes_an_attacker_would_actually_send(hostile):
    """Written as the request rather than as the branch. Each of these is a URL
    somebody would put in a `client_id` on purpose, and each has to be refused
    by the guard rather than by something further down."""
    answers = {
        METADATA_SERVER: [METADATA_SERVER],
        "metadata.google.internal": [METADATA_SERVER],
        "localhost": ["127.0.0.1"],
        "::ffff:169.254.169.254": ["::ffff:169.254.169.254"],
    }
    with mock.patch.object(clients, "_resolve", side_effect=lambda h: answers[h]):
        outcome = clients.safe_https_url(hostile)

    assert isinstance(outcome, clients.Unsafe), hostile
    assert outcome.reason.startswith("address:"), hostile
