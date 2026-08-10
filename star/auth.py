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
        # The exception type and message, at warning level, on the server's own
        # log. Not the token, and nothing reaches the client: the return value
        # below is unchanged, so this is a diagnostic, not a behaviour change.
        logger.warning("ID token verification failed: %s: %s", type(exc).__name__, exc)
        return None
    if not isinstance(claims, dict):
        return None
    uid = claims.get("uid")
    return uid or None
