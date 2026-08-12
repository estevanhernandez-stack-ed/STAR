"""Firestore persistence. The only module in the project that touches it.

Document shaping is pure and lives at the top of this file; the RoomStore
adapter underneath is a thin wrapper over the client so the shaping can be
tested without a network. The server owns all access — the browser never
talks to Firestore directly, which leaves exactly one security boundary to
get right instead of two.

Schema:
    /users/{uid}/rooms/{run_id}
    /users/{uid}/rooms/{run_id}/scenes/{scene_id}
    /mcp_tokens/{token_id}

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
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import FieldFilter

_UNTITLED = "Untitled room"


def _retention_cutoff() -> str:
    """The ISO instant a deleted room stops being recoverable.

    Compared as a STRING against `deleted_at`, which is safe only because every
    timestamp this project writes is `datetime.now(timezone.utc).isoformat()` —
    same length, same offset, so lexical order is chronological order. Anything
    that starts writing a different format breaks the comparison silently, which
    is why this reads from the same clock rather than parsing what it finds.
    """
    from star import config

    days = config.room_retention_days()
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()  # noqa: UP017


_client = None


def _default_client():
    """The one Firestore client this process uses, built on first need.

    Lazy for the reason the property below was lazy before there were two
    stores: `star/server.py` constructs its stores at import time, and every
    test in the suite injects a fake instead — building a real client at import
    would put a network dependency in front of a suite that has none. Shared
    because two stores in one process should not mean two gRPC channels; both
    classes below still take a client for injection, and only fall through to
    this when they were given none.
    """
    global _client
    if _client is None:
        from google.cloud import firestore

        _client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    return _client


def room_to_document(
    run_id: str,
    result: dict,
    status: str,
    created_at: str,
    *,
    spent: dict | None = None,
    note: str = "",
) -> dict:
    """Shape a finished run into its stored document. Pure.

    `spent` carries what the RUN cost, separately from what it produced, and it
    exists because a failed build has no `result` to read a cost off. Without
    it a room that spent a dozen live searches and a slot of the shared daily
    budget was stored with `search_count: 0` — the department charging for
    work and then filing a document saying it did none. The counts are the
    run's own, so they are right on every branch rather than only on the ones
    that reached a result.

    `note` is the same argument applied to the account rather than the cost. A
    run that ends badly already explains itself in plain language — the
    timeout branch names the ceiling, the failure branch says the details are
    in the server log — but it explains itself down the SSE stream, which is
    gone the moment the tab is. What persisted was `status: "error"` and
    nothing else, so a writer returning to the rail the next morning, or any
    agent calling `get_room`, found a room that had failed and would not say
    why. The department charging for work and then declining to account for
    it is the same failure `spent` was added to fix, one field over.

    Only the language already written for a stranger goes in here. The
    exception type and the stack vocabulary stay in the server log where
    star/server.py's error branches deliberately put them: this string is read
    by a browser and by an agent, and it was public copy before it was stored.
    """
    result = result or {}
    spent = spent or {}
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
        "search_count": spent.get("search_count", result.get("search_count") or 0),
        "source_count": spent.get("source_count", result.get("source_count") or 0),
        "categories": result.get("categories") or {},
        # What the editor said about its own turn. Stored because it cannot be
        # recovered afterwards: a bible that was cut off looks, in the text,
        # exactly like a bible about a thin subject, and every diagnosis of one
        # before this was inference from headings weeks after the fact.
        "bible_finish_reason": result.get("bible_finish_reason") or "",
        "bible_tokens": result.get("bible_tokens") or {},
        # Which room this one follows. Empty at build: a story becomes a story
        # when its writer says so, not when the department guesses from two
        # treatments sharing a decade.
        "continues": "",
        # Why this room ended the way it did, when that needs saying. Empty on
        # a room that finished: a complete build's account of itself is the
        # research, and a note there would be a label on a door that is open.
        "note": note or "",
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
        "bible_finish_reason": doc.get("bible_finish_reason") or "",
        "bible_tokens": doc.get("bible_tokens") or {},
        "continues": doc.get("continues") or "",
        "note": doc.get("note") or "",
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
        # Here rather than only in the full room, because the rail groups on it.
        # Reading twenty rooms whole to draw a list of twenty is the exact cost
        # this shape exists to avoid.
        "continues": doc.get("continues") or "",
        # For the same reason, one layer along: a rail that shows a room as
        # failed and makes the reader open it to learn why has moved the
        # explanation somewhere they have to go looking for it.
        "note": doc.get("note") or "",
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
        # Persisted for the same reason the claims are. A replayed check that
        # dropped this would read CLEANER than the one that ran, which is the
        # exact failure the note exists to prevent, arriving a day later.
        "scope_note": result.get("scope_note") or "",
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
        "scope_note": doc.get("scope_note") or "",
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
            self._client = _default_client()
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
        """Every room this writer can still see, and the moment expired ones go.

        A deleted room leaves this list immediately — that is the whole point of
        the delete, and a workspace that still shows what you removed has not
        removed it. The document survives for `config.room_retention_days()` so
        the delete can be taken back, and is destroyed here once it cannot.

        The purge is lazy, on the read, rather than scheduled. It follows the
        precedent star/server.py's `_evict_old_runs` already sets for the same
        reason: this app deploys to Cloud Run at `--min-instances=1` with no
        scheduler, and a sweep that only runs when someone looks is one less
        moving part than a cron that has to be deployed, monitored and paid for.

        The honest cost of that choice, stated rather than buried: **a writer
        who never lists their rooms never purges them.** Their deleted rooms sit
        in Firestore past the window. Nothing about that is visible to them or
        chargeable to anyone else, and the alternative is infrastructure this
        project does not otherwise need — but it is a real difference between
        "gone in thirty days" and "gone the next time you look after thirty
        days", and the copy must not promise the first.
        """
        docs = [s.to_dict() for s in self._rooms(uid).stream() if s.exists]

        cutoff = _retention_cutoff()
        live = []
        for doc in docs:
            deleted_at = doc.get("deleted_at") or ""
            if not deleted_at:
                live.append(doc)
            elif deleted_at < cutoff:
                self.purge_room(uid, doc.get("run_id") or "")

        live.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        return [room_summary(d) for d in live]

    def list_deleted_rooms(self, uid: str) -> list[dict]:
        """The rooms a writer has deleted and can still take back.

        Its own read rather than a flag on `list_rooms`, because the two lists
        are answering different questions and the rail draws them apart. This
        one does NOT purge: `list_rooms` owns that sweep, and a second caller
        deleting documents mid-read is how the same room gets purged twice.
        """
        cutoff = _retention_cutoff()
        docs = [
            doc
            for snapshot in self._rooms(uid).stream()
            if snapshot.exists
            for doc in [snapshot.to_dict()]
            if (doc.get("deleted_at") or "") >= cutoff and doc.get("deleted_at")
        ]
        docs.sort(key=lambda d: d.get("deleted_at") or "", reverse=True)
        return [{**room_summary(d), "deleted_at": d.get("deleted_at") or ""} for d in docs]

    def soft_delete_room(self, uid: str, run_id: str, when: str) -> bool:
        """Take a room out of sight, keeping it recoverable.

        Returns False when there was nothing there, for the reason
        `delete_scene` reads before it deletes: the endpoint turns False into a
        404, and a delete that always reported success would tell a writer their
        research was gone on a run_id that was never theirs.

        Marking twice is not an error and does not move the clock. A second
        delete of an already-deleted room would otherwise extend its life by
        another full window every time an agent retried, which is the opposite
        of what a retry should do.
        """
        document = self._rooms(uid).document(run_id)
        snapshot = document.get()
        if not snapshot.exists:
            return False
        if (snapshot.to_dict() or {}).get("deleted_at"):
            return True
        document.update({"deleted_at": when})
        return True

    def set_title(self, uid: str, run_id: str, title: str) -> str | None:
        """Rename a room, and hand back the name it now carries.

        Returns None when there was nothing there, for the reason
        `delete_scene` reads before it writes: the endpoint turns that into a
        404, and a rename that always reported success would tell a writer they
        had named a room that was never theirs. A room under another account
        never reaches the write — the path is rooted at `users/{uid}`, so the
        read finds nothing by construction rather than by an ownership check.

        **An empty title restores the derived one** rather than storing `""`.
        A room called nothing is worse than a room called what the intake
        thought it was, and `story_profile.title` still holds that, untouched
        by every rename, so the original is never actually spent. This is why
        there is no `title_set_by_writer` flag: a second field to explain the
        first is a second thing that has to stay true.
        """
        document = self._rooms(uid).document(run_id)
        snapshot = document.get()
        if not snapshot.exists:
            return None
        stored = snapshot.to_dict() or {}

        chosen = title.strip()
        if not chosen:
            profile = stored.get("story_profile") or {}
            chosen = profile.get("title") or _UNTITLED
        document.update({"title": chosen})
        return chosen

    def set_continues(self, uid: str, run_id: str, parent_id: str) -> bool:
        """Say which room this one follows, or clear it with an empty parent.

        Writes the link and nothing else. Whether the parent exists, belongs to
        this account, or would close a cycle is decided **above** this method,
        in the endpoint, because those are three different refusals with three
        different sentences and a store method that returned one bool for all
        of them would force the door to invent the reason.

        False when the room itself is missing, the same way every other write
        here answers a run_id that was never this account's.
        """
        document = self._rooms(uid).document(run_id)
        if not document.get().exists:
            return False
        document.update({"continues": parent_id.strip()})
        return True

    def restore_room(self, uid: str, run_id: str) -> bool:
        """Put a deleted room back, if the window has not closed on it.

        False when there is no such room, when it was not deleted, or when it is
        past the cutoff — three different reasons the caller reports apart,
        because "you cannot restore this" and "there is nothing here" are
        different answers and a writer is owed the real one.
        """
        snapshot = self._rooms(uid).document(run_id).get()
        if not snapshot.exists:
            return False
        deleted_at = (snapshot.to_dict() or {}).get("deleted_at") or ""
        if not deleted_at or deleted_at < _retention_cutoff():
            return False
        self._rooms(uid).document(run_id).update({"deleted_at": ""})
        return True

    def purge_room(self, uid: str, run_id: str) -> bool:
        """Destroy a room for good, and the checks filed against it with it.

        The scenes go first and the room second. A room deleted ahead of its
        subcollection would strand every scene under a path nothing lists,
        because Firestore does not cascade — deleting a document leaves its
        subcollections addressable and invisible, which is the worst of both:
        the writer's own pages, kept forever, reachable by nobody.

        Only ever called on a room already past its window, so there is no
        confirmation here. The gate is upstream.
        """
        if not run_id:
            return False
        # Collected before anything is deleted, not deleted as they stream.
        # `stream()` is a live cursor and removing rows out from under one is
        # undefined against Firestore and raises outright against the in-memory
        # double — which is how this was written the first time, and what the
        # purge test caught before it could reach a real database.
        scenes = [snapshot.reference for snapshot in self._scenes(uid, run_id).stream()]
        for reference in scenes:
            reference.delete()
        document = self._rooms(uid).document(run_id)
        if not document.get().exists:
            return False
        document.delete()
        return True

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


class ClientStore:
    """Reads and writes OAuth clients at the top-level /oauth_clients/{client_id}.

    Top level and unscoped, for the reason TokenStore below is: a client
    registers before anybody has signed in, so there is no uid to root the path
    at. A registered client belongs to no account — it is a program, and the
    accounts that approve it are recorded on the tokens it holds.

    Persisted rather than held in memory, which is where this departs from
    `spec-oauth-as.md`'s Decision 2 about authorization codes, and the
    difference is the lifetime. A code is dead in sixty seconds, so losing one
    to a restart costs a reader one retry. A client id is handed to a desktop
    program that stores it in a config file and presents it for months; losing
    the row means every one of them starts failing at `/authorize` after a
    deploy, with a refusal that says the client is not registered when the
    client's own file says it is.

    Client ID Metadata Document clients are never written here. Their identity
    is a URL somebody else serves and it is re-read on every authorization —
    see star/oauth/clients.py's `lookup` for why a cache would be this server
    enforcing a version of an identity that has already changed.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _default_client()
        return self._client

    def _clients(self):
        return self.client.collection("oauth_clients")

    def save(self, client_id: str, document: dict) -> None:
        self._clients().document(client_id).set(document)

    def get(self, client_id: str) -> dict | None:
        snapshot = self._clients().document(client_id).get()
        return snapshot.to_dict() if snapshot.exists else None


class TokenStore:
    """Reads and writes MCP tokens at the top-level /mcp_tokens/{token_id}.

    Top level, not /users/{uid}/tokens/{token_id}, and the read that decides it
    is authentication's: an agent presents a token and nothing else, so the
    server does not know the uid until after the lookup. A top-level collection
    makes that lookup one get() by document id — no query, no index, no
    collection-group scan, on the path every single MCP call pays for. The
    card's list is the rare read and pays instead with a where(), which
    Firestore's automatic single-field index already serves.

    The mirrored alternative — a document under the user plus a hash index —
    was rejected because two documents means a revoke can half-apply, and a
    half-revoked credential is worse than a slow list.

    A separate class rather than methods on RoomStore, because every RoomStore
    method opens with a uid and this collection has no uid in its path. Putting
    `get(token_id)` on a class organised around user scoping is how an
    unscoped read ends up looking scoped to the next reader.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _default_client()
        return self._client

    def _tokens(self):
        return self.client.collection("mcp_tokens")

    def save(self, token_id: str, document: dict) -> None:
        self._tokens().document(token_id).set(document)

    def get(self, token_id: str) -> dict | None:
        snapshot = self._tokens().document(token_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_for_uid(self, uid: str) -> list[dict]:
        """Every token issued to one account, newest first.

        Sorted in Python rather than by `order_by`, because a where() plus an
        order_by on different fields is a composite index, and a composite
        index is a deploy artifact this project does not otherwise have. N is
        the number of tokens one writer has issued.

        `filter=FieldFilter(...)` rather than the positional
        `where("uid", "==", uid)` the spec writes as shorthand: the positional
        form is deprecated in google-cloud-firestore 2.x and warns on every
        call.
        """
        query = self._tokens().where(filter=FieldFilter("uid", "==", uid))
        documents = [s.to_dict() for s in query.stream() if s.exists]
        documents.sort(key=lambda d: (d or {}).get("created_at") or "", reverse=True)
        return documents

    def list_for_family(self, family_id: str) -> list[dict]:
        """Every token in one rotation chain, in whatever order they come back.

        Keyed on `family_id` rather than on uid, which is the one query in this
        class that is not the account's. It is deliberate and it is bounded:
        a family id is minted per authorization-code exchange, it is a random
        32-hex value nobody outside this server ever sees, and the only caller
        already resolved a credential carrying it. Nobody can ask this question
        about a family they were not handed.

        `where()` on a single field is served by Firestore's automatic index —
        no composite, no deploy artifact, which is the same argument
        `list_for_uid` makes for sorting in Python.
        """
        if not family_id:
            # A `where(field == "")` would match every document written before
            # the field existed. An empty family id is a defect upstream and it
            # must not become "revoke everything".
            return []
        query = self._tokens().where(filter=FieldFilter("family_id", "==", family_id))
        return [s.to_dict() for s in query.stream() if s.exists]

    def revoke_family(self, family_id: str, when: str) -> int:
        """Kill a whole rotation chain. Returns how many were newly revoked.

        This is OAuth 2.1's answer to a refresh token presented twice. Rotation
        alone already denies the second presenter; what it cannot do on its own
        is decide WHICH of the two was the thief, because both hold a credential
        the server issued. Revoking the family resolves that by refusing to
        guess: the legitimate client is sent back through consent, and the
        attacker's freshly rotated pair dies with it.

        Not scoped by uid, unlike `revoke` above, and that is safe for the
        reason `list_for_family` gives: the caller reached this by resolving a
        credential that already carried the family id. Adding a uid parameter
        would read as an ownership check while checking nothing a family id did
        not already prove.

        Already-revoked members keep their first timestamp and are not counted,
        matching `revoke`: the first revocation is the fact worth keeping.
        """
        revoked = 0
        for stored in self.list_for_family(family_id):
            token_id = (stored or {}).get("token_id")
            if not token_id or stored.get("revoked_at"):
                continue
            self._tokens().document(token_id).update({"revoked_at": when})
            revoked += 1
        return revoked

    def touch(self, token_id: str, when: str) -> None:
        """Stamp when this token was last used. Throttled by the caller.

        Raises `NotFound` on a token that is no longer there, the same way
        `mark_interrupted` does and for the same reason: `.update()` on a
        missing document raises rather than creating a partial one. The caller
        decides what a lost stamp is worth, which is nothing — see
        star/tokens.py.
        """
        self._tokens().document(token_id).update({"last_used_at": when})

    def revoke(self, uid: str, token_id: str, when: str) -> bool:
        """Soft-delete one token, if it is this uid's.

        Returns False for a token that does not exist AND for a token that
        belongs to someone else — one answer for both, so the endpoint above
        cannot become an oracle for which token ids are real. That is
        `get_room`'s posture, reached here by an explicit comparison because a
        top-level collection has no uid in its path to reach it by
        construction. This is the one place in the project where cross-uid
        isolation is a check somebody has to remember rather than a property of
        the path, so it lives here, against the write, instead of in a handler
        where the next handler could forget it.

        Soft, where `delete_scene` is hard, and the difference is who is owed
        an answer. A revoked token has to be TOLD it was revoked on its next
        call, and a deleted document answers exactly like a token that never
        existed. A writer's script pages are the opposite case: the promise
        above the paste box is that the text stops being kept.

        An already-revoked token keeps its first timestamp and still reports
        True. The first revocation is the fact worth keeping, and a second
        DELETE from a card that still lists the token is a plausible click
        rather than an error.
        """
        document = self._tokens().document(token_id)
        snapshot = document.get()
        if not snapshot.exists:
            return False
        stored = snapshot.to_dict() or {}
        if stored.get("uid") != uid:
            return False
        if not stored.get("revoked_at"):
            document.update({"revoked_at": when})
        return True
