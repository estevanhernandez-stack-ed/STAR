"""A room that reports `complete` must not claim a bible it does not have.

THE BUG. `complete` means the pipeline reached its end. It never meant "the
bible is whole", but the copy on both doors said so anyway — the agent door
promised "the story profile, the research plan, four category drawers of
findings with the sources behind them, and the research bible", and the web app
rendered whatever text there was under an unqualified heading. Measured against
the live store on 2026-08-11: seven of the fourteen stored rooms carried a bible
missing at least one section, most of them stopping mid-word partway through
section one, and every one of them described itself as complete.

The generation-side cause is known and narrowed (`config.max_synthesis_thinking
_tokens` splits a budget that thinking used to eat whole) but NOT closed —
three of the seven were built hours after that shipped. These tests hold the
half that does not depend on generation ever being perfect: whatever the editor
produces, the app describes it accurately.

WHAT MAKES THE MARK HONEST. Nothing here is a length threshold. The question is
one the room answers about itself: the researchers filed findings in these
drawers, the editor was told to write a section for each, so which sections are
in the document? The count is derived from the payload, and the section names
come from the same map the editor's instruction is built from — one fact, one
place, checked below in both directions.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from star import bible, server, store
from star.agents.synthesis import synthesis_agent
from star.mcp import tools
from star.models import SECTION_TITLES, Category

AUTH = {"Authorization": "Bearer t"}

FOUR_DRAWERS = {c.value: {"findings": [{"fact": "x"}]} for c in Category}

WHOLE = "\n".join(
    f"## {n}. {SECTION_TITLES[c]}\nprose\n" for n, c in enumerate(Category, start=1)
)


def _room(bible_text: str, categories: dict | None = None) -> dict:
    return {
        "research_bible": bible_text,
        "categories": FOUR_DRAWERS if categories is None else categories,
    }


# --- the measurement --------------------------------------------------------


def test_a_whole_bible_is_not_marked():
    assert bible.coverage(_room(WHOLE)) == {
        "covered": 4,
        "expected": 4,
        "missing": [],
        "truncated": False,
    }


def test_a_bible_that_stops_after_section_one_is_counted_as_such():
    counts = bible.coverage(_room("# Title\n\n## 1. Setting & Atmosphere\nprose"))

    assert counts["covered"] == 1
    assert counts["expected"] == 4
    assert counts["missing"] == ["Objects & Props", "Logistics", "Forces & Conflicts"]


def test_a_subheading_is_not_a_section_arriving_late():
    """The false positive the first pass at this actually shipped. `The 28 Tram
    Heist` covers section one only, but a `###` subheading inside it reads
    `Escudo Currency & Physical Cash Logistics`, and matching anywhere in the
    document scored that room 2 of 4 instead of 1 of 4."""
    counts = bible.coverage(
        _room(
            "# Research Bible\n\n"
            "## 1. Setting & Atmosphere\n"
            "### Escudo Currency & Physical Cash Logistics (May 1974)\n"
            "prose"
        )
    )

    assert counts["covered"] == 1
    assert "Logistics" in counts["missing"]


def test_a_document_that_keeps_its_sections_at_h3_is_still_whole():
    """The false positive an absolute `#{1,2}` rule shipped with, caught by
    replaying a real room rather than by a test. The same room, the same
    prompt, one setting apart, produced `## 1. Setting & Atmosphere` in one
    document and `### 1. Setting & Atmosphere` in the other — both with all
    four sections, both entirely healthy. The second scored 0 of 4: a whole
    bible reported as stopping before its own first section, which is the
    expensive direction for this measurement to be wrong in."""
    deep = "\n".join(
        f"### {n}. {SECTION_TITLES[c]}\n#### A subheading\nprose\n"
        for n, c in enumerate(Category, start=1)
    )
    counts = bible.coverage(_room("# Research Bible: A Room\n\n" + deep))

    assert counts == {"covered": 4, "expected": 4, "missing": [], "truncated": False}


def test_depth_is_read_from_the_document_not_from_a_constant():
    """The two halves have to hold at once: a section is whatever sits at the
    shallowest level that names one, and anything deeper is inside it. Here
    that level is h3, so the h4 line naming Logistics is a subheading — the
    same judgement the `##`/`###` pair gets, one level down."""
    counts = bible.coverage(
        _room(
            "# Research Bible\n"
            "### 1. Setting & Atmosphere\n"
            "#### Cash Logistics and Objects & Props of the Trade\n"
            "prose"
        )
    )

    assert counts["covered"] == 1
    assert counts["missing"] == ["Objects & Props", "Logistics", "Forces & Conflicts"]


def test_only_drawers_that_filed_are_expected():
    """A build whose logistics researcher came back empty has no logistics
    section to miss. Expecting one would be the app inventing a failure."""
    two = {
        "setting": {"findings": [{"fact": "x"}]},
        "objects_props": {"findings": [{"fact": "y"}]},
        "logistics": {"findings": []},
        "forces_conflicts": {},
    }
    counts = bible.coverage(
        _room("## 1. Setting & Atmosphere\na\n## 2. Objects & Props\nb", two)
    )

    assert counts == {"covered": 2, "expected": 2, "missing": [], "truncated": False}


def test_a_heading_indented_the_way_markdown_allows_still_counts():
    """Markdown treats up to three leading spaces as still a heading, and the
    editor is a model writing prose, not a formatter. A section that arrived
    indented used to read as no section at all, which marks a whole bible
    short — the expensive direction for this measurement to be wrong in."""
    two = {
        "setting": {"findings": [{"fact": "x"}]},
        "objects_props": {"findings": [{"fact": "y"}]},
    }
    counts = bible.coverage(
        _room("  ## 1. Setting & Atmosphere\na\n   ## 2. Objects & Props\nb", two)
    )

    assert counts == {"covered": 2, "expected": 2, "missing": [], "truncated": False}


def test_a_stored_bible_with_windows_line_endings_measures_the_same():
    """Kept, but honestly labelled. This started as a guard on a CRLF
    normalisation in `_headings` and could not be made to fail by removing it —
    the match is a title looked for inside a stripped heading line, so a
    trailing \\r never reaches the comparison. The normalisation came out; this
    stayed, as a statement that the property holds rather than a claim to be
    protecting a line of code that does the work."""
    assert bible.coverage(_room(WHOLE.replace("\n", "\r\n")))["missing"] == []


def test_no_bible_is_a_different_fact_and_gets_no_count():
    """An absent bible has its own copy on both surfaces. Answering `0 of 4`
    there would describe a missing document as a damaged one."""
    assert bible.coverage(_room("")) is None
    assert bible.coverage(_room("   \n  ")) is None
    assert bible.coverage(None) is None


# --- what the agent door says -----------------------------------------------


def test_a_whole_room_still_reads_the_way_it_always_did():
    report = tools._room_report("complete", _room(WHOLE))

    assert report.endswith("and the research bible.")
    assert "stops early" not in report


def test_a_short_room_never_claims_the_bible_it_does_not_have():
    """The claim is narrowed, not asserted and then retracted. A reader who
    stops after the first sentence must not come away with the wrong answer."""
    report = tools._room_report("complete", _room("## 1. Setting & Atmosphere\na"))

    assert "and the research bible." not in report
    assert "stops early" in report
    assert "1 of the 4 drawers" in report
    assert "never reaches Objects & Props, Logistics and Forces & Conflicts" in report


def test_one_missing_section_is_named_without_a_list():
    report = tools._room_report(
        "complete",
        _room(WHOLE.replace("## 4. Forces & Conflicts\nprose\n", "")),
    )

    assert "never reaches Forces & Conflicts." in report
    assert " and Forces" not in report


def test_the_drawer_count_is_counted_not_typed():
    """`four category drawers` was a literal, and a complete build with an
    empty drawer was told it had four."""
    two = {
        "setting": {"findings": [{"fact": "x"}]},
        "objects_props": {"findings": [{"fact": "y"}]},
    }
    report = tools._room_report("complete", _room(WHOLE, two))

    assert "2 category drawers" in report
    assert "four category drawers" not in report


def test_one_drawer_is_a_drawer():
    one = {"setting": {"findings": [{"fact": "x"}]}}
    report = tools._room_report("complete", _room("## 1. Setting & Atmosphere\na", one))

    assert "1 category drawer of findings" in report


@pytest.mark.asyncio
async def test_a_shaped_read_still_hears_about_a_short_bible():
    """`get_room` with `shape: "findings"` returns a payload with no bible in
    it. Reporting off that projection told the caller nothing was wrong — the
    shape they asked for deciding what they were allowed to learn."""

    class _Calls:
        async def read_room(self, uid, run_id):
            return {"status": "complete", "result": _room("## 1. Setting & Atmosphere\na")}

    identity = mock.Mock(uid="uid-one")
    payload = await tools._get_room(
        {"run_id": "r", "shape": "findings"}, _Calls(), identity
    )

    assert "stops early" in payload["content"][0]["text"]


@pytest.mark.asyncio
async def test_the_bible_shape_carries_the_measurement_with_the_document():
    """`shape: "bible"` is the one request where the measurement is most
    obviously the caller's business, and it is also the shape that strips the
    room down to two keys. An agent that asked for the bible and got a
    truncated one back with no count has to eyeball prose to notice."""

    class _Calls:
        async def read_room(self, uid, run_id):
            # As `_read_room` really answers: the measurement travels inside
            # the room, not beside it.
            room = _room("## 1. Setting & Atmosphere\na")
            room["bible_coverage"] = bible.coverage(room)
            return {"status": "complete", "result": room}

    payload = await tools._get_room(
        {"run_id": "r", "shape": "bible"}, _Calls(), mock.Mock(uid="uid-one")
    )
    # `_payload` ships one block: the plain-language line, a blank line, then
    # the JSON it is about. The report itself can contain blank lines, so the
    # JSON is what follows the LAST one.
    text = payload["content"][0]["text"]
    room = json.loads(text.rsplit("\n\n", 1)[-1])["room"]

    assert room["bible_coverage"]["covered"] == 1
    assert room["bible_coverage"]["expected"] == 4


# --- the run's own verdict, which counting sections cannot reach -------------


def test_a_bible_with_every_section_can_still_have_been_cut_off():
    """The gap the heading count cannot close. One stored room reached all
    four sections and ends on the word "outside" — whole by the only question
    counting asks, and unfinished by the only one that matters to a reader.
    `finish_reason` is first-hand and settles it."""
    room = _room(WHOLE)
    room["bible_finish_reason"] = "MAX_TOKENS"

    counts = bible.coverage(room)

    assert counts["missing"] == []
    assert counts["truncated"] is True


def test_a_clean_finish_is_not_a_truncation():
    room = _room(WHOLE)
    room["bible_finish_reason"] = "STOP"

    assert bible.coverage(room)["truncated"] is False


def test_a_room_built_before_the_verdict_was_recorded_claims_nothing():
    """Every room stored before this shipped has no finish reason at all, and
    absence must not read as a truncation — that would mark the whole existing
    corpus on a fact nobody measured."""
    assert bible.coverage(_room(WHOLE))["truncated"] is False


def test_a_cut_off_bible_with_every_section_is_not_called_short():
    """Nothing is missing, so there is no list to give the reader, and "short"
    would send them looking for absent sections that are all present."""
    room = _room(WHOLE)
    room["bible_finish_reason"] = "MAX_TOKENS"
    report = tools._room_report("complete", room)

    assert "stops early" not in report
    assert "reached all 4 of its sections" in report
    assert "stopped before it finished" in report


def test_the_stored_document_keeps_the_verdict_because_it_cannot_be_rederived():
    """A bible that was cut off looks, in the text, exactly like a bible about
    a thin subject. The evidence exists once, at generation."""
    doc = store.room_to_document(
        "run-1",
        {
            "research_bible": WHOLE,
            "categories": FOUR_DRAWERS,
            "bible_finish_reason": "MAX_TOKENS",
            "bible_tokens": {"thinking": 15358, "output": 638},
        },
        "complete",
        "2026-08-11T00:00:00Z",
    )

    assert doc["bible_finish_reason"] == "MAX_TOKENS"
    assert doc["bible_tokens"] == {"thinking": 15358, "output": 638}
    # And survives the round trip, or the mark cannot read it back.
    assert store.document_to_room(doc)["bible_finish_reason"] == "MAX_TOKENS"


# --- what the browser is given ----------------------------------------------


def test_the_room_payload_carries_the_count_so_the_browser_need_not_recompute():
    """One derivation, both doors. The alternative is a second implementation
    in a language that cannot see the first, which is how web/consent.js came
    to say `four calls` on the day a fifth tool shipped."""
    client = TestClient(server.app)
    document = {
        "run_id": "r",
        "status": "complete",
        "story_profile": {"title": "t"},
        "research_bible": "## 1. Setting & Atmosphere\na",
        "search_count": 3,
        "categories": FOUR_DRAWERS,
    }
    fake_store = mock.Mock()
    fake_store.get.return_value = document

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        body = client.get("/api/rooms/r", headers=AUTH).json()

    # Read where the BROWSER reads it. The first version of this test asserted
    # `body["bible_coverage"]`, the browser's test asserted
    # `result.bible_coverage`, both passed, and the live page rendered nothing.
    assert body["result"]["bible_coverage"]["covered"] == 1
    assert body["result"]["bible_coverage"]["expected"] == 4
    assert body["result"]["bible_coverage"]["missing"] == [
        "Objects & Props",
        "Logistics",
        "Forces & Conflicts",
    ]


def test_a_whole_room_ships_a_coverage_the_browser_will_stay_quiet_about():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "r",
        "status": "complete",
        "story_profile": {"title": "t"},
        "research_bible": WHOLE,
        "search_count": 3,
        "categories": FOUR_DRAWERS,
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        body = client.get("/api/rooms/r", headers=AUTH).json()

    assert body["result"]["bible_coverage"]["missing"] == []


# --- the two ends of the one fact -------------------------------------------


def test_the_editor_is_asked_for_the_sections_this_check_looks_for():
    """The drift guard that makes the mark meaningful. If the instruction and
    the map disagree, this file measures a document against sections nobody
    asked for and marks every healthy room short."""
    instruction = synthesis_agent.instruction

    for n, category in enumerate(Category, start=1):
        assert f"{n}. {SECTION_TITLES[category]}" in instruction


def test_the_instruction_states_its_section_count_by_listing_them():
    """`four sections` was typed above a list of four. Two places for one fact
    is one place too many, and this one is handed to a model."""
    assert "four sections" not in synthesis_agent.instruction
