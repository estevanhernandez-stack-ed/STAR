"""The resource-server side: is this token still good, for HERE, for THIS?

star/tokens.py answers whether a credential is real and unrevoked, which is the
same question for a card token and an OAuth one. Three questions are left over
and all three belong to the resource rather than to the credential: has it
expired, was it minted for this resource, and does it carry the scope the
operation needs. They live here rather than inside `resolve` for a reason that
is about the transport, not about tidiness: the first two are a **401** and the
third is a **403 insufficient_scope**, and a resolver that refused all three
identically would collapse a distinction the client acts on. A 401 says get a
new token. A 403 says the token is fine and this account did not approve that.

THE CARD TOKEN IS THE FIRST BRANCH AND THE WHOLE COMPATIBILITY STORY.
`spec-oauth-as.md`'s Decision 5: `/mcp` accepts both, a card token has no
audience and no expiry and stays that way, and `harness/runs/*.md` are
committed transcripts of it working. `identity.oauth is None` is that sentence
as a branch, and it is first so that nothing below it can grow a rule a card
token was never meant to satisfy.

Card tokens are also unscoped, which follows from the same decision rather than
being a concession to it: nothing ever asked a reader which scopes their card
token should carry, so refusing one for want of `rooms:write` would be
enforcing a consent that was never sought. The scope model starts with OAuth
and applies to OAuth.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from star import tokens
from star.oauth import metadata

# `spec-oauth-as.md`'s Decision 4, as a mapping. It is the free-versus-spends
# split every description in star/mcp/tools.py already states, which is what
# lets the consent screen say something true and specific instead of asking for
# everything.
SCOPE_SEPARATOR = metadata.SCOPE_SEPARATOR

SCOPE_BY_TOOL = {
    "list_rooms": "rooms:read",
    "get_room": "rooms:read",
    "ask_room": "rooms:read",
    # Reads, so it reads. The card is a SHAPE of a room that already exists —
    # one finding, its sources, its retrieval date — assembled from the same
    # document `get_room` returns. It sends nobody to the field and spends
    # nothing, and a writer handing an agent a read token should be able to
    # get a citation out of it.
    "defend_claim": "rooms:read",
    "build_room": "rooms:write",
    "check_scene": "rooms:write",
    # rooms:write and not rooms:read, though it reads like a question. What
    # separates the two scopes on this door is spending, not reading: this one
    # sends a researcher to the field, spends live searches against the
    # writer's hourly window, and changes what a room contains. `ask_room` is
    # the free half of the same gesture and stays on rooms:read, which is what
    # lets a reader hand an agent a read token and know the worst it can do is
    # read.
    "research_question": "rooms:write",
    # Its own scope, not folded into rooms:write. Building and deleting are
    # opposite risks — one spends money to make something, the other destroys
    # something already paid for — and a reader handing an agent the ability to
    # research for them has said nothing about whether it may clear their
    # workspace. Granting them together would be inferring the second consent
    # from the first.
    "delete_room": "rooms:delete",
    # The file half. Reads read, spends spend, and the two that are neither
    # obviously are worth their own sentence.
    "get_sweep": "rooms:read",
    "export_room": "rooms:read",
    # Spends nothing and is still a write: it rewires what a story IS, and
    # every check, every `ask_room` and every story export afterwards reads the
    # chain it sets. A reader who handed an agent a read token was promising
    # themselves the worst it could do is read.
    "link_room": "rooms:write",
    # Same band, and this is the line most worth arguing. `import_rooms`
    # spends no searches and costs nothing — by the "what separates the two
    # scopes is spending" rule above it would be a read. It is not: it MINTS
    # ROOMS in somebody's account, and a reader who handed an agent a read
    # token was promising themselves that the worst it could do is read. A
    # workspace filling with rooms nobody asked for is not that.
    "import_rooms": "rooms:write",
    # Spends a model call over research the room already holds, and writes the
    # document into it. No searches, but a write either way.
    "write_bible": "rooms:write",
    # One slot of the hourly window and one search budget for a whole draft.
    "sweep_draft": "rooms:write",
}

# A tool missing from the map above is not scope-free, it is unfinished: the
# router skips the check when `scope_for` returns None, so an unmapped tool is
# callable by any valid token whatever it was granted. `ask_room` shipped that
# way and was caught by adding delete. tests/test_mcp_protocol.py asserts this
# map covers every tool, which is the guard that stops the next one.

# RFC 6750's two, and they are the only two this file emits.
INVALID_TOKEN = "invalid_token"
INSUFFICIENT_SCOPE = "insufficient_scope"

EXPIRED = (
    "This access token has expired. Exchange your refresh token at "
    "/oauth/token for a new one; if that is also refused, run the "
    "authorization flow again."
)

WRONG_AUDIENCE = (
    "This access token was issued for a different resource and is not accepted "
    "here. Request a token with the `resource` parameter set to this server's "
    "canonical URI, which is published at /.well-known/oauth-protected-resource."
)

NOT_AN_ACCESS_TOKEN = (
    "That credential is not an access token. A refresh token is exchanged at "
    "/oauth/token and is never sent to this endpoint."
)


@dataclass(frozen=True)
class Allowed:
    """The call may proceed, and this is who is making it."""

    identity: tokens.TokenIdentity


@dataclass(frozen=True)
class Denied:
    """The call may not proceed, in the terms the transport has to answer in.

    `status` is 401 or 403 and nothing else. `error` is RFC 6750's code, or
    None for the one case that carries no code: a request that presented no
    credential at all. RFC 6750 says a challenge answering that SHOULD NOT
    carry an error, and the reason is behavioural rather than pedantic — a
    client told `invalid_token` before it has ever authenticated will try to
    refresh a token it does not have.

    `scope` is set only on `insufficient_scope`, where RFC 6750 defines it as
    the scope the request needs. It goes into the challenge, so a client is
    told what to ask for next rather than being left to guess.
    """

    status: int
    error: str | None
    description: str
    scope: str | None = None
    reason: str = ""

    def challenge(self) -> str:
        """The `WWW-Authenticate` value this denial is owed."""
        return metadata.www_authenticate(
            error=self.error, description=self.description, scope=self.scope
        )


def scope_for(tool: str) -> str | None:
    """Which scope one MCP tool needs, or None when it is not one of the four.

    None rather than a default, and the default it is refusing to pick is the
    interesting half. Defaulting to `rooms:read` would let a tool added later
    spend money under a read-only grant; defaulting to `rooms:write` would
    refuse an unknown tool that costs nothing. Returning None hands the choice
    back to the caller, and star/mcp/tools.py already answers an unknown tool
    name with a refusal that names the four, so an unknown name never reaches a
    scope decision in practice.
    """
    return SCOPE_BY_TOOL.get(tool)


def requested_scope(requested: object, client_scope: str) -> str | None:
    """What an authorization request may actually ask the reader to approve.

    Called at `/authorize`, before the consent screen is drawn, and it is the
    ceiling on what that screen may offer. A client registered for
    `rooms:read` that requests `rooms:write` is asking for something it was
    never registered for, and the screen must not print a checkbox for it — a
    reader approving a screen is approving what the screen said, so anything
    the screen can say has to already be true.

    None means refuse the authorization request outright, which is
    `invalid_scope` on the wire. Silently narrowing instead would draw a screen
    granting less than the client asked for, and the client would then fail at
    its first call with a 403 naming a scope its own registration says it has.

    An empty or absent request gets everything the client registered for. That
    is RFC 6749's default, and it is safe for the same reason the registration
    default is: the consent screen is the ceiling, not this function.
    """
    available = set(client_scope.split())
    if requested is None or requested == "":
        return SCOPE_SEPARATOR.join(sorted(available))
    if not isinstance(requested, str):
        return None
    asked = set(requested.split())
    if not asked or not asked <= available:
        return None
    return SCOPE_SEPARATOR.join(sorted(asked))


def expired(expires_at: object, now: datetime) -> bool:
    """Is this expiry stamp in the past? Anything unreadable counts as expired.

    Fail closed, in every direction. An empty stamp, a non-string, a value no
    parser recognises: all expired. That is the opposite of star/tokens.py's
    `_is_stale`, which treats an unreadable `last_used_at` as stale so it
    self-heals — and the difference is what the field costs when it is wrong.
    A wrong `last_used_at` shows a reader a stale date. A wrong `expires_at`
    read generously is a one-hour credential that never ends.

    A naive stamp is read as UTC, matching `_is_stale`, because everything this
    project writes is `datetime.now(timezone.utc).isoformat()` and a stamp that
    lost its offset in a round trip is still describing UTC.
    """
    if not isinstance(expires_at, str) or not expires_at:
        return True
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)  # noqa: UP017
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)  # noqa: UP017
    return deadline <= now


def check(
    identity: tokens.TokenIdentity,
    *,
    need: str | None = None,
    now: datetime | None = None,
) -> Allowed | Denied:
    """The three resource-side questions, in the order their answers matter.

    Kind, then expiry, then audience, then scope, and the order is doing work
    at both ends. A refresh token presented as a bearer token is refused first
    because it is the wrong KIND of credential and nothing else about it is
    worth evaluating. Audience is checked before scope so that a token minted
    for somebody else's resource is never handed a 403 describing THIS
    server's scopes — that answer would confirm the token is otherwise valid
    here, and it is not this server's business to say so.
    """
    facts = identity.oauth
    if facts is None:
        return Allowed(identity)

    stamp = now or datetime.now(timezone.utc)  # noqa: UP017

    if facts.kind != tokens.ACCESS:
        return Denied(401, INVALID_TOKEN, NOT_AN_ACCESS_TOKEN, reason="wrong_kind")
    if expired(facts.expires_at, stamp):
        return Denied(401, INVALID_TOKEN, EXPIRED, reason="expired")
    if metadata.canonical(facts.audience) != metadata.resource():
        return Denied(401, INVALID_TOKEN, WRONG_AUDIENCE, reason="audience")
    if need and need not in facts.scope.split():
        return Denied(
            403,
            INSUFFICIENT_SCOPE,
            f"This token does not carry the `{need}` scope, which that "
            f"operation needs. It carries `{facts.scope or 'nothing'}`. "
            "Authorize again and approve the missing scope.",
            scope=need,
            reason="scope",
        )
    return Allowed(identity)


async def authorize(
    header: str | None,
    store,
    *,
    need: str | None = None,
    resolve=tokens.resolve,
    now: datetime | None = None,
) -> Allowed | Denied:
    """Resolve a credential and check it, as one call. The whole door.

    ONE FUNCTION BECAUSE TWO IS A GAP. `resolve` deliberately does not enforce
    expiry or audience — it cannot, since it has no opinion about which HTTP
    status the answer becomes — so a transport that calls it and forgets this
    file accepts expired OAuth tokens forever and accepts tokens minted for
    other resources, which is precisely the MUST the MCP authorization spec
    puts on a resource server. Composing them here means the wiring cannot get
    half of it.

    `resolve` is injected so a test can drive every outcome without a store,
    matching how star/mcp/router.py already takes its token resolver.

    The three Refusals become Denied with their own messages carried through
    unchanged. Nothing is re-worded: star/tokens.py argues at length that a
    token of the wrong shape, an unknown id, and a wrong secret are ONE answer,
    and a second file paraphrasing them is how that stops being true.
    """
    identity = await resolve(header, store, now=now)
    if isinstance(identity, tokens.Refusal):
        return Denied(
            401,
            # No error code when nothing was presented. See Denied's docstring.
            None if identity is tokens.MISSING else INVALID_TOKEN,
            identity.message,
            reason=identity.reason,
        )
    return check(identity, need=need, now=now)
