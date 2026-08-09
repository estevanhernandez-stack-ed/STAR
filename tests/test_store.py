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
        self._store.data.setdefault(self._path, {}).update(patch)

    def get(self):
        return _FakeSnapshot(self._store.data.get(self._path))


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeCollection:
    def __init__(self, store, prefix):
        self._store, self._prefix = store, prefix

    def document(self, doc_id):
        return _FakeDoc(self._store, f"{self._prefix}/{doc_id}")

    def collection(self, name):
        return _FakeCollection(self._store, f"{self._prefix}/{name}")

    def stream(self):
        depth = self._prefix.count("/") + 1
        for path, data in self._store.data.items():
            if path.startswith(self._prefix + "/") and path.count("/") == depth:
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

    store.mark_interrupted("uid-one", "abc123")

    assert store.get("uid-one", "abc123")["status"] == "interrupted"
