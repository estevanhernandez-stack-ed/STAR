"""Authorization codes: single-use, 60 seconds, bounded, in memory.

`spec-oauth-as.md`'s Decision 2 is what this file implements, and it names its
own cost rather than hiding it: a deploy or a restart inside the roughly thirty
seconds between the redirect and the token exchange drops the code, and the
reader starts the flow again. The alternative is a Firestore write and a
Firestore read on a path that is already two round trips, to protect a window
that closes in under a minute.

The bound and the stale sweep are star/guards.py's RateLimiter posture, copied
deliberately and for the same documented reason: the sweep is O(n) in the
number of tracked keys and runs on a single-threaded event loop shared with
every other request and every open SSE stream on the instance, so the number of
tracked keys is a cost every caller pays rather than only the one adding a key.
A store that cannot afford to track another code refuses to issue one instead
of growing past what it can afford.

This is in-memory state, so the same sentence star/guards.py ends on applies
here: it is correct only under `--max-instances=1` AND `--min-instances=1`
together. If anyone raises the instance count, `_runs`, both limiters, and this
move to a shared store in the same change, not after.

WHAT A SECOND REDEMPTION MEANS. OAuth 2.1 requires the server to deny it and
says it SHOULD revoke every token already issued from that code. That is not
bookkeeping: the only way one code is presented twice is that somebody other
than the client that requested it got hold of it, so the second presentation is
an interception report. This store keeps enough to act on one — which token ids
came out of the first exchange — and star/oauth/tokens.py revokes them.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field

from star.oauth import pkce

# `spec-oauth-as.md`'s number. Sixty seconds is long enough for a browser to
# follow a redirect and a client to POST once, and short enough that a code
# sitting in a shell history, a proxy log, or a URL bar is dead before anyone
# reads it. It is a constant rather than an env var because it is a security
# parameter, and a parameter that can be widened by setting a variable will be.
TTL_SECONDS = 60

# 256 bits, from the same CSPRNG star/tokens.py mints with. A code is a bearer
# credential for the whole of what the consent screen just approved, so it gets
# a credential's entropy rather than an identifier's.
_CODE_BYTES = 32

# The three ways a redemption is refused that are NOT a replay. All three are
# `invalid_grant` on the wire — one error code, so a client cannot use the
# difference to learn whether a code it holds is real — and these strings exist
# for the server's own log, which is where the distinction is worth having.
UNKNOWN = "unknown"
EXPIRED = "expired"
CLIENT_MISMATCH = "client_mismatch"
REDIRECT_MISMATCH = "redirect_mismatch"
PKCE_FAILED = "pkce_failed"
REPLAYED = "replayed"


@dataclass(frozen=True)
class Grant:
    """What one consent approved, held until the code is exchanged for it.

    `resource` is here because RFC 8707 binds it at the authorization request
    and the token endpoint must not widen it: a client that asked for a token
    for one resource and received one for another has been handed a credential
    it did not ask for. `code_challenge` is here because PKCE binds the
    exchange to the client that started the flow, and `redirect_uri` because
    the exchange must prove it is the same request.
    """

    uid: str
    client_id: str
    redirect_uri: str
    scope: str
    code_challenge: str
    resource: str


@dataclass(frozen=True)
class Redeemed:
    """The allow answer, plus the handle for recording what it produced.

    `receipt` is the store's internal key for this code — the sha256 of it, so
    it is not itself a credential and may be logged. Handing it back rather
    than asking the caller for the plaintext a second time keeps the code
    itself from travelling any further than the one function that parsed it.
    """

    grant: Grant
    receipt: str


@dataclass(frozen=True)
class Denied:
    """A redemption that produced nothing. `reason` is for the log, not the wire."""

    reason: str


@dataclass(frozen=True)
class Replayed:
    """A code presented a second time, and what the first time produced.

    A separate outcome from Denied because the caller owes it more than a
    refusal: `token_ids` are the credentials issued on the first exchange, and
    OAuth 2.1 says they should not survive the discovery that the code leaked.
    `uid` comes along because revoking a token is scoped to its owner.
    """

    uid: str
    token_ids: tuple[str, ...]


@dataclass
class _Entry:
    grant: Grant
    issued_at: float
    spent: bool = False
    token_ids: tuple[str, ...] = field(default_factory=tuple)


def _receipt(code: str) -> str:
    """The dict key for one code: its sha256, never the code itself.

    In-memory only, so this is not the durability argument star/tokens.py makes
    for hashing what goes to Firestore. It is the exposure argument: a
    traceback, a debugger, or a `repr` of this object prints its keys, and a
    key that is a live credential is a credential in a crash report. The lookup
    that follows is a dict lookup rather than a comparison, so nothing here
    needs to be constant-time — see `redeem` for the one comparison that does.
    """
    return hashlib.sha256(code.encode()).hexdigest()


class CodeStore:
    """Every authorization code this instance has issued and not yet forgotten."""

    def __init__(self, ttl_seconds: float = TTL_SECONDS, max_keys: int = 5000) -> None:
        self._ttl = ttl_seconds
        self._max_keys = max_keys
        self._entries: dict[str, _Entry] = {}

    def _sweep(self, now: float) -> None:
        """Drop every code past its TTL, spent or not.

        One dict and one lifetime for both states, rather than a live table and
        a longer-lived tombstone table. A spent entry is what makes a replay
        detectable, and it stops being worth keeping at exactly the moment the
        code would have expired anyway: past the TTL both a replay and a first
        use are refused, so the only thing a longer tombstone buys is the
        ability to call the refusal `replayed` instead of `unknown`. That is a
        log line, and it is not worth a second unbounded structure.
        """
        cutoff = now - self._ttl
        for key in list(self._entries):
            if self._entries[key].issued_at <= cutoff:
                del self._entries[key]

    def issue(self, grant: Grant, now: float | None = None) -> str | None:
        """Mint one code for one approved consent, or None when full.

        None rather than an exception, and rather than growing: a store already
        at capacity that accepts one more lets a caller spraying `/authorize`
        make the O(n) sweep above cost more on every future call, for everyone,
        including the flows already in flight. RateLimiter refuses the same way
        for the same reason. The endpoint turns None into a refusal naming the
        server as the cause, because it is.
        """
        now = time.time() if now is None else now
        self._sweep(now)
        if len(self._entries) >= self._max_keys:
            return None
        code = secrets.token_hex(_CODE_BYTES)
        self._entries[_receipt(code)] = _Entry(grant=grant, issued_at=now)
        return code

    def redeem(
        self,
        code: object,
        *,
        client_id: object,
        redirect_uri: object,
        verifier: object,
        now: float | None = None,
    ) -> Redeemed | Denied | Replayed:
        """Spend one code, once.

        The order is the argument. Absent and expired come first because both
        mean there is nothing here to burn. Everything after them burns the
        code before it is checked, which is the deliberate call: a caller
        holding a real code either requested it or intercepted it, since 256
        bits are not guessed, so refusing to spend it on a failed check would
        leave an intercepted code alive for the interceptor to retry with a
        better guess at the client id. The cost is that an interceptor who gets
        one wrong attempt in first also denies the legitimate client — which is
        a flow the reader restarts, against a flow that was already
        compromised.

        PKCE is checked last and is the only comparison here that is
        constant-time, because it is the only one against a value derived from
        a secret. `client_id` and `redirect_uri` are public strings that
        travelled in a query string, and comparing them in constant time would
        imply they were something they are not.
        """
        now = time.time() if now is None else now
        self._sweep(now)

        if not isinstance(code, str) or not code:
            return Denied(UNKNOWN)
        entry = self._entries.get(_receipt(code))
        if entry is None:
            # Either never issued, or issued and swept. The sweep runs above,
            # so an expired code is indistinguishable from an invented one
            # here, and both get the same wire answer regardless.
            return Denied(UNKNOWN)
        if entry.issued_at + self._ttl <= now:
            # Unreachable while `_sweep` uses the same cutoff, and kept anyway:
            # the two must agree, and a TTL check that lives only inside the
            # sweep is a TTL that a future change to the sweep can remove
            # without anything failing.
            return Denied(EXPIRED)
        if entry.spent:
            return Replayed(uid=entry.grant.uid, token_ids=entry.token_ids)

        entry.spent = True
        grant = entry.grant
        if client_id != grant.client_id:
            return Denied(CLIENT_MISMATCH)
        if redirect_uri != grant.redirect_uri:
            return Denied(REDIRECT_MISMATCH)
        if not pkce.verify(verifier, grant.code_challenge):
            return Denied(PKCE_FAILED)
        return Redeemed(grant=grant, receipt=_receipt(code))

    def bind_issued(self, receipt: str, token_ids: tuple[str, ...]) -> None:
        """Record which credentials one exchange produced.

        Called immediately after the tokens are written, by the one function
        that does both — see star/oauth/tokens.py's `exchange_code`. Skipping
        it does not break the flow, and that is exactly why it does not live in
        the caller's hands: what it costs is the revocation half of OAuth 2.1's
        answer to a replayed code, which is the half nobody notices missing
        until a code has already leaked.
        """
        entry = self._entries.get(receipt)
        if entry is not None:
            entry.token_ids = tuple(token_ids)

    def is_spent(self, code: str) -> bool:
        """Whether a code has already been redeemed. Diagnostics and tests."""
        entry = self._entries.get(_receipt(code))
        return entry is not None and entry.spent

    def __len__(self) -> int:
        return len(self._entries)
