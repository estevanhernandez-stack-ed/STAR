"""A count is not a preview.

The import's dry run said "25 claims in this sweep would take a note from that
file. Nothing has been changed yet." True, and unactionable: a writer arming a
write into their own filed record could read it and still not know whether the
notes were landing where they meant, whether a line they struck last week was
about to be un-struck, or whether a note they typed a fortnight ago was about
to be replaced out of a stale copy of the file.

Sixth time on this surface in two days that the screen said something true and
left the reader with nothing to do about it, and the first one caught before it
shipped rather than after.

WHAT MAKES THIS WORTH A SERVER TEST rather than a rendering one: the diff needs
BOTH documents, and only the endpoint holds both. The payload carries the
after-state, so an app computing "what changed" from it would be guessing at
the before-state — a second implementation of one fact, in a second language,
which is how web/consent.js came to say "four calls" on the day a fifth tool
shipped.
"""

import copy
from unittest import mock

from fastapi.testclient import TestClient

from star import server
from star.server import _annotation_changes
from star.store import sweep_to_document
from tests.test_annotations import SWEEP
from tests.test_scenes import AUTH, ROOM, UID, a_store, filed_room

SWEEP_ID = "aa11bb22cc33"


def a_dry_run(csv_text: str, prepare=None) -> dict:
    """One preview against a filed sweep, through the real store.

    `prepare` gets the stored document before it is saved, so a scenario can
    start from a sweep that ALREADY carries a writer's marks — which is the
    case every interesting assertion here depends on.
    """
    # DEEP-COPIED, and this cost three red tests to learn. `sweep_to_document`
    # hands back a document whose claim dicts are THE SAME OBJECTS as its
    # input's, so a scenario that seeds a stored note writes it into the shared
    # SWEEP fixture and every later test in this file starts from a sweep it
    # never asked for. Harmless in production — the one caller passes the
    # result straight to save_sweep and never touches it again — and lethal
    # here, where half these assertions are about what the stored sweep
    # already said.
    document = sweep_to_document(copy.deepcopy(SWEEP), SWEEP_ID, "2026-08-13T13:35:00Z")
    if prepare:
        prepare(document)

    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, SWEEP_ID, document)

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        return TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/{SWEEP_ID}/annotations",
            json={"csv": csv_text, "apply": False},
            headers=AUTH,
        ).json()


def test_a_first_note_is_named_not_counted():
    body = a_dry_run("claim,writer_note\nKaiserkeller,Check the stage\n")

    assert body["matched"] == 1
    assert body["changes"] == [
        {"claim": "Kaiserkeller", "writer_note": "Check the stage", "dismissed": False}
    ]


def test_a_replacement_carries_the_words_it_is_replacing():
    """THE DANGEROUS ONE. A writer re-imports a fortnight-old copy of the file
    and silently loses the note they typed since. It is invisible in a count,
    and it is the reason this preview exists at all."""

    def prepare(document):
        document["claims"][0]["writer_note"] = "The note I typed on Tuesday"

    body = a_dry_run("claim,writer_note\nKaiserkeller,Something else\n", prepare)

    assert body["changes"] == [
        {
            "claim": "Kaiserkeller",
            "writer_note": "Something else",
            "dismissed": False,
            "was_note": "The note I typed on Tuesday",
        }
    ]


def test_an_unstrike_is_named_because_nobody_would_guess_it():
    """A blank `dismissed` cell in a stale file RESTORES a line the writer cut
    on purpose. Nothing about the file says so and nothing about the count
    does either."""

    def prepare(document):
        document["claims"][0]["dismissed"] = True

    body = a_dry_run("claim,writer_note\nKaiserkeller,keep\n", prepare)

    assert body["changes"][0]["dismissed"] is False
    assert body["changes"][0]["was_dismissed"] is True


def test_a_strike_is_named():
    body = a_dry_run("claim,dismissed\nKaiserkeller,yes\n")

    assert body["changes"] == [
        {"claim": "Kaiserkeller", "writer_note": "", "dismissed": True, "was_dismissed": False}
    ]


def test_a_claim_the_file_does_not_move_is_absent():
    """The preview lists what CHANGES. A file re-imported unaltered would
    otherwise redraw all sixty-three claims as though it were about to rewrite
    the sweep, which is precisely the wrong thing to tell somebody hovering
    over a confirm button."""

    def prepare(document):
        document["claims"][0]["writer_note"] = "Already said this"

    body = a_dry_run("claim,writer_note\nKaiserkeller,Already said this\n", prepare)

    assert body["matched"] == 1, "the row still matched"
    assert body["changes"] == [], "and nothing about the sweep would move"


def test_the_preview_writes_nothing():
    """It is a dry run. The clue is in the name, and this is the assertion the
    whole arming rests on."""
    # DEEP-COPIED, and this cost three red tests to learn. `sweep_to_document`
    # hands back a document whose claim dicts are THE SAME OBJECTS as its
    # input's, so a scenario that seeds a stored note writes it into the shared
    # SWEEP fixture and every later test in this file starts from a sweep it
    # never asked for. Harmless in production — the one caller passes the
    # result straight to save_sweep and never touches it again — and lethal
    # here, where half these assertions are about what the stored sweep
    # already said.
    document = sweep_to_document(copy.deepcopy(SWEEP), SWEEP_ID, "2026-08-13T13:35:00Z")
    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, SWEEP_ID, document)

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        body = TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/{SWEEP_ID}/annotations",
            json={"csv": "claim,writer_note\nKaiserkeller,Check the stage\n"},
            headers=AUTH,
        ).json()

    stored = client_data.data[f"users/{UID}/rooms/{ROOM}/sweeps/{SWEEP_ID}"]
    assert body["changes"], "the preview describes a change"
    assert "writer_note" not in stored["claims"][0], "and the sweep is untouched"


def test_the_diff_is_pure_and_survives_a_ragged_document():
    """Called on whatever the store hands back. A claim with no text, a None in
    the list, a missing claims key — none of those are worth a 500 on a preview
    endpoint, and all three have shipped out of this store at some point."""
    assert _annotation_changes({}, {}) == []
    assert _annotation_changes({"claims": None}, {"claims": None}) == []
    assert _annotation_changes({"claims": [None]}, {"claims": [None]}) == []

    before = {"claims": [{"text": " Kaiserkeller "}]}
    after = {"claims": [{"text": " Kaiserkeller ", "writer_note": "x"}]}
    changes = _annotation_changes(before, after)
    assert changes == [{"claim": "Kaiserkeller", "writer_note": "x", "dismissed": False}]
    assert before == {"claims": [{"text": " Kaiserkeller "}]}, "and it mutated nothing"


def test_this_files_own_scenarios_cannot_leak_into_each_other():
    """A guard on the harness, because its absence cost three red tests above
    and would have cost a wrong answer instead if the leak had run the other
    way. `sweep_to_document` shares claim dicts with its input, so seeding a
    stored note without a deep copy writes it into the module-level SWEEP that
    tests/test_annotations.py also imports."""
    before = copy.deepcopy(SWEEP)

    a_dry_run(
        "claim,writer_note\nKaiserkeller,a note this scenario invented\n",
        lambda document: document["claims"][0].update({"writer_note": "seeded"}),
    )

    assert SWEEP == before, "a scenario changed the fixture every other test reads"
