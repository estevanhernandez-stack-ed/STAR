"""A sweep's export belongs to that sweep, and the file says so on every row.

THE DEFECT, measured on the live service 2026-08-13. A writer exported sweep
`26881297a20d`, marked thirteen claims in a spreadsheet, and imported it with a
different sweep open on screen. Everything downstream behaved exactly as
designed and the screen read as a fault:

  - five claims matched, because the two sweeps shared five claims
  - eight came back "named a claim this sweep does not hold", every one of them
    a claim the file's OWN sweep raised
  - six rows were reported as having edited source_url, source_title,
    source_excerpt and verdict, because those rows carried the other sweep's
    citations and `apply_annotations` correctly compares against this one

Fourteen true statements, and not one of them said "this file is from another
sweep". `sweep_id` has been written into every exported row since the export
shipped, and nothing ever read it back.

REFUSED, NOT REPORTED. A complaint would leave the writer one press away from
filing whichever notes the two sweeps happened to share onto a document they
were not looking at, which is a worse outcome than an error: the five that
landed would look like success.

A file with no `sweep_id` column is still accepted. The first exports had no
such column, a writer may hand-build a two-column file of claims and notes, and
the import has always matched on claim text. Absence is not a mismatch.
"""

from unittest import mock

from fastapi.testclient import TestClient

from star import exports, server
from star.store import sweep_to_document
from tests.test_annotations import SWEEP
from tests.test_scenes import AUTH, ROOM, UID, a_store, filed_room


def test_origin_is_read_off_the_first_row():
    text = "claim,sweep_id\na Gibson,abc123\n"

    assert exports.annotation_origin(text) == "abc123"


def test_a_file_that_does_not_say_claims_nothing():
    """Absence is not a mismatch. A hand-built two-column file has always been
    a legitimate way to annotate, and it names no sweep."""
    assert exports.annotation_origin("claim,writer_note\na Gibson,keep\n") == ""
    assert exports.annotation_origin("claim,sweep_id\na Gibson,\n") == ""
    assert exports.annotation_origin("") == ""
    assert exports.annotation_origin("claim,sweep_id\n") == ""


def test_an_unreadable_file_names_no_sweep_rather_than_raising():
    """This runs before the parse that reports unreadable files, so it has to
    hand that job back rather than take it."""
    assert exports.annotation_origin('claim,sweep_id\n"unclosed,abc\n') in {"", "abc"}


def test_the_id_survives_the_formula_guard():
    """`unsafe_cell` is applied to every cell read out of a returned file. An id
    is alphanumeric and must come back unchanged; the point is that the guard
    runs here too rather than being skipped for a field that looks safe."""
    assert exports.annotation_origin("claim,sweep_id\nx,26881297a20d\n") == "26881297a20d"


STORED = "users/{uid}/rooms/{room}/sweeps/sw1"


def a_post(csv_text: str, apply: bool = False):
    """One import against the filed sweep `sw1`, through the real store.

    Returns (response, the stored sweep afterwards), because half of what this
    file asserts is that a refusal WROTE NOTHING, and a status code cannot say
    that.
    """
    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "sw1", sweep_to_document(SWEEP, "sw1", "2026-08-12T22:00:00Z"))

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/sw1/annotations",
            json={"csv": csv_text, "apply": apply},
            headers=AUTH,
        )
    return response, client_data.data[STORED.format(uid=UID, room=ROOM)]


def test_a_file_from_another_sweep_is_refused_by_name():
    """And BOTH ids are in the message. "Wrong sweep" leaves a writer holding
    two sweeps filed on one room with no way to tell which file is which."""
    response, _ = a_post("claim,sweep_id,writer_note\nKaiserkeller,sw-other,keep it\n")

    assert response.status_code == 400
    body = response.json()["detail"]
    assert "sw-other" in body, body
    assert "sw1" in body, body
    assert "Nothing was changed" in body, body


def test_nothing_is_filed_from_a_file_belonging_elsewhere():
    """The refusal is the point. A complaint would leave the writer one press
    from filing whatever the two sweeps share onto the wrong document, and the
    notes that landed would look like success."""
    response, stored = a_post(
        "claim,sweep_id,writer_note\nKaiserkeller,sw-other,keep it\n", apply=True
    )

    assert response.status_code == 400
    assert "writer_note" not in stored["claims"][0], "a refused import writes nothing"


def test_the_sweep_its_own_file_came_from_still_takes_it():
    response, stored = a_post(
        "claim,sweep_id,writer_note\nKaiserkeller,sw1,keep it\n", apply=True
    )

    assert response.status_code == 200
    assert response.json()["matched"] == 1
    assert stored["claims"][0]["writer_note"] == "keep it"


def test_a_file_naming_no_sweep_is_still_accepted():
    """The oldest exports had no `sweep_id` column and a hand-built file has
    none either. Refusing those would break a path that has always worked."""
    response, stored = a_post("claim,writer_note\nKaiserkeller,keep it\n", apply=True)

    assert response.status_code == 200
    assert response.json()["matched"] == 1
    assert stored["claims"][0]["writer_note"] == "keep it"


def test_a_real_export_imports_into_its_own_sweep():
    """End to end over the export this feature is for, rather than a hand-typed
    two-column file. `sweep_to_csv` writes the id and this reads it, so the two
    halves are pinned to each other rather than to my memory of the shape."""
    document = sweep_to_document(SWEEP, "sw1", "2026-08-12T22:00:00Z")
    text = exports.sweep_to_csv(document)

    assert exports.annotation_origin(text) == "sw1"

    response, _ = a_post(text)
    assert response.status_code == 200, response.text


def test_the_refusal_comes_before_the_rows_are_read():
    """Ordering, asserted rather than assumed. The refusal has to land before
    anything parses rows, or a mismatched file's own row complaints reach the
    reader first and bury the one that explains all of them."""
    response, _ = a_post(
        "claim,sweep_id,writer_note\n"
        ",sw-other,a row naming no claim\n"
        "Kaiserkeller,sw-other,keep it\n"
    )

    assert response.status_code == 400
    # The row-level complaint would have been "Row 2 names no claim". It is
    # absent because nothing got that far.
    assert "names no claim" not in response.json()["detail"]
