"""Round-trip a room through the real Firestore database.

The store's unit tests use a fake client, which proves the adapter's logic
and nothing about Firestore. This closes that gap. Writes to a throwaway uid
and deletes it afterwards.

Also covers two things only a real database can answer:

  - What RoomStore.mark_interrupted() does against a document that does not
    exist. ANSWERED here on 2026-08-09: Firestore's .update() raises NotFound
    ("404 No document to update"), which the store did not catch, so a delete
    landing between get_room's read and its update would have surfaced as an
    unhandled 500. mark_interrupted now catches NotFound specifically and
    returns False; get_room 404s on it. This script asserts that contract and
    that the raise no longer escapes.
  - Whether the slash-path collection address star/store.py uses
    (client.collection(f"users/{uid}/rooms")) is really interchangeable with
    the chained .collection("users").document(uid).collection("rooms") form.
    ANSWERED: yes, confirmed against the live service — identical paths, and a
    document written through one is readable through the other.

Run from the repo root:
    .venv/Scripts/python.exe scripts/verify_persistence.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


from star.store import RoomStore, room_to_document  # noqa: E402

UID = "verify-throwaway-uid"
RUN_ID = "verify-run"
MISSING_RUN_ID = "verify-missing-run"
SLASH_RUN_ID = "verify-slash-path-run"
RESULT = {
    "story_profile": {"title": "1962 Memphis", "era": "1960-1962", "genre": "Crime"},
    "research_bible": "# Bible\n\nStax operated from a converted theater.",
    "search_count": 14,
    "source_count": 106,
    "categories": {"setting": {"parse_rate": 1.0, "findings": [], "unverified_count": 0}},
}


def _cleanup(store) -> None:
    """Delete every document this script may have written.

    Runs from a finally block, not the happy path. This writes to the real
    database, so a failed assertion partway through must not leave throwaway
    documents behind — and an assertion failing is exactly the case where
    someone re-runs the script and needs a clean slate.
    """
    for doc_id in (RUN_ID, SLASH_RUN_ID, MISSING_RUN_ID):
        try:
            store.client.collection(f"users/{UID}/rooms").document(doc_id).delete()
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup: could not delete {doc_id}: {type(exc).__name__}")


def main() -> int:
    print("project:", os.environ.get("GOOGLE_CLOUD_PROJECT"))
    store = RoomStore()
    try:
        _verify(store)
    finally:
        _cleanup(store)
        print("cleaned up")

    print("\nround trip complete against real Firestore")
    return 0


def _verify(store) -> None:
    doc = room_to_document(RUN_ID, RESULT, "complete", "2026-08-09T12:00:00Z")
    store.save(UID, RUN_ID, doc)
    print(f"wrote /users/{UID}/rooms/{RUN_ID}")

    got = store.get(UID, RUN_ID)
    assert got is not None, "read back nothing"
    assert got["title"] == "1962 Memphis", got.get("title")
    assert got["categories"]["setting"]["parse_rate"] == 1.0
    print("read back OK, title =", got["title"])

    rooms = store.list_rooms(UID)
    assert any(r["run_id"] == RUN_ID for r in rooms), rooms
    assert "research_bible" not in rooms[0], "summary leaked the bible"
    print("list_rooms OK,", len(rooms), "room(s), summary shape correct")

    # --- Addition: the slash-path collection form ---------------------------
    # Write directly through the slash-delimited form store.py actually uses
    # (bypassing RoomStore's own helper, so this is a fresh assertion rather
    # than a restatement of what save()/get() already exercised), then read
    # it back through the chained form and check the resulting path.
    slash_ref = store.client.collection(f"users/{UID}/rooms").document(SLASH_RUN_ID)
    chained_ref = (
        store.client.collection("users")
        .document(UID)
        .collection("rooms")
        .document(SLASH_RUN_ID)
    )
    assert slash_ref.path == chained_ref.path, (slash_ref.path, chained_ref.path)

    slash_ref.set(room_to_document(SLASH_RUN_ID, RESULT, "complete", "2026-08-09T12:00:00Z"))
    snapshot = chained_ref.get()
    assert snapshot.exists, "document written via the slash-path form is invisible via the chained form"
    assert snapshot.to_dict()["title"] == "1962 Memphis"
    assert snapshot.reference.path == f"users/{UID}/rooms/{SLASH_RUN_ID}", snapshot.reference.path
    print("slash-path collection form OK, readable via chained form, path =", snapshot.reference.path)

    # --- Addition: mark_interrupted against a document that does not exist --
    store.client.collection(f"users/{UID}/rooms").document(MISSING_RUN_ID).delete()
    assert store.get(UID, MISSING_RUN_ID) is None, "missing-doc fixture was not actually missing"

    # This script originally discovered that Firestore's .update() raises
    # NotFound here, which the store did not catch — so a delete landing
    # between get_room's read and its update would have surfaced as a 500.
    # mark_interrupted now catches NotFound specifically and reports the miss
    # instead, and get_room 404s on it. Assert the current contract, and
    # assert the raise does NOT escape, since that was the original defect.
    marked = store.mark_interrupted(UID, MISSING_RUN_ID)
    assert marked is False, f"expected False for a missing document, got {marked!r}"
    assert store.get(UID, MISSING_RUN_ID) is None, "a missing document was resurrected"
    print("mark_interrupted on a missing document returned False without raising")

    marked = store.mark_interrupted(UID, RUN_ID)
    assert marked is True, f"expected True for a document that exists, got {marked!r}"
    assert store.get(UID, RUN_ID)["status"] == "interrupted"
    print("mark_interrupted OK")

    assert store.get("someone-else", RUN_ID) is None
    print("cross-user read correctly returns None")


if __name__ == "__main__":
    sys.exit(main())
