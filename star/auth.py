"""Firebase ID token verification.

The browser signs in anonymously and sends its ID token as a bearer
credential. This module turns that header into a uid, or into None. It never
raises on bad input: a forged token and a missing header are the same
non-event, and the caller decides the HTTP consequence.

Header parsing is separated from verification so the parsing — the part most
likely to be subtly wrong — is testable without a network.

One caller needs more than the uid. Issuing an MCP token to an account whose
only proof of ownership is a `localStorage` entry would be issuing a
credential nobody can recover, so `verify_claims` returns the whole verified
claim set and `linked_provider` reads the one question that refusal actually
turns on.
"""

import logging
import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None

# Ceiling on any exception detail this module is willing to write. See
# _failure_detail for why a ceiling is needed at all.
_DETAIL_LIMIT = 200


def _get_app() -> firebase_admin.App:
    """Initialize lazily; Application Default Credentials locally, the
    service account on Cloud Run."""
    global _app
    if _app is None:
        project = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get(
            "GOOGLE_CLOUD_PROJECT"
        )
        _app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(), {"projectId": project}
        )
    return _app


def _verify(token: str) -> dict:
    """Seam for tests. Real verification hits Google's public certs."""
    return firebase_auth.verify_id_token(token, app=_get_app())


def _failure_detail(exc: Exception) -> str:
    """How much of a verification failure is safe to write to the log.

    THE TYPE, ALWAYS. It is also most of what the log was added for:
    `CertificateFetchError` (our cert fetch failed) and `InvalidIdTokenError` /
    `ExpiredIdTokenError` (their token is bad) are the distinction three tasks
    of an intermittent 401 could not make.

    THE MESSAGE, ONLY FROM `CertificateFetchError`. Verified against the
    vendored libraries rather than assumed, because the first cut of this logged
    `str(exc)` unconditionally and that is not credential-free:

      firebase_admin/_token_gen.py:411  _decode_unverified calls
        google.auth.jwt.decode_header(token), catches ValueError, and re-raises
        it as InvalidIdTokenError(str(error)) — message preserved verbatim.
      google/auth/jwt.py:148  formats the WHOLE TOKEN into
        "Wrong number of segments in token: {0}".
      google/auth/jwt.py:126, :161  format decoded segment bytes and the raw
        encoded header into "Can't parse segment: {0}" and "Header segment
        should be a JSON object: {0}".

    Measured end to end: `Authorization: Bearer supersecret-not-a-jwt` produces
    InvalidIdTokenError("Wrong number of segments in token:
    b'supersecret-not-a-jwt'"), and `extract_bearer` waves through any two
    whitespace-separated parts, so a stranger picks the bytes.

    Two things that measurement also corrected, in both directions. A VALID
    Firebase ID token has two dots and reaches the signature check, so a
    replayable credential effectively cannot arrive by this route — this is not
    a credential leak. But the input is echoed verbatim and unbounded: 448 bytes
    in produced a 488-character message, and a large header would produce a
    proportionally large log line on a public endpoint. Newline injection is
    weaker than it first looks — every one of the three paths above formats a
    `bytes`, and `repr` escapes control characters, so a literal newline did not
    survive in any case tried. That is the library's incidental behaviour, not a
    guarantee, so the sanitiser below strips them anyway.

    `CertificateFetchError` is the exception to the exception: _token_gen.py:405
    builds it from a `google.auth.exceptions.TransportError` raised while
    fetching the certs URL, so its message describes our own HTTP failure and
    never sees the token. It is also the message actually worth having — the
    suspected cause of the 401 this whole diagnostic exists for. It is still
    stripped and truncated: one guard is a claim about a library, two are a
    property of this function.

    An unknown type degrades to the safe side — the name, and nothing else.
    """
    if not isinstance(exc, firebase_auth.CertificateFetchError):
        return ""
    detail = " ".join(str(exc).split())
    if len(detail) > _DETAIL_LIMIT:
        detail = detail[:_DETAIL_LIMIT] + "…"
    return detail


def extract_bearer(header: str | None) -> str | None:
    """Pull the credential out of an Authorization header. Pure."""
    if not header:
        return None
    parts = header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    return parts[1]


def verify_claims(header: str | None) -> dict | None:
    """Return the caller's verified claim set, or None.

    The whole of what `verify_token` used to be, minus the last line. It is
    split out because one caller needs more than the uid: `POST /api/tokens`
    refuses to issue a credential to an account nobody can recover, and
    whether an account is recoverable is a claim, not a uid — see
    `linked_provider` below.

    Contract unchanged and load-bearing: never raises, one log line per
    verification failure, None for every way a header can be wrong. A claim
    set with no uid is None too, so `verify_token` below stays a field read
    rather than a second set of rules.
    """
    token = extract_bearer(header)
    if token is None:
        return None
    try:
        claims = _verify(token)
    except Exception as exc:  # noqa: BLE001
        # Forged, expired, malformed, or verification itself failed. All the
        # same ANSWER to the caller — we do not know who this is, and telling a
        # stranger which of those it was is free reconnaissance. But they are
        # not the same EVENT, and until Task 7 nothing anywhere recorded which
        # one had happened.
        #
        # That gap cost three tasks. An intermittent 401 on a cold `GET
        # /api/rooms` has been in the ledger since Task 2, explained as a
        # propagation lag on a too-new token. Task 7 measured that directly and
        # it is false: a token sent at an age of 0ms is accepted, five times out
        # of five. So the refusal is very likely raised HERE, by verification
        # failing transiently rather than by a bad token — and nobody could see
        # that, because this branch discarded the only evidence.
        #
        # The exception TYPE, at warning level, on the server's own log, and a
        # message only where a message is provably free of the caller's own
        # bytes — see _failure_detail, which is where the first cut of this got
        # it wrong. Nothing reaches the client: the return value below is
        # unchanged, so this is a diagnostic, not a behaviour change.
        detail = _failure_detail(exc)
        logger.warning(
            "ID token verification failed: %s%s",
            type(exc).__name__,
            f": {detail}" if detail else "",
        )
        return None
    if not isinstance(claims, dict):
        return None
    return claims if claims.get("uid") else None


def verify_token(header: str | None) -> str | None:
    """Return the caller's uid, or None if the header is absent or invalid."""
    claims = verify_claims(header)
    return claims["uid"] if claims else None


def linked_provider(claims: dict | None) -> str | None:
    """The federated account attached to this uid, or None.

    THE QUESTION IS NOT "HOW DID THIS SESSION SIGN IN." `POST /api/tokens`
    refuses an anonymous account, and `spec.md > The card` names that check as
    `firebase.sign_in_provider == "anonymous"`. The reason `prd.md` gives for
    the refusal is narrower than that field: an anonymous account's only proof
    of ownership is a `localStorage` entry, so a long-lived token pointing at
    one is a credential to an account nobody can recover. What makes an
    account recoverable is a federated identity being ATTACHED to it, and
    `firebase.identities` is where that is recorded.

    UNMEASURED, AND BUILT FOR BOTH ANSWERS. Nobody has yet read the claim set
    of a real Firebase ID token minted after an anonymous session linked a
    Google credential through `accounts:signInWithIdp`. Two shapes are
    possible and the difference is not cosmetic:

      A. Linking flips `firebase.sign_in_provider` to "google.com". Either
         field admits the account and the spec's check works as written.
      B. `sign_in_provider` keeps describing how THIS session began and stays
         "anonymous", while `firebase.identities` gains a "google.com" entry.
         A guard reading `sign_in_provider` alone then refuses exactly the
         linked accounts it exists to admit, and does so silently until
         somebody tries to mint a token.

    So identities is read first and sign_in_provider is the fallback, which is
    correct under A and under B. B is the shape `web/auth.js`'s
    `linkedProvider()` already assumes, and the two have to agree: a card
    drawing "attached to a Google account" over a server refusing to issue a
    token is the worst failure available here, because both halves look like
    they are working. When the claim shape is finally measured, this becomes a
    confirmation rather than a change.

    The dot is the whole of the provider rule, verbatim from `web/auth.js`:
    Firebase keys a federated identity by the provider's domain — google.com,
    apple.com, github.com — and keys the two non-federated ones as plain
    "email" and "phone". Values are not inspected, matching the browser
    exactly. A dotted key with an empty value is not a shape Firebase emits,
    and a server stricter than the browser is a false refusal on a real
    account, which is the failure this function exists to prevent.
    """
    firebase = (claims or {}).get("firebase")
    if not isinstance(firebase, dict):
        return None
    identities = firebase.get("identities")
    if isinstance(identities, dict):
        for key in identities:
            if isinstance(key, str) and "." in key:
                return key
    sign_in = firebase.get("sign_in_provider")
    if isinstance(sign_in, str) and sign_in and sign_in != "anonymous":
        return sign_in
    return None
