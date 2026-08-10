"""Firebase ID token verification.

The browser signs in anonymously and sends its ID token as a bearer
credential. This module turns that header into a uid, or into None. It never
raises on bad input: a forged token and a missing header are the same
non-event, and the caller decides the HTTP consequence.

Header parsing is separated from verification so the parsing — the part most
likely to be subtly wrong — is testable without a network.
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


def verify_token(header: str | None) -> str | None:
    """Return the caller's uid, or None if the header is absent or invalid."""
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
    uid = claims.get("uid")
    return uid or None
