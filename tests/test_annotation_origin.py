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


def test_a_spreadsheet_mangled_id_is_read_as_no_id_at_all():
    """FAIL OPEN, and this is the half that matters.

    A sweep id is uuid4().hex[:12]. 1 in 141 of those parses as a number —
    10^12 of the 16^12 are all digits, another 10^12 have the shape
    `digits e digits` — and a spreadsheet coerces the cell and writes the
    coerced value back on save.

    The caller REFUSES on a mismatch. Reading `1.23457E+11` as an id would
    reject a file that genuinely belongs to the open sweep, and the refusal's
    own advice — export this sweep and mark that up — walks the writer into
    the same wall next try. A loop, out of a cell nobody typed in.
    """
    for mangled in ("1.23457E+11", "inf", "#NUM!", "2.6881E+11", "-inf", "1E+05"):
        text = f"claim,sweep_id\nKaiserkeller,{mangled}\n"
        assert exports.annotation_origin(text) == "", mangled


def test_an_id_a_spreadsheet_left_alone_still_counts():
    """The other side of the same coin. An all-digit id that Excel preserved
    exactly is still an id, and treating every numeric-looking value as damage
    would silently disable the check for 1 in 270 sweeps."""
    assert exports.annotation_origin("claim,sweep_id\nx,123456789012\n") == "123456789012"


def test_the_shape_test_does_not_swallow_a_real_mismatch():
    """Fail-open must not become fail-always. A well-formed id that differs is
    the case this feature exists for."""
    assert exports.annotation_origin("claim,sweep_id\nx,f1d31518e372\n") == "f1d31518e372"


STORED = "users/{uid}/rooms/{room}/sweeps/aa11bb22cc33"


def a_post(csv_text: str, apply: bool = False):
    """One import against the filed sweep `aa11bb22cc33`, through the real store.

    Returns (response, the stored sweep afterwards), because half of what this
    file asserts is that a refusal WROTE NOTHING, and a status code cannot say
    that.
    """
    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "aa11bb22cc33", sweep_to_document(SWEEP, "aa11bb22cc33", "2026-08-12T22:00:00Z"))

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/aa11bb22cc33/annotations",
            json={"csv": csv_text, "apply": apply},
            headers=AUTH,
        )
    return response, client_data.data[STORED.format(uid=UID, room=ROOM)]


def test_a_file_from_a_sweep_not_on_this_room_says_so():
    """A different answer from "open the other one", and it has to be. The
    writer cannot open a sweep that is not filed here, and pointing at one
    would be a lie about a button that is not on the screen."""
    response, _ = a_post("claim,sweep_id,writer_note\nKaiserkeller,dd44ee55ff66,keep it\n")

    assert response.status_code == 400
    body = response.json()["detail"]
    assert "not filed on this room" in body, body
    assert "Nothing was changed" in body, body


def test_the_refusal_names_the_other_sweep_the_way_the_picker_does():
    """NOT BY ID. The reader has never seen a sweep id — the picker draws each
    filed sweep as "24 scenes · 64 claims · 13 AUG 2026 13:35" and an id
    appears on no surface of this app. The first version of this message named
    one, which sent a writer looking for a string written nowhere they could
    look. So the message has to carry the same three fields the button does.
    """
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "aa11bb22cc33", sweep_to_document(SWEEP, "aa11bb22cc33", "2026-08-13T13:35:00Z"))
    # The sweep the file actually came from, also filed on this room.
    other = sweep_to_document(SWEEP, "f1d31518e372", "2026-08-13T11:41:00Z")
    other["scenes_read"] = 24
    store.save_sweep(UID, ROOM, "f1d31518e372", other)

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/aa11bb22cc33/annotations",
            json={"csv": "claim,sweep_id,writer_note\nKaiserkeller,f1d31518e372,keep it\n"},
            headers=AUTH,
        )

    assert response.status_code == 400
    body = response.json()["detail"]
    assert "24 scenes" in body, body
    assert "2 claims" in body, body
    assert "2026-08-13 11:41" in body, body
    assert "f1d31518e372" not in body, f"the id is not a handle the reader has: {body}"


def test_one_scene_and_one_claim_are_not_pluralised():
    """The message is read next to a button that says "1 scene · 1 claim", and
    a sentence that says "1 scenes" beside it reads like a different sweep."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "aa11bb22cc33", sweep_to_document(SWEEP, "aa11bb22cc33", "2026-08-13T13:35:00Z"))
    one = {"room": SWEEP["room"], "claims": SWEEP["claims"][:1]}
    other = sweep_to_document(one, "f1d31518e372", "2026-08-13T11:41:00Z")
    other["scenes_read"] = 1
    store.save_sweep(UID, ROOM, "f1d31518e372", other)

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        body = TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/aa11bb22cc33/annotations",
            json={"csv": "claim,sweep_id,writer_note\nKaiserkeller,f1d31518e372,keep it\n"},
            headers=AUTH,
        ).json()["detail"]

    assert "1 scene ·" in body, body
    assert "1 scenes" not in body, body
    assert "1 claim ·" in body or "1 claim " in body, body


def test_nothing_is_filed_from_a_file_belonging_elsewhere():
    """The refusal is the point. A complaint would leave the writer one press
    from filing whatever the two sweeps share onto the wrong document, and the
    notes that landed would look like success."""
    response, stored = a_post(
        "claim,sweep_id,writer_note\nKaiserkeller,dd44ee55ff66,keep it\n", apply=True
    )

    assert response.status_code == 400
    assert "writer_note" not in stored["claims"][0], "a refused import writes nothing"


def test_the_sweep_its_own_file_came_from_still_takes_it():
    response, stored = a_post(
        "claim,sweep_id,writer_note\nKaiserkeller,aa11bb22cc33,keep it\n", apply=True
    )

    assert response.status_code == 200
    assert response.json()["matched"] == 1
    assert stored["claims"][0]["writer_note"] == "keep it"


def test_a_file_whose_id_a_spreadsheet_ate_still_imports():
    """End to end on the loop this prevents: the file belongs to the open
    sweep, Excel turned its id into a float, and it must still file."""
    response, stored = a_post(
        "claim,sweep_id,writer_note\nKaiserkeller,1.23457E+11,keep it\n", apply=True
    )

    assert response.status_code == 200, response.text
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
    document = sweep_to_document(SWEEP, "aa11bb22cc33", "2026-08-12T22:00:00Z")
    text = exports.sweep_to_csv(document)

    assert exports.annotation_origin(text) == "aa11bb22cc33"

    response, _ = a_post(text)
    assert response.status_code == 200, response.text


def test_the_refusal_comes_before_the_rows_are_read():
    """Ordering, asserted rather than assumed. The refusal has to land before
    anything parses rows, or a mismatched file's own row complaints reach the
    reader first and bury the one that explains all of them."""
    response, _ = a_post(
        "claim,sweep_id,writer_note\n"
        ",dd44ee55ff66,a row naming no claim\n"
        "Kaiserkeller,dd44ee55ff66,keep it\n"
    )

    assert response.status_code == 400
    # The row-level complaint would have been "Row 2 names no claim". It is
    # absent because nothing got that far.
    assert "names no claim" not in response.json()["detail"]
