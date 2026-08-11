"""MCP bearer tokens: minting, the shape they are stored in, and resolution.

A token is `star_<12 hex>.<32 hex>`, and it is two parts on purpose. The first
is an identifier: it names the token in `GET /api/tokens`, in a DELETE path, on
the card, and in any log line that ever mentions one. The second is a
credential. They should not carry the same entropy or the same exposure, which
is the argument `star/server.py:601-620` already makes for `run_id` versus
`stream_key`, applied one layer up to a credential that outlives a process
instead of dying with it.

Only the sha256 of the secret is stored. The plaintext exists on the wire
exactly once, in the response to `POST /api/tokens`, and nowhere else: not in
Firestore, not in a log line, not in any read this module offers.

Firestore is not touched here. Every read and write goes through
`star/store.py`'s TokenStore, which stays the only module in the project that
talks to the database, and every call to it crosses `asyncio.to_thread` because
the client is blocking and this runs on the same single-threaded loop as every
open SSE stream on the instance.
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from star.auth import extract_bearer
from star.models import McpToken

logger = logging.getLogger(__name__)

_PREFIX = "star_"
_ID_HEX = 12
_SECRET_HEX = 32
_HEX = frozenset("0123456789abcdef")

# How often one token's last_used_at may be rewritten. `get_room` is a polling
# endpoint by design, so a write per MCP call is a Firestore write per agent
# poll — a cost that scales with how well-behaved the agent is.
_LAST_USED_THROTTLE_SECONDS = 60

# Ceiling on a reader-supplied label. Long enough for "desktop agent, work
# laptop", short enough that the card's token list stays a list.
MAX_LABEL_CHARS = 80


@dataclass(frozen=True)
class OAuthFacts:
    """The five fields an OAuth-issued credential carries and a card one does not.

    A separate object rather than five optional fields on TokenIdentity, and
    the reason is the one distinction this whole epic turns on:
    `spec-oauth-as.md`'s Decision 5 says a card token has no audience and no
    expiry and stays that way, while an OAuth token has both and is checked for
    both. `identity.oauth is None` IS that sentence, in one place, as a type. A
    caller that forgets to check it gets an attribute error rather than a
    silently unbounded credential.

    Nothing here is enforced by this module. `resolve` answers "is this
    credential real and not revoked", which is the same question for both kinds
    of token; whether an OAuth token is still in date, minted for THIS resource,
    and carrying enough scope is star/oauth/validate.py's, because those three
    are the difference between a 401 and a 403 and only the transport knows
    which it is answering.
    """

    kind: str
    client_id: str
    audience: str
    scope: str
    expires_at: str
    family_id: str


@dataclass(frozen=True)
class TokenIdentity:
    """Who a presented token turned out to be. The allow answer.

    `oauth` is None for every token the card issues, which is every token that
    existed before the authorization server did. That default is what keeps
    `harness/` and `claude mcp add --header` working against a resolver that
    now also serves OAuth: a document with none of the OAuth fields produces
    exactly the object it produced before.
    """

    uid: str
    token_id: str
    oauth: OAuthFacts | None = None


@dataclass(frozen=True)
class Refusal:
    """Why a presented token was not accepted, and what to say about it.

    `reason` is carried alongside `message` so a transport can branch without
    matching on prose. It is deliberately as coarse as the message is: the
    three ways a token can fail to match anything share ONE reason value as
    well as one string, so a router that switches on `reason` cannot
    reintroduce the distinction the string refuses to draw.
    """

    reason: str
    message: str


# The refusals, as constants, because "these two strings are identical" and
# "these two strings differ" are both properties tests assert directly.
#
# MISSING is not an exception to the generic answer below, because it is not an
# answer about a token: the caller sent no credential and already knows it.
# Telling them so costs nothing and is the only one of the three that can name
# a next step precisely, which is what `prd.md`'s "every error names what
# failed and what to do next" asks for. It is unreachable the moment any
# credential is presented — see resolve.
MISSING = Refusal(
    "missing",
    "Authorization header missing. Issue a token from Your card in the web app "
    "and send it as `Authorization: Bearer star_...`.",
)

# The generic refusal, covering a token of the wrong shape, a token id that
# matches no document, and a secret whose hash does not match the one on file.
# One message, one reason, no distinguishing detail — `star/auth.py:119-145`'s
# posture, for the same reason: a well-formed token that matches nothing and a
# malformed one are the same answer, and telling a stranger which of them they
# sent is free reconnaissance into which token ids are real.
UNRECOGNISED = Refusal(
    "unrecognised",
    "This token was not recognised. Issue a new one from Your card.",
)

# The one deliberate exception, and it is safe only because reaching it
# required presenting the correct secret for a token that exists. Getting here
# proves the caller held this credential, so naming its state tells them
# nothing they did not already have. It has to be its own answer: an agent
# configured months ago and revoked yesterday would otherwise spend its
# operator's afternoon debugging a malformed header.
REVOKED = Refusal(
    "revoked",
    "This token was revoked. Issue a new one from Your card.",
)


def mint() -> tuple[str, str, str]:
    """A fresh `(token_id, secret, plaintext)`.

    `secrets`, not `random`, and both halves come from the same CSPRNG — the
    id is not a secret but a guessable id is still a nuisance on a surface
    where ids appear in paths.
    """
    token_id = secrets.token_hex(_ID_HEX // 2)
    secret = secrets.token_hex(_SECRET_HEX // 2)
    return token_id, secret, f"{_PREFIX}{token_id}.{secret}"


def hash_secret(secret: str) -> str:
    """What goes to Firestore in place of the secret.

    Plain sha256 with no salt and no stretching, and that is the right call
    rather than a corner cut: this is a 128-bit value from a CSPRNG, not a
    human-chosen password. There is no dictionary to run against it and no
    other account it is reused on, so the work factor a password hash buys
    would only be spent on every MCP call. The 626Labs dashboard's token
    scheme makes the same choice, which is the precedent `prd.md` names.
    """
    return hashlib.sha256(secret.encode()).hexdigest()


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and set(value) <= _HEX


def parse(token: str | None) -> tuple[str, str] | None:
    """Split a presented token into `(token_id, secret)`, or None. Pure.

    The shape is checked here, before the store is asked anything, and that is
    worth a line: a token id that cannot exist never costs a Firestore read, so
    a public endpoint cannot be used to make the department do database work
    for free. `partition` splits on the FIRST dot only; a secret carrying a
    second one fails the hex check rather than being quietly accepted.
    """
    if not token or not token.startswith(_PREFIX):
        return None
    token_id, separator, secret = token[len(_PREFIX) :].partition(".")
    if not separator:
        return None
    if not _is_hex(token_id, _ID_HEX) or not _is_hex(secret, _SECRET_HEX):
        return None
    return token_id, secret


def to_metadata(document: dict | None) -> McpToken:
    """One stored token as the card is allowed to see it.

    Field by field rather than `McpToken(**document)`, and that is the load-
    bearing choice here: the stored document carries `secret_sha256`, and a
    splat is how a field added to the document later arrives on the wire
    without anyone deciding it should. Pydantic would drop the extra key today;
    this drops it on purpose, which is a different guarantee.
    """
    document = document or {}
    return McpToken(
        token_id=str(document.get("token_id") or ""),
        label=str(document.get("label") or ""),
        created_at=str(document.get("created_at") or ""),
        last_used_at=document.get("last_used_at") or None,
        revoked_at=document.get("revoked_at") or None,
    )


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)  # noqa: UP017


async def issue(
    uid: str, label: str, store, now: datetime | None = None
) -> tuple[str, McpToken]:
    """Mint one token, store its hash, and hand back the plaintext once.

    Deliberately NOT best-effort. `_persist` and `save_scene` swallow their
    Firestore failures because the answer they are recording was already
    decided and losing it costs durability alone; here the write IS the answer.
    A caller who received a plaintext for a token that never landed holds a
    credential that will be refused forever, with the generic message, giving
    them nothing to act on. So this raises and the endpoint 500s, which is the
    honest report that no token was issued.
    """
    stamp = _now(now)
    token_id, secret, plaintext = mint()
    created_at = stamp.isoformat()
    await asyncio.to_thread(
        store.save,
        token_id,
        {
            # The document id is repeated as a field for the reason
            # `room_to_document` repeats `run_id`: the card's list reads
            # documents through `to_dict()`, which carries no id of its own.
            "token_id": token_id,
            "uid": uid,
            "secret_sha256": hash_secret(secret),
            "label": label,
            "created_at": created_at,
            "last_used_at": None,
            "revoked_at": None,
        },
    )
    return plaintext, McpToken(token_id=token_id, label=label, created_at=created_at)


async def list_for(uid: str, store) -> list[McpToken]:
    """Every token this account ISSUED FROM THE CARD, newest first. Metadata only.

    Filtered to card tokens rather than listing the collection, and the filter
    is load-bearing rather than cosmetic. OAuth access tokens live in the same
    collection by design (`spec-oauth-as.md`'s Decision 1: one shape, one
    lookup, one revocation path), they are minted hourly by rotation, and every
    one of them would otherwise appear on a card whose whole job is to show a
    reader the small set of credentials they chose to create. A list that grows
    by 24 rows a day per connected client is a list nobody reads, and a card
    nobody reads is a revoke button nobody finds.

    The consequence, named because it is a real gap rather than a detail: no
    surface currently lists or revokes an OAuth grant. The mechanism exists —
    `TokenStore.revoke_family` kills a whole rotation chain — and nothing calls
    it from a screen.
    """
    documents = await asyncio.to_thread(store.list_for_uid, uid)
    return [to_metadata(one) for one in documents if oauth_facts(one) is None]


async def revoke(uid: str, token_id: str, store, now: datetime | None = None) -> bool:
    """Revoke one of this account's tokens. False when it is not one."""
    return await asyncio.to_thread(store.revoke, uid, token_id, _now(now).isoformat())


# Every field that only an OAuth-issued credential carries. Presence of ANY of
# them makes a document an OAuth token, and `kind` is not required to be one of
# the three, because the question this set answers is "may this credential be
# used without an expiry check?" and the safe answer to a document nobody
# recognises is no. A document carrying `expires_at` and nothing else reads as
# OAuth and gets checked; the reverse default would let one dropped field turn
# a one-hour token into a permanent one.
_OAUTH_FIELDS = ("kind", "expires_at", "audience", "scope", "client_id", "family_id")

ACCESS = "oauth_access"
REFRESH = "oauth_refresh"


def oauth_facts(document: dict | None) -> OAuthFacts | None:
    """The OAuth half of a stored token, or None for a card token. Pure.

    Every value is read as a string with `""` for absent, so a malformed
    document reaches star/oauth/validate.py as an OAuth token with an
    unreadable expiry and an audience matching nothing — which is refused.
    Returning None on a partial document is the only alternative and it is the
    one that fails open.
    """
    document = document or {}
    if not any(document.get(field) for field in _OAUTH_FIELDS):
        return None
    return OAuthFacts(
        kind=str(document.get("kind") or ""),
        client_id=str(document.get("client_id") or ""),
        audience=str(document.get("audience") or ""),
        scope=str(document.get("scope") or ""),
        expires_at=str(document.get("expires_at") or ""),
        family_id=str(document.get("family_id") or ""),
    )


async def resolve(
    header: str | None, store, now: datetime | None = None
) -> TokenIdentity | Refusal:
    """Turn an Authorization header into an identity, or into a refusal.

    The six steps `spec.md > MCP tokens > Verification` names, in order:

      1. `extract_bearer`, reused from star/auth.py — already pure, already
         tested, and the one piece of header parsing in the project that has
         been wrong before.
      2. Split once on the dot. Wrong shape, generic refusal.
      3. One `get()` by document id. Absent, generic refusal.
      4. `hmac.compare_digest` on the hashes. Mismatch, generic refusal.
      5. `revoked_at` set, the revoked refusal.
      6. Otherwise an identity, and a throttled `last_used_at` stamp.

    `hmac.compare_digest` rather than `==` because a hash comparison's timing
    should not describe the hash. `secrets.compare_digest`, which
    star/server.py uses for the stream key, is the same function object under
    another name.

    Step 5 sits after step 4 and never before it, and that ordering is the
    whole safety argument for the distinct message: reaching it required
    presenting the correct secret. A revoked check that ran on the token id
    alone would tell anyone who guessed an id that the id was real.
    """
    presented = extract_bearer(header)
    if presented is None:
        return MISSING
    return await resolve_presented(presented, store, now=now)


async def resolve_presented(
    presented: str, store, now: datetime | None = None
) -> TokenIdentity | Refusal:
    """Steps 2 through 6, on a credential that arrived somewhere other than a header.

    Split out for exactly one caller: a refresh token arrives in a form body at
    `POST /oauth/token`, not in an Authorization header, and it is the same
    credential in the same collection resolved by the same six steps. The
    alternative was a second copy of the hash comparison and the revoked check
    inside star/oauth/tokens.py, which is how two revocation paths end up
    disagreeing about what revoked means.

    `resolve` above is unchanged in behaviour and is still the only entry point
    that can answer MISSING — a caller who hands this function an empty string
    gets the generic refusal, because at that point something WAS presented.
    """
    parts = parse(presented)
    if parts is None:
        return UNRECOGNISED
    token_id, secret = parts

    document = await asyncio.to_thread(store.get, token_id)
    if not isinstance(document, dict):
        return UNRECOGNISED

    stored_hash = document.get("secret_sha256")
    if not isinstance(stored_hash, str) or not hmac.compare_digest(
        hash_secret(secret), stored_hash
    ):
        return UNRECOGNISED

    if document.get("revoked_at"):
        return REVOKED

    uid = document.get("uid")
    if not isinstance(uid, str) or not uid:
        # A document with a matching hash and no owner is a defect in the
        # store, not a fact about the caller, so it gets the answer that
        # describes the caller's position: this token buys nothing. Checked
        # after step 5 so a store defect can never withhold the one message a
        # revoked token is owed.
        logger.warning("Token %s has no uid on its document", token_id)
        return UNRECOGNISED

    await _stamp_last_used(store, token_id, document, _now(now))
    return TokenIdentity(uid=uid, token_id=token_id, oauth=oauth_facts(document))


def _is_stale(value, now: datetime) -> bool:
    """Is this token's last_used_at old enough to be worth rewriting?

    Anything unreadable is stale: a missing stamp, a non-string, a value no
    parser recognises. A field that cannot be read is a field that has never
    usefully been written, and self-healing on the next call is better than
    leaving it wrong forever.

    A stamp from the FUTURE is stale too, which is the case worth naming. Two
    clocks that disagree would otherwise park a value ahead of real time and
    freeze the field there for as long as the difference lasts, and this
    surface reports "last used" to a reader deciding whether to revoke.
    """
    if not isinstance(value, str) or not value:
        return True
    try:
        seen = datetime.fromisoformat(value)
    except ValueError:
        return True
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)  # noqa: UP017
    age = (now - seen).total_seconds()
    return age >= _LAST_USED_THROTTLE_SECONDS or age < 0


async def _stamp_last_used(store, token_id: str, document: dict, now: datetime) -> None:
    """Record that this token was just used, at most once per 60s per token.

    The throttle reads the stored value rather than keeping a table of last
    write times in memory, and that is the cheaper design in both directions:
    the document is already in hand from step 3, so it costs no extra read, and
    the throttle survives a restart, which an in-memory table on a service
    pinned to one instance would not.

    Awaited rather than fired into a background task. It crosses
    `asyncio.to_thread` so it never blocks the loop, it happens at most once a
    minute per token, and the alternative is a bare task whose reference the
    loop is free to collect mid-write — the hazard `create_room` already holds
    a strong reference to avoid.

    Never raises. A lost stamp costs a reader one stale date on the card; a
    raised one would cost an agent the call it was making.
    """
    if not _is_stale(document.get("last_used_at"), now):
        return
    try:
        await asyncio.to_thread(store.touch, token_id, now.isoformat())
    except Exception:
        logger.exception("Failed to stamp last_used_at on token %s", token_id)
