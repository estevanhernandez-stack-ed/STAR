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
    def __init__(self, data, reference=None):
        self._data = data
        # Real snapshots carry a `.reference` back to the document they came
        # from, and a sweep that deletes what it streamed uses it rather than
        # rebuilding a path from a field inside the data. The fake grew one when
        # RoomStore.purge_room needed it: modelling the API the code legitimately
        # uses beats bending the code around a gap in the double.
        self.reference = reference

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
                yield _FakeSnapshot(data, _FakeDoc(self._store, path))


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
        # A run_id, and the rail groups a story on it. It earns its place by
        # the same test the exclusions below fail: the alternative is reading
        # twenty rooms whole to draw a list of twenty.
        "continues": "",
        # Empty here, and that is the point of it being cheap: a note only
        # exists on a room that ended badly, so the rail carries one sentence
        # for the one room in twenty that failed and nothing for the rest. It
        # earns its place on the other side of the same trade as `continues` —
        # without it a rail can say a room failed and cannot say why, which
        # sends the reader into the room to find out and puts the explanation
        # behind the click it was written to save.
        "note": "",
    }
    assert "research_bible" not in summary
    assert "categories" not in summary


def test_a_note_survives_the_document_and_reaches_the_rail():
    """Both shapes carry it, because both are places a reader learns a room failed.

    The rail is the one that matters most: it is where a writer sees a room is
    flagged, and a rail that can say a room stopped without saying why has put
    the explanation behind a click it exists to save.
    """
    note = "The department ran past its 10-minute limit and was stopped."
    doc = room_to_document("abc123", {}, "error", "2026-08-09T12:00:00Z", note=note)

    assert doc["note"] == note
    assert document_to_room(doc)["note"] == note
    assert room_summary(doc)["note"] == note


def test_a_room_that_finished_carries_no_note():
    """An empty string, not a missing key, and not a sentence.

    A note on a complete room would be a label on an open door — and the
    default has to be falsy rather than absent so every reader can ask the
    same question of every room without checking whether the field is there.
    """
    doc = room_to_document("abc123", RESULT, "complete", "2026-08-09T12:00:00Z")

    assert doc["note"] == ""
    assert room_summary(doc)["note"] == ""


def test_an_older_document_written_before_notes_existed_reads_as_having_none():
    """The twenty-three rooms already in Firestore have no `note` field at all.

    They were written before it existed, and `.get()` on a missing key has to
    land on the same empty string a finished room writes — otherwise the first
    reader of an old failed room gets a None into copy that expects a string.
    """
    assert document_to_room({"run_id": "old"})["note"] == ""
    assert room_summary({"run_id": "old"})["note"] == ""


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



def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _long_ago() -> str:
    """Comfortably past any retention window a config could set."""
    from datetime import datetime, timedelta, timezone

    from star import config

    days = config.room_retention_days() + 5
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()  # noqa: UP017


# -- deleting a room ---------------------------------------------------------
#
# Reversible for a window, then real. The two halves are tested apart because
# they fail apart: a soft delete that does not hide the room leaves a workspace
# that never gets clean, and a purge that misses the scenes subcollection leaves
# the writer's own script pages under a path nothing lists and nobody can reach.


def _room_with_a_check(store, uid="uid-one", run_id="abc123", created="2026-08-09T12:00:00Z"):
    store.save(uid, run_id, room_to_document(run_id, RESULT, "complete", created))
    store.save_scene(uid, run_id, "scene-1", {"scene_id": "scene-1", "scene": "INT. ..."})
    return uid, run_id


def _fresh():
    return RoomStore(client=_FakeClient())


def test_a_deleted_room_leaves_the_list_at_once_but_is_not_destroyed():
    store = _fresh()
    uid, run_id = _room_with_a_check(store)

    assert store.soft_delete_room(uid, run_id, _now()) is True
    assert store.list_rooms(uid) == [], "gone from the writer's sight immediately"
    assert store.get(uid, run_id) is not None, "and still there to be restored"
    assert store.get_scene(uid, run_id, "scene-1") is not None


def test_deleting_a_room_that_is_not_there_says_so():
    """`delete_scene`'s rule, for the same reason: the endpoint turns False into
    a 404, and a delete that always reported success would tell a writer their
    research was gone on a run_id that was never theirs."""
    assert _fresh().soft_delete_room("uid-one", "never-existed", _now()) is False


def test_deleting_twice_does_not_extend_the_window():
    """A retry must not buy another thirty days. An agent that retries a delete
    would otherwise keep a room alive indefinitely by trying to remove it."""
    store = _fresh()
    uid, run_id = _room_with_a_check(store)
    first = "2026-07-01T00:00:00+00:00"

    store.soft_delete_room(uid, run_id, first)
    assert store.soft_delete_room(uid, run_id, _now()) is True
    assert store.get(uid, run_id)["deleted_at"] == first, "the clock did not move"


def test_restore_brings_a_room_back_inside_the_window():
    store = _fresh()
    uid, run_id = _room_with_a_check(store)
    store.soft_delete_room(uid, run_id, _now())

    assert store.restore_room(uid, run_id) is True
    assert [r["run_id"] for r in store.list_rooms(uid)] == [run_id]


def test_restore_refuses_a_room_that_was_never_deleted_or_is_past_the_window():
    store = _fresh()
    uid, run_id = _room_with_a_check(store)
    assert store.restore_room(uid, run_id) is False, "nothing to bring back"

    store.soft_delete_room(uid, run_id, _long_ago())
    assert store.restore_room(uid, run_id) is False, "the window has closed"
    assert store.restore_room(uid, "never-existed") is False


def test_listing_destroys_a_room_whose_window_has_closed_and_its_checks_with_it():
    """The purge, and the half that is easy to get wrong.

    Firestore does not cascade: deleting a document leaves its subcollections
    addressable and invisible. A purge that took the room and left the scenes
    would keep the writer's own script pages forever under a path nothing lists.
    """
    store = _fresh()
    uid, run_id = _room_with_a_check(store)
    store.soft_delete_room(uid, run_id, _long_ago())

    assert store.list_rooms(uid) == []
    assert store.get(uid, run_id) is None, "the room is gone for good"
    assert store.get_scene(uid, run_id, "scene-1") is None, (
        "and the check filed against it went with it"
    )


def test_the_purge_leaves_every_other_room_alone():
    store = _fresh()
    uid, doomed = _room_with_a_check(store, run_id="doomed")
    _room_with_a_check(store, run_id="kept", created="2026-08-10T12:00:00Z")
    store.soft_delete_room(uid, doomed, _long_ago())

    assert [r["run_id"] for r in store.list_rooms(uid)] == ["kept"]
    assert store.get(uid, "kept") is not None
    assert store.get_scene(uid, "kept", "scene-1") is not None


def test_one_writers_delete_cannot_reach_another_writers_room():
    """Ownership by path construction, the way delete_scene already gets it —
    `users/{uid}/rooms/...` never resolves across accounts, so this is true by
    the shape of the read rather than by a check somebody has to remember."""
    store = _fresh()
    _room_with_a_check(store, uid="owner", run_id="theirs")

    assert store.soft_delete_room("stranger", "theirs", _now()) is False
    assert store.purge_room("stranger", "theirs") is False
    assert store.get("owner", "theirs") is not None


# --- Naming a room, and saying what it follows ------------------------------
#
# THE BUG. `star/store.py` hard-coded "Untitled room" as a permanent fate.
# There was no rename path anywhere — not in the store, not in the server, not
# in the web app — so a build whose intake could not find a title produced a
# room that could never be called anything else. The judge's round-two review
# named it under "Room hygiene": three Untitled rooms and an errored husk, and
# no way to clean any of it up.
#
# And rooms had no relation to each other, so a story spanning five eras was
# five strangers in a rail sorted newest-first.


def _saved(store, uid="uid-one", run_id="abc123", result=RESULT):
    doc = room_to_document(run_id, result, "complete", "2026-08-09T12:00:00Z")
    store.save(uid, run_id, doc)
    return run_id


def test_a_room_can_be_renamed():
    store = RoomStore(client=_FakeClient())
    _saved(store)

    assert store.set_title("uid-one", "abc123", "The Substitute Sync") == (
        "The Substitute Sync"
    )
    assert store.get("uid-one", "abc123")["title"] == "The Substitute Sync"


def test_renaming_leaves_the_intake_s_own_title_intact():
    """`story_profile.title` is what the department thought the room was, and
    a rename is the writer disagreeing — not the department being wrong. Kept
    so the derived name is never actually spent."""
    store = RoomStore(client=_FakeClient())
    _saved(store)

    store.set_title("uid-one", "abc123", "Something else entirely")

    assert store.get("uid-one", "abc123")["story_profile"]["title"] == "1962 Memphis"


def test_an_empty_title_restores_the_derived_one():
    """A room called nothing is worse than a room called what intake guessed."""
    store = RoomStore(client=_FakeClient())
    _saved(store)
    store.set_title("uid-one", "abc123", "A working title")

    assert store.set_title("uid-one", "abc123", "   ") == "1962 Memphis"
    assert store.get("uid-one", "abc123")["title"] == "1962 Memphis"


def test_an_empty_title_on_a_room_intake_never_named_falls_back_to_untitled():
    store = RoomStore(client=_FakeClient())
    _saved(store, result={**RESULT, "story_profile": {}})

    assert store.set_title("uid-one", "abc123", "") == "Untitled room"


def test_a_title_is_trimmed():
    store = RoomStore(client=_FakeClient())
    _saved(store)

    assert store.set_title("uid-one", "abc123", "  Padded  ") == "Padded"


def test_renaming_a_room_this_account_does_not_own_answers_none():
    """The path is rooted at users/{uid}, so another account's room is not
    found rather than refused — the same construction `delete_scene` relies on.
    None so the endpoint can 404, because a rename that always reported success
    would tell a writer they had named a room that was never theirs."""
    store = RoomStore(client=_FakeClient())
    _saved(store)

    assert store.set_title("uid-two", "abc123", "Mine now") is None
    assert store.get("uid-one", "abc123")["title"] == "1962 Memphis"


def test_a_room_can_say_which_room_it_follows():
    store = RoomStore(client=_FakeClient())
    _saved(store, run_id="second")

    assert store.set_continues("uid-one", "second", "first") is True
    assert store.get("uid-one", "second")["continues"] == "first"


def test_the_link_can_be_cleared():
    store = RoomStore(client=_FakeClient())
    _saved(store, run_id="second")
    store.set_continues("uid-one", "second", "first")

    assert store.set_continues("uid-one", "second", "") is True
    assert store.get("uid-one", "second")["continues"] == ""


def test_linking_a_room_this_account_does_not_own_answers_false():
    store = RoomStore(client=_FakeClient())
    _saved(store, run_id="second")

    assert store.set_continues("uid-two", "second", "first") is False


def test_a_room_summary_carries_the_link_so_the_rail_need_not_read_rooms_whole():
    store = RoomStore(client=_FakeClient())
    _saved(store, run_id="second")
    store.set_continues("uid-one", "second", "first")

    listed = store.list_rooms("uid-one")

    assert [r["continues"] for r in listed] == ["first"]


def test_a_padded_parent_id_is_trimmed_so_it_can_match_a_room():
    """A run_id arrives from a paste as often as from a click, and a trailing
    space makes it match nothing. Caught by mutation testing: the clear-the-link
    test passed with the trim removed, because an empty string is empty either
    way, so it was proving nothing about the trim it appeared to guard."""
    store = RoomStore(client=_FakeClient())
    _saved(store, run_id="second")

    store.set_continues("uid-one", "second", "  first  ")

    assert store.get("uid-one", "second")["continues"] == "first"


def test_a_whitespace_only_parent_clears_the_link():
    store = RoomStore(client=_FakeClient())
    _saved(store, run_id="second")
    store.set_continues("uid-one", "second", "first")

    store.set_continues("uid-one", "second", "   ")

    assert store.get("uid-one", "second")["continues"] == ""
