"""Firebase ID token verification.

The browser signs in anonymously and sends its ID token as a bearer
credential. This module turns that header into a uid, or into None. It never
raises on bad input: a forged token and a missing header are the same
non-event, and the caller decides the HTTP consequence.

Header parsing is separated from verification so the parsing — the part most
likely to be subtly wrong — is testable without a network.
"""

import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

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
    except Exception:  # noqa: BLE001
        # Forged, expired, malformed, or the cert fetch failed. All the same
        # answer to the caller: we do not know who this is.
        return None
    if not isinstance(claims, dict):
        return None
    uid = claims.get("uid")
    return uid or None
