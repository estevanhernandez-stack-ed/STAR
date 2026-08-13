"""Bringing a writer's marks back, and everything an import must refuse.

This is the first path where text a user typed becomes part of a room's record.
The property that has to hold is narrow and absolute: a room must never read as
better-sourced than its research made it. A verdict, a source and an excerpt
are the department's, hydrated out of a ledger; an import carries a writer's
own decisions and nothing else.
"""

from unittest import mock

from fastapi.testclient import TestClient

from star import server
from star.exports import (
    apply_annotations,
    read_annotations,
    sweep_to_csv,
    unsafe_cell,
)
from star.store import sweep_to_document
from tests.test_scenes import AUTH, ROOM, UID, a_store, filed_room

SWEEP = {
    "room": {"title": "Doctor Who", "era": "1958-1962"},
    "claims": [
        {
            "text": "Kaiserkeller",
            "verdict": "confirmed",
            "scenes": [13],
            "note": "Music venue.",
            "citations": [{"url": "https://a.example", "title": "K", "excerpt": "Opened 1959."}],
        },
        {
            "text": "turning it up to eleven",
            "verdict": "anachronism",
            "scenes": [19],
            "note": "Coined 1984.",
            "citations": [{"url": "https://b.example", "title": "T", "excerpt": "1984."}],
        },
    ],
}


def a_sweep():
    return sweep_to_document(SWEEP, "sw1", "2026-08-12T22:00:00Z")


def test_a_writers_note_comes_back_and_nothing_else_moves():
    marks, complaints = read_annotations(
        "claim,writer_note,dismissed\n"
        "Kaiserkeller,Checked with the club — keep,\n"
        "turning it up to eleven,Cut this line,yes\n"
    )

    assert complaints == []
    assert marks["Kaiserkeller"]["writer_note"] == "Checked with the club — keep"
    assert marks["turning it up to eleven"]["dismissed"] is True

    updated, unmatched, complaints = apply_annotations(a_sweep(), marks)

    assert unmatched == [] and complaints == []
    kaiser = updated["claims"][0]
    assert kaiser["writer_note"] == "Checked with the club — keep"
    assert kaiser["verdict"] == "confirmed", "the verdict is untouched"
    assert kaiser["note"] == "Music venue.", "and so is the department's note"
    assert kaiser["citations"][0]["url"] == "https://a.example", "and the source"


def test_an_import_cannot_introduce_a_verdict_or_a_source():
    """THE PROPERTY THIS FEATURE RESTS ON.

    A room reading as better-sourced than its research made it is the one thing
    that must stay impossible, and this is the first path where text a user
    typed reaches a room's record.
    """
    marks, complaints = read_annotations(
        "claim,writer_note,verdict,source_url,source_excerpt\n"
        "Kaiserkeller,Keep it,anachronism,https://evil.example,Definitely true\n"
    )

    updated, _, edits = apply_annotations(a_sweep(), marks)
    kaiser = updated["claims"][0]

    assert kaiser["writer_note"] == "Keep it", "the writer's own mark lands"
    assert kaiser["verdict"] == "confirmed", "unchanged, and not because the row said so"
    assert [c["url"] for c in kaiser["citations"]] == ["https://a.example"], (
        "no url a spreadsheet supplied is anywhere in this room"
    )
    assert complaints == [], "the file itself was readable; nothing to say about its rows"
    assert any("verdict" in c and "source_url" in c and "Row 2" in c for c in edits), (
        "and the refusal names the columns AND the row, so a writer knows which "
        "change was dropped rather than wondering why it did nothing"
    )


def test_a_note_on_an_untouched_row_is_not_accused_of_editing_it():
    """THE HAPPY PATH, and it used to be an accusation.

    An export carries a verdict and a source on every row. A writer types a
    note into one of those rows and imports it — which is the entire workflow —
    and the old check, which could only see that the columns were PRESENT,
    answered "Row 2 carries verdict, note, source_title, source_url,
    source_excerpt, which the department writes". Nothing had been changed. A
    surface that cries wolf on its own happy path teaches a reader to ignore
    the one complaint that matters.
    """
    marked = sweep_to_csv(a_sweep()).replace("sweep_id\r\n", "sweep_id,writer_note\r\n", 1)
    marked = marked.replace("sw1\r\n", "sw1,Ask the club\r\n", 1)

    marks, complaints = read_annotations(marked)
    _, unmatched, edits = apply_annotations(a_sweep(), marks)

    assert marks["Kaiserkeller"]["writer_note"] == "Ask the club"
    assert complaints == [] and unmatched == []
    assert edits == [], "the row carried the department's columns, and changed none of them"


def test_a_source_moved_to_another_row_is_not_a_change():
    """A spreadsheet gets sorted, and a claim with two sources is two rows. A
    url that came back on a different row of the same claim is still a url that
    claim carries, and asking WHICH row would make the answer depend on how the
    writer sorted the file."""
    document = sweep_to_document(
        {
            "claims": [
                {
                    "text": "Kaiserkeller",
                    "verdict": "confirmed",
                    "scenes": [13],
                    "citations": [
                        {"url": "https://a.example", "title": "A", "excerpt": "one"},
                        {"url": "https://b.example", "title": "B", "excerpt": "two"},
                    ],
                }
            ]
        },
        "sw1",
        "2026-08-12T22:00:00Z",
    )
    marks, _ = read_annotations(
        "claim,source_url,source_title,writer_note\n"
        "Kaiserkeller,https://b.example,A,Swapped round by a sort\n"
    )

    _, _, edits = apply_annotations(document, marks)

    assert edits == []


def test_an_unmodified_export_re_imported_complains_about_nothing():
    """An export carries every one of the department's columns. Refusing on
    their PRESENCE would make the file this feature produces the file it
    rejects."""
    marks, complaints = read_annotations(sweep_to_csv(a_sweep()))

    assert marks == {}, "nothing of the writer's in it, so nothing to apply"
    assert complaints == [], "and no complaint about columns it wrote itself"


def test_a_row_matching_no_claim_is_named_rather_than_dropped():
    """Silence would let a writer annotate twenty claims, import, find
    nineteen, and have no way to learn which one went missing."""
    marks, _ = read_annotations(
        "claim,writer_note\nKaiserkeller,Fine\nA claim that was never here,Also fine\n"
    )

    _, unmatched, _ = apply_annotations(a_sweep(), marks)

    assert unmatched == ["A claim that was never here"]


def test_notes_are_matched_on_claim_text_and_not_on_row_order():
    """A spreadsheet gets sorted. A writer who sorted by verdict before
    annotating would otherwise have every note land on the wrong claim."""
    marks, _ = read_annotations(
        "claim,writer_note\nturning it up to eleven,Cut\nKaiserkeller,Keep\n"
    )

    updated, _, _ = apply_annotations(a_sweep(), marks)

    assert updated["claims"][0]["writer_note"] == "Keep", "Kaiserkeller is still first"
    assert updated["claims"][1]["writer_note"] == "Cut"


def test_a_claim_annotated_on_two_of_its_rows_keeps_both_notes():
    """A claim is several rows when it has several sources. A note a writer
    typed is a note they meant, so the second does not silently replace the
    first."""
    marks, _ = read_annotations(
        "claim,source_url,writer_note\n"
        "Kaiserkeller,https://a.example,Ask the club\n"
        "Kaiserkeller,https://b.example,And check the address\n"
    )

    assert marks["Kaiserkeller"]["writer_note"] == "Ask the club And check the address"


def test_the_escaping_survives_a_round_trip():
    """`safe_cell` prefixes a formula with an apostrophe on the way out, and
    this takes exactly one off on the way back — but never off `'61 Impala`,
    which is a period detail and not an escape."""
    assert unsafe_cell("'=SUM(1)") == "=SUM(1)"
    assert unsafe_cell("'@x") == "@x"
    assert unsafe_cell("'61 Impala") == "'61 Impala", "a writer's own apostrophe stays"
    assert unsafe_cell("Kaiserkeller") == "Kaiserkeller"
    assert unsafe_cell(None) == ""


def test_a_file_that_is_not_an_export_is_refused_with_a_reason():
    marks, complaints = read_annotations("something,else\n1,2\n")
    assert marks == {}
    assert "no `claim` column" in complaints[0]

    marks, complaints = read_annotations("")
    assert marks == {}
    assert complaints


def test_the_endpoint_reports_before_it_writes():
    """Two calls, and the first changes nothing — the arming `delete_room`
    uses, for the same reason: this writes into a filed record."""
    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "sw1", a_sweep())
    body = {"csv": "claim,writer_note\nKaiserkeller,Keep it\n"}

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        client = TestClient(server.app)
        dry = client.post(
            f"/api/rooms/{ROOM}/sweeps/sw1/annotations", json=body, headers=AUTH
        ).json()
        stored_after_dry = client_data.data[f"users/{UID}/rooms/{ROOM}/sweeps/sw1"]
        wet = client.post(
            f"/api/rooms/{ROOM}/sweeps/sw1/annotations",
            json={**body, "apply": True},
            headers=AUTH,
        ).json()
        stored_after_wet = client_data.data[f"users/{UID}/rooms/{ROOM}/sweeps/sw1"]

    assert dry["applied"] is False and dry["matched"] == 1
    assert dry["claims"][0]["writer_note"] == "Keep it", "the preview shows the change"
    assert "writer_note" not in stored_after_dry["claims"][0], "and nothing was written"

    assert wet["applied"] is True
    assert stored_after_wet["claims"][0]["writer_note"] == "Keep it"
    assert stored_after_wet["claims"][0]["verdict"] == "confirmed"


def test_another_accounts_sweep_cannot_be_annotated():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "sw1", a_sweep())

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).post(
            f"/api/rooms/{ROOM}/sweeps/sw1/annotations",
            json={"csv": "claim,writer_note\nKaiserkeller,x\n", "apply": True},
            headers=AUTH,
        )

    assert response.status_code == 404
