"""OAuth access and refresh tokens, on the shape star/tokens.py already mints.

A PARALLEL MODULE, NOT A REWRITE OF star/tokens.py, and the split is by
question rather than by feature. star/tokens.py answers "is this credential
real, and has it been revoked?" — one shape, one sha256, one six-step
resolution, one revocation path — and that question is identical for a card
token and an OAuth access token. This file answers "what does an OAuth grant
turn into?", which star/tokens.py has no business knowing: authorization codes,
PKCE, rotation, and audiences are protocol, and star/tokens.py is storage.

So the only thing that changed over there is additive. `TokenIdentity` gained
one optional field carrying the five OAuth-only facts off the document
`resolve` already had in hand, and `resolve` gained a sibling that takes a
credential from somewhere other than an Authorization header, because a refresh
token arrives in a form body. Both changes leave every existing test in
tests/test_tokens.py passing unmodified, which is the constraint
`spec-oauth-as.md`'s Decision 5 puts on this whole epic: the card token is the
one credential a human can issue, read once, and paste somewhere, and
`harness/runs/*.md` are committed transcripts of it working.

ROTATION, AND WHY THE OLD TOKEN DIES. OAuth 2.1 requires refresh token rotation
for public clients, which every client here is. Redeeming a refresh token
issues a new pair and revokes the one presented. That alone denies a second
presenter; what it cannot do is say WHICH of the two presenters was the thief,
since both hold something this server issued. So a refresh token presented
after it was already rotated kills the whole family — see
`star/store.py`'s revoke_family. The legitimate client is sent back through
consent, and the attacker's freshly rotated pair dies with it. Refusing to
guess is the only correct answer available.
"""

import asyncio
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from star import config, tokens
from star.oauth import codes as authorization_codes
from star.oauth import metadata, validate

# RFC 6749's error codes for the token endpoint. `invalid_grant` covers every
# way a code or a refresh token fails, which is the point of it: a client
# cannot learn from the wire whether the code was unknown, expired, replayed,
# bound to another client, bound to another redirect URI, or failed PKCE.
# star/oauth/codes.py keeps the distinction for the log, which is where it is
# useful and where a stranger cannot read it.
INVALID_GRANT = "invalid_grant"
INVALID_REQUEST = "invalid_request"
INVALID_TARGET = "invalid_target"
SERVER_ERROR = "server_error"

# One sentence for every `invalid_grant`, for the same reason star/tokens.py
# keeps one generic refusal: a message that named which check failed would tell
# whoever is holding a stolen code exactly which part of it to change.
GRANT_REFUSED = (
    "That grant was not accepted. An authorization code is good once and for "
    "sixty seconds, and it must be redeemed by the same client, to the same "
    "redirect URI, with the code verifier that produced its challenge. Start "
    "the authorization flow again."
)

REFRESH_REFUSED = (
    "That refresh token was not accepted. Refresh tokens are rotated: each one "
    "may be used once, and using an already-rotated token ends the whole "
    "session on purpose. Start the authorization flow again."
)

WRONG_RESOURCE = (
    "This authorization server issues tokens for one resource, and the "
    "`resource` parameter did not name it. Read "
    f"{metadata.PROTECTED_RESOURCE_PATH} for the canonical URI."
)

# What appears in `label` on the stored document. The card no longer lists
# these — see star/tokens.py's `list_for` — so this is for a log line and for
# whoever opens the collection, and it exists because a document with an empty
# label and no explanation is the kind of row somebody deletes.
_LABEL_LIMIT = 60


@dataclass(frozen=True)
class Issued:
    """One freshly minted pair, and the response body it becomes."""

    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    access_token_id: str
    refresh_token_id: str
    family_id: str

    def body(self) -> dict:
        """RFC 6749 §5.1's token response.

        `token_type: "Bearer"` capitalised exactly this way. The value is
        case-insensitive per RFC 6750 and half the clients in the world compare
        it with `==` anyway.
        """
        return {
            "access_token": self.access_token,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class Denied:
    """A grant this server would not exchange. `error` is RFC 6749's code."""

    error: str
    description: str


def _label(kind: str, client_id: str) -> str:
    which = "access" if kind == tokens.ACCESS else "refresh"
    return f"OAuth {which} for {client_id}"[:_LABEL_LIMIT]


def _document(
    *,
    token_id: str,
    uid: str,
    secret: str,
    kind: str,
    client_id: str,
    audience: str,
    scope: str,
    issued: datetime,
    expires: datetime,
    family_id: str,
) -> dict:
    """One OAuth token as it is stored: the card's seven fields, plus six.

    The card's seven are unchanged and in the same order, because this document
    is read back by the same `resolve` that reads a card token's — the same
    `secret_sha256`, the same `revoked_at`, the same `last_used_at` throttle.
    `spec-oauth-as.md`'s Decision 1 is that opaque tokens on this existing
    shape beat JWTs on a deployment pinned to one instance: the one thing a JWT
    buys is stateless validation across instances, and this door already
    performs the database read on every call.
    """
    return {
        "token_id": token_id,
        "uid": uid,
        "secret_sha256": tokens.hash_secret(secret),
        "label": _label(kind, client_id),
        "created_at": issued.isoformat(),
        "last_used_at": None,
        "revoked_at": None,
        "kind": kind,
        "client_id": client_id,
        "audience": audience,
        "scope": scope,
        "expires_at": expires.isoformat(),
        "family_id": family_id,
    }


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)  # noqa: UP017


async def issue_pair(
    *,
    uid: str,
    client_id: str,
    scope: str,
    audience: str,
    store,
    family_id: str = "",
    now: datetime | None = None,
) -> Issued:
    """Mint an access token and a refresh token, and write both.

    Deliberately not best-effort, which is `star/tokens.py`'s `issue` posture
    and the same argument: a caller who received a plaintext for a token that
    never landed holds a credential that will be refused forever, with a
    message naming nothing they can act on. This raises and the endpoint 500s,
    which is the honest report that no token was issued.

    The refresh token is written first. If the second write fails, what exists
    is a refresh token nobody was handed — dead weight in a collection, and it
    expires. The other order leaves an access token live for an hour that its
    holder never received, which is worse by exactly the difference between a
    row and a credential.
    """
    stamp = _now(now)
    family = family_id or secrets.token_hex(16)
    access_seconds = config.oauth_access_token_seconds()

    minted = {}
    for kind, lifetime in (
        (tokens.REFRESH, config.oauth_refresh_token_seconds()),
        (tokens.ACCESS, access_seconds),
    ):
        token_id, secret, plaintext = tokens.mint()
        minted[kind] = (token_id, plaintext)
        await asyncio.to_thread(
            store.save,
            token_id,
            _document(
                token_id=token_id,
                uid=uid,
                secret=secret,
                kind=kind,
                client_id=client_id,
                audience=audience,
                scope=scope,
                issued=stamp,
                expires=stamp + timedelta(seconds=lifetime),
                family_id=family,
            ),
        )

    return Issued(
        access_token=minted[tokens.ACCESS][1],
        refresh_token=minted[tokens.REFRESH][1],
        expires_in=access_seconds,
        scope=scope,
        access_token_id=minted[tokens.ACCESS][0],
        refresh_token_id=minted[tokens.REFRESH][0],
        family_id=family,
    )


async def exchange_code(
    *,
    code: object,
    client_id: object,
    redirect_uri: object,
    verifier: object,
    resource: object,
    code_store,
    store,
    now: datetime | None = None,
) -> Issued | Denied:
    """`authorization_code` at `POST /oauth/token`. The whole grant, in one call.

    One function rather than three the endpoint calls in order, and that is the
    anti-footgun rather than a convenience. Redeeming the code, minting the
    pair, and recording which tokens came out of that code have to happen
    together: skipping the third leaves OAuth 2.1's answer to a replayed code
    half-built, and a half-built revocation is the kind of gap nobody notices
    until a code has already leaked.
    """
    stamp = _now(now)
    outcome = code_store.redeem(
        code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        verifier=verifier,
        now=stamp.timestamp(),
    )

    if isinstance(outcome, authorization_codes.Replayed):
        # The interception report. Everything the first exchange produced is
        # revoked before this call answers, so the window between "the code
        # leaked" and "the tokens it bought are dead" is one request.
        for token_id in outcome.token_ids:
            await asyncio.to_thread(
                store.revoke, outcome.uid, token_id, stamp.isoformat()
            )
        return Denied(INVALID_GRANT, GRANT_REFUSED)

    if isinstance(outcome, authorization_codes.Denied):
        return Denied(INVALID_GRANT, GRANT_REFUSED)

    grant = outcome.grant
    if not metadata.accepts_resource(resource):
        return Denied(INVALID_TARGET, WRONG_RESOURCE)
    if not metadata.accepts_resource(grant.resource):
        # The grant itself names a resource this server does not serve, which
        # means `/authorize` admitted something it should not have. Refused
        # here as well as there, because a token's audience is the one field
        # the whole resource-server side turns on and it must not be able to
        # arrive from a path that was checked once.
        return Denied(INVALID_TARGET, WRONG_RESOURCE)

    issued = await issue_pair(
        uid=grant.uid,
        client_id=grant.client_id,
        scope=grant.scope,
        audience=metadata.resource(),
        store=store,
        now=stamp,
    )
    code_store.bind_issued(
        outcome.receipt, (issued.access_token_id, issued.refresh_token_id)
    )
    return issued


async def refresh(
    *,
    refresh_token: object,
    client_id: object,
    store,
    now: datetime | None = None,
) -> Issued | Denied:
    """`refresh_token` at `POST /oauth/token`. Rotates, and detects reuse.

    Resolution goes through `star/tokens.py`'s `resolve_presented`, so a
    refresh token is checked by the same six steps and the same
    `hmac.compare_digest` an access token is. The alternative was a second copy
    of the hash comparison here, which is how two revocation paths end up
    disagreeing about what revoked means.

    A REVOKED answer on this path is the case worth reading twice. Reaching it
    required presenting the correct secret for a token that exists, which is
    the ordering star/tokens.py's step 5 depends on — so this is not somebody
    guessing, it is somebody holding a credential this server issued and
    already rotated. That is either the legitimate client replaying, or a thief
    using a token the client has since rotated past. There is no way to tell,
    so the family dies and both go back through consent.
    """
    stamp = _now(now)
    if not isinstance(refresh_token, str) or not refresh_token:
        return Denied(INVALID_REQUEST, REFRESH_REFUSED)

    identity = await tokens.resolve_presented(refresh_token, store, now=stamp)

    if identity is tokens.REVOKED:
        await _end_the_family(refresh_token, store, stamp)
        return Denied(INVALID_GRANT, REFRESH_REFUSED)
    if not isinstance(identity, tokens.TokenIdentity):
        return Denied(INVALID_GRANT, REFRESH_REFUSED)

    facts = identity.oauth
    if facts is None or facts.kind != tokens.REFRESH:
        # A card token or an access token presented as a refresh token. Both
        # are the wrong credential for this grant, and neither may be exchanged
        # for a new pair — a card token especially, because it is long-lived by
        # design and turning one into an OAuth session would launder a
        # credential the reader issued for a different purpose.
        return Denied(INVALID_GRANT, REFRESH_REFUSED)
    if validate.expired(facts.expires_at, stamp):
        return Denied(INVALID_GRANT, REFRESH_REFUSED)
    if client_id is not None and client_id != "" and client_id != facts.client_id:
        # The client id is optional on a refresh request from a public client,
        # since there is no secret to check it against. When it IS sent it has
        # to be right: a client sending somebody else's id is either confused
        # or probing.
        return Denied(INVALID_GRANT, REFRESH_REFUSED)

    issued = await issue_pair(
        uid=identity.uid,
        client_id=facts.client_id,
        scope=facts.scope,
        audience=facts.audience,
        store=store,
        family_id=facts.family_id,
        now=stamp,
    )
    # Revoked AFTER the new pair is written, not before. The other order leaves
    # a client with nothing at all if the mint fails: its only credential is
    # dead and the replacement never existed. This order's failure mode is one
    # extra live refresh token for the length of one request, which the next
    # rotation kills.
    await asyncio.to_thread(
        store.revoke, identity.uid, identity.token_id, stamp.isoformat()
    )
    return issued


async def _end_the_family(refresh_token: str, store, now: datetime) -> None:
    """Kill every token in the rotation chain a reused refresh token belongs to.

    Costs one extra read, on this path only. `resolve_presented` answered
    REVOKED, which carries no document, and the family id is on the document —
    so it is fetched again by the id in the token that was just presented. Safe
    to do: reaching REVOKED required the hash to match, so this read is about a
    credential the caller demonstrably held.

    Silent on failure. A store that cannot answer here has already refused the
    refresh, so the caller is denied either way; raising would turn a denial
    into a 500 and tell a client to retry something that must not succeed.
    """
    parts = tokens.parse(refresh_token)
    if parts is None:
        return
    try:
        document = await asyncio.to_thread(store.get, parts[0])
        family_id = (document or {}).get("family_id")
        if family_id:
            await asyncio.to_thread(store.revoke_family, family_id, now.isoformat())
    except Exception:  # noqa: BLE001
        return
