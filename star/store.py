"""Firestore persistence. The only module in the project that touches it.

Document shaping is pure and lives at the top of this file; the RoomStore
adapter underneath is a thin wrapper over the client so the shaping can be
tested without a network. The server owns all access — the browser never
talks to Firestore directly, which leaves exactly one security boundary to
get right instead of two.

Schema:
    /users/{uid}/rooms/{run_id}
"""

import os

from google.api_core.exceptions import NotFound

_UNTITLED = "Untitled room"


def room_to_document(run_id: str, result: dict, status: str, created_at: str) -> dict:
    """Shape a finished run into its stored document. Pure."""
    result = result or {}
    profile = result.get("story_profile") or {}
    return {
        "run_id": run_id,
        "status": status,
        "created_at": created_at,
        "title": profile.get("title") or _UNTITLED,
        "era": profile.get("era") or "",
        "genre": profile.get("genre") or "",
        "story_profile": profile,
        "research_plan": result.get("research_plan"),
        "research_bible": result.get("research_bible") or "",
        "search_count": result.get("search_count") or 0,
        "source_count": result.get("source_count") or 0,
        "categories": result.get("categories") or {},
    }


def document_to_room(doc: dict) -> dict:
    """Rebuild the API's room payload from a stored document. Pure."""
    doc = doc or {}
    return {
        "story_profile": doc.get("story_profile") or {},
        "research_plan": doc.get("research_plan"),
        "research_bible": doc.get("research_bible") or "",
        "search_count": doc.get("search_count") or 0,
        "source_count": doc.get("source_count") or 0,
        "categories": doc.get("categories") or {},
    }


def room_summary(doc: dict) -> dict:
    """The small shape the project rail lists. Pure.

    Deliberately excludes the bible and the categories: a rail listing twenty
    rooms should not carry twenty research bibles across the wire.
    """
    doc = doc or {}
    return {
        "run_id": doc.get("run_id"),
        "title": doc.get("title") or _UNTITLED,
        "era": doc.get("era") or "",
        "status": doc.get("status") or "unknown",
        "created_at": doc.get("created_at") or "",
        "search_count": doc.get("search_count") or 0,
    }


class RoomStore:
    """Reads and writes rooms under /users/{uid}/rooms/{run_id}."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google.cloud import firestore

            self._client = firestore.Client(
                project=os.environ.get("GOOGLE_CLOUD_PROJECT")
            )
        return self._client

    def _rooms(self, uid: str):
        # A single slash-delimited path, not chained .document().collection()
        # calls: Client.collection() accepts either form, and the single-path
        # form is what keeps this working against a hand-written fake whose
        # document objects don't implement .collection().
        return self.client.collection(f"users/{uid}/rooms")

    def save(self, uid: str, run_id: str, document: dict) -> None:
        self._rooms(uid).document(run_id).set(document)

    def get(self, uid: str, run_id: str) -> dict | None:
        snapshot = self._rooms(uid).document(run_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_rooms(self, uid: str) -> list[dict]:
        docs = [s.to_dict() for s in self._rooms(uid).stream() if s.exists]
        docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        return [room_summary(d) for d in docs]

    def mark_interrupted(self, uid: str, run_id: str) -> bool:
        """A run left 'running' with no live task did not survive a restart.

        Returns True when it marked the document, False when the document
        was already gone. `.update()` raises `NotFound` in that case —
        verified against real Firestore — and get_room only calls this after
        its own read already succeeded, so a delete racing between that read
        and this update is the one case this catches; any other error is a
        genuine failure and is left to propagate.
        """
        try:
            self._rooms(uid).document(run_id).update({"status": "interrupted"})
            return True
        except NotFound:
            return False
