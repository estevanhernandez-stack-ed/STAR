from google.api_core.exceptions import NotFound

from star.store import (
    RoomStore,
    document_to_room,
    room_summary,
    room_to_document,
)

RESULT = {
    "story_profile": {"title": "1962 Memphis", "era": "1960-1962", "genre": "Crime"},
    "research_plan": {"questions": []},
    "research_bible": "# Bible\n\nSome text.",
    "search_count": 14,
    "source_count": 106,
    "categories": {
        "setting": {
            "category": "setting",
            "markdown": "raw",
            "findings": [{"fact": "A fact", "citations": [], "unverified_urls": []}],
            "field_notes": "",
            "parse_rate": 1.0,
            "unverified_count": 0,
        }
    },
}


class _FakeDoc:
    def __init__(self, store, path):
        self._store, self._path = store, path

    def set(self, data):
        self._store.data[self._path] = data

    def update(self, patch):
        # Real Firestore raises NotFound from .update() on a missing
        # document rather than creating a partial one — verified against the
        # live database. This fake used to silently `setdefault` a partial
        # document instead, which let mark_interrupted's missing-document
        # path pass tests without ever exercising real behavior.
        if self._path not in self._store.data:
            raise NotFound(f"No document to update: {self._path}")
        self._store.data[self._path].update(patch)

    def get(self):
        return _FakeSnapshot(self._store.data.get(self._path))

    def delete(self):
        # Real Firestore's .delete() is idempotent and says nothing about what
        # it removed — no raise on a missing document, no return value. Stores
        # that answer "did anything go?" have to read first, which is why
        # RoomStore.delete_scene does.
        self._store.data.pop(self._path, None)


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeCollection:
    def __init__(self, store, prefix, matches=None):
        self._store, self._prefix = store, prefix
        self._matches = matches

    def document(self, doc_id):
        return _FakeDoc(self._store, f"{self._prefix}/{doc_id}")

    def collection(self, name):
        return _FakeCollection(self._store, f"{self._prefix}/{name}")

    def where(self, filter=None):
        """Keyword-only, like the real client's supported form.

        google-cloud-firestore 2.x deprecated the positional
        `where("uid", "==", uid)` shape in favour of `filter=FieldFilter(...)`,
        so a fake that accepted three positional arguments would let a caller
        pass the form that warns on every call in production. Only `==` is
        modelled, because only `==` is used.
        """
        assert filter is not None, "the positional where() form is deprecated"
        assert filter.op_string == "==", f"unmodelled operator {filter.op_string}"
        field, value = filter.field_path, filter.value

        def matches(data):
            return (data or {}).get(field) == value

        return _FakeCollection(self._store, self._prefix, matches)

    def stream(self):
        depth = self._prefix.count("/") + 1
        for path, data in self._store.data.items():
            if (
                path.startswith(self._prefix + "/")
                and path.count("/") == depth
                and (self._matches is None or self._matches(data))
            ):
                yield _FakeSnapshot(data)


class _FakeClient:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return _FakeCollection(self, name)


def test_room_to_document_carries_the_fields_the_rail_and_room_need():
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    assert doc["run_id"] == "abc123"
    assert doc["status"] == "complete"
    assert doc["created_at"] == "2026-08-09T12:00:00Z"
    assert doc["title"] == "1962 Memphis"
    assert doc["era"] == "1960-1962"
    assert doc["search_count"] == 14
    assert doc["research_bible"].startswith("# Bible")
    assert doc["categories"]["setting"]["parse_rate"] == 1.0


def test_room_to_document_survives_a_result_with_no_story_profile():
    """A run that errored before intake finished still has to persist."""
    doc = room_to_document("abc123", {"search_count": 0}, "error", "2026-08-09T12:00:00Z")

    assert doc["title"] == "Untitled room"
    assert doc["status"] == "error"
    assert doc["categories"] == {}


def test_document_to_room_round_trips_the_api_payload():
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    room = document_to_room(doc)

    assert room["story_profile"]["title"] == "1962 Memphis"
    assert room["research_bible"].startswith("# Bible")
    assert room["categories"]["setting"]["findings"][0]["fact"] == "A fact"
    assert room["search_count"] == 14


def test_document_to_room_carries_created_at_for_the_retrieval_stamp():
    """The room view stamps this on every citation receipt as the day those
    sources came back from a search (`RET <date>`, web/clip.js). Until Task 6
    this shape dropped it, and the browser had no honest value to print — it
    refuses to reuse the filed date for a retrieval claim, so the stamp shipped
    two thirds complete."""
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    assert document_to_room(doc)["created_at"] == "2026-08-09T12:00:00Z"


def test_document_to_room_leaves_created_at_empty_when_the_document_has_none():
    """An older document, written before the field existed. Empty rather than
    "now": the client drops the RET line for a falsy value, and a fabricated
    retrieval date on a source is worse than no date at all."""
    room = document_to_room({"story_profile": {"title": "1962 Memphis"}})

    assert room["created_at"] == ""


def test_room_summary_is_small_enough_for_a_rail():
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    summary = room_summary(doc)

    assert summary == {
        "run_id": "abc123",
        "title": "1962 Memphis",
        "era": "1960-1962",
        "status": "complete",
        "created_at": "2026-08-09T12:00:00Z",
        "search_count": 14,
    }
    assert "research_bible" not in summary
    assert "categories" not in summary


def test_save_and_get_round_trip_per_user():
    store = RoomStore(client=_FakeClient())
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    store.save("uid-one", "abc123", doc)

    assert store.get("uid-one", "abc123")["title"] == "1962 Memphis"


def test_one_user_cannot_read_another_users_room():
    store = RoomStore(client=_FakeClient())
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")
    store.save("uid-one", "abc123", doc)

    assert store.get("uid-two", "abc123") is None


def test_get_returns_none_for_an_unknown_room():
    store = RoomStore(client=_FakeClient())
    assert store.get("uid-one", "does-not-exist") is None


def test_list_rooms_returns_summaries_newest_first():
    store = RoomStore(client=_FakeClient())
    store.save("uid-one", "old", room_to_document("old", RESULT, "complete", "2026-08-01T00:00:00Z"))
    store.save("uid-one", "new", room_to_document("new", RESULT, "complete", "2026-08-09T00:00:00Z"))

    rooms = store.list_rooms("uid-one")

    assert [r["run_id"] for r in rooms] == ["new", "old"]
    assert "research_bible" not in rooms[0]


def test_list_rooms_is_empty_for_a_new_user():
    store = RoomStore(client=_FakeClient())
    assert store.list_rooms("nobody") == []


def test_mark_interrupted_moves_a_stuck_run_off_running():
    store = RoomStore(client=_FakeClient())
    store.save("uid-one", "abc123", room_to_document("abc123", RESULT, "running", "2026-08-09T12:00:00Z"))

    assert store.mark_interrupted("uid-one", "abc123") is True

    assert store.get("uid-one", "abc123")["status"] == "interrupted"


# --- Task 2: a delete-between-read-and-update race must 404, not 500 -------


def test_mark_interrupted_returns_false_when_the_document_is_gone():
    """Real Firestore's .update() raises NotFound on a missing document — a
    race genuinely reachable now that create_room writes a document at
    creation time and get_room calls mark_interrupted after its own read.
    The fake must agree with real Firestore here, or this test would pass
    for the wrong reason."""
    store = RoomStore(client=_FakeClient())

    assert store.mark_interrupted("uid-one", "does-not-exist") is False
