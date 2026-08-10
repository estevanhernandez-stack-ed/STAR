"""Firestore persistence. The only module in the project that touches it.

Document shaping is pure and lives at the top of this file; the RoomStore
adapter underneath is a thin wrapper over the client so the shaping can be
tested without a network. The server owns all access — the browser never
talks to Firestore directly, which leaves exactly one security boundary to
get right instead of two.

Schema:
    /users/{uid}/rooms/{run_id}
    /users/{uid}/rooms/{run_id}/scenes/{scene_id}

Filed checks hang off the room they were checked against, as a subcollection
rather than a field on the room. Three reasons, in order: a room is read on
every rail click and a scene is 8,000 characters plus its claims, so keeping
them apart is what stops a room read paying for every check ever run against
it; `.set()` replaces a whole document, so checks living inside the room
document would be rewritten by every `_persist` call a late-finishing build
makes; and deleting one check has to be one delete, because the scene text is
disclosed as deletable and a read-modify-write of a shared document can lose a
concurrent write.
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
    """Rebuild the API's room payload from a stored document. Pure.

    `created_at` is here and not only in `room_summary` because the room view
    stamps it on every citation receipt as the day those sources came back
    from a search (web/clip.js's `RET <date>`). It was dropped from this shape
    until Task 6, which left the signature stamp two thirds complete: the
    browser had a filed date for the drawer and no retrieval date for the
    sources, and web/drawer.js deliberately refuses to substitute one for the
    other. A room's creation is when its searches ran, so this is the honest
    source for that claim and there is no other one on the wire.

    Left as "" when the document has none — an older document written before
    Task 1 added the field. The client drops the RET line rather than filling
    it, which is the whole reason this is a real value and not a default.
    """
    doc = doc or {}
    return {
        "created_at": doc.get("created_at") or "",
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


def scene_to_document(result: dict, scene: str) -> dict:
    """Shape one finished check into its stored document. Pure.

    `scene_id` and `created_at` are read off the result rather than minted
    here, for the reason `_persist` records at length for a room: a second
    clock in the write path is how a stamped date drifts away from the answer
    it belongs to. `star/verdicts.py` took both once, from the server, and
    this write is downstream of that.

    The scene text is the one field a room's own document has no equivalent
    of. It is stored because a filed check has to render the marked scene
    again without re-running the pipeline, and the claims are exact substrings
    of the scene rather than offsets into it — without the text they are a
    list of quotations with nowhere to sit. It is deletable for the same
    reason it is disclosed: it is a writer's script pages, which is strictly
    more sensitive than the treatment the intake copy promises not to keep.
    """
    result = result or {}
    return {
        "scene_id": result.get("scene_id") or "",
        "created_at": result.get("created_at") or "",
        "scene": scene,
        "claims": result.get("claims") or [],
        "parse_rate": result.get("parse_rate") or 0.0,
        "unsourced_count": result.get("unsourced_count") or 0,
        "field_notes": result.get("field_notes") or "",
        "search_count": result.get("search_count") or 0,
        "budget_exhausted": bool(result.get("budget_exhausted")),
        "cover_note": result.get("cover_note") or "",
    }


def document_to_scene(doc: dict) -> dict:
    """Rebuild the API's check payload from a stored document. Pure.

    Deliberately the same shape the check returned when it ran, scene text
    included. A filed check is replayable, and replay means the surface draws
    the same marked scene from the same fields — one shape for both, so no
    client ever has to know which of the two answered it.
    """
    doc = doc or {}
    return {
        "scene_id": doc.get("scene_id") or "",
        "created_at": doc.get("created_at") or "",
        "scene": doc.get("scene") or "",
        "claims": doc.get("claims") or [],
        "parse_rate": doc.get("parse_rate") or 0.0,
        "unsourced_count": doc.get("unsourced_count") or 0,
        "field_notes": doc.get("field_notes") or "",
        "search_count": doc.get("search_count") or 0,
        "budget_exhausted": bool(doc.get("budget_exhausted")),
        "cover_note": doc.get("cover_note") or "",
    }


def scene_summary(doc: dict) -> dict:
    """The small shape the room's list of filed checks carries. Pure.

    Excludes the scene text and the claims for the reason `room_summary`
    excludes the bible: a room with twenty filed checks would otherwise send
    twenty scenes across the wire to draw a list. `claim_count` is here
    because it is the one thing a reader wants from a list that none of the
    remaining fields carry.
    """
    doc = doc or {}
    return {
        "scene_id": doc.get("scene_id"),
        "created_at": doc.get("created_at") or "",
        "claim_count": len(doc.get("claims") or []),
        "search_count": doc.get("search_count") or 0,
        "unsourced_count": doc.get("unsourced_count") or 0,
        "budget_exhausted": bool(doc.get("budget_exhausted")),
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

    def _scenes(self, uid: str, run_id: str):
        # One slash-delimited path for the same reason `_rooms` uses one: the
        # chained .document().collection() form needs a document object that
        # implements .collection(), which the hand-written fake in
        # tests/test_store.py does not.
        return self.client.collection(f"users/{uid}/rooms/{run_id}/scenes")

    def save_scene(self, uid: str, run_id: str, scene_id: str, document: dict) -> None:
        self._scenes(uid, run_id).document(scene_id).set(document)

    def get_scene(self, uid: str, run_id: str, scene_id: str) -> dict | None:
        snapshot = self._scenes(uid, run_id).document(scene_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_scenes(self, uid: str, run_id: str) -> list[dict]:
        docs = [s.to_dict() for s in self._scenes(uid, run_id).stream() if s.exists]
        docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        return [scene_summary(d) for d in docs]

    def delete_scene(self, uid: str, run_id: str, scene_id: str) -> bool:
        """Remove one filed check, and with it the scene text it stored.

        Returns False when there was nothing there. Firestore's `.delete()` is
        idempotent and reports nothing about what it removed, so the read
        ahead of it is the only way this can answer honestly — and it has to
        answer honestly, because the endpoint above turns False into the same
        404 an unknown room gets. A delete that always reported success would
        tell a writer their pages were gone on a scene_id that was never
        theirs, which is the one promise on this surface that has to hold.

        A room belonging to another uid never reaches the delete: the path is
        rooted at `users/{uid}`, so the read finds nothing and this returns
        False by construction rather than by an ownership check.
        """
        document = self._scenes(uid, run_id).document(scene_id)
        if not document.get().exists:
            return False
        document.delete()
        return True
