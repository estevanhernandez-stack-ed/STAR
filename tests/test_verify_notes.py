"""The cautions belong where a reader is, not only where they were written.

THE ASK, from `docs/judge-critique-round2-2026-08-11.md`. The premise check
works — a treatment claiming a September 1977 blackout came back with a "Verify
before writing" block naming the real date, July 13-14 — and the review's one
complaint was placement: "the callout lives inside the bible's prose. It
belongs in the room's *summary* too — a writer who skims drawers and never
reads the bible top-to-bottom shouldn't miss the one line that saves them a
rewrite." An agent has it worse: it reads the tool's sentence first and may
never request the bible at all.

WHAT MAKES THIS DELICATE. There is no structured field for these. Synthesis is
instructed to write one note per section and it obliges every time, so most of
them say nothing — six of the eight blocks in one stored room read "None noted
in field findings." Surfacing those trains a reader to skim past the one that
matters, which is the exact failure this feature exists to prevent. So the
extraction reads model prose loosely and forgives formatting, and the
nothing-to-report filter is narrow on purpose: a wrongly-included line costs one
line, a wrongly-dropped one is a caution the department found and withheld.

Measured against all 16 stored rooms on 2026-08-12: 20 notes, no empty ones
leaked, no stray markdown markers.
"""

from __future__ import annotations

from unittest import mock

from fastapi.testclient import TestClient

from star import bible, server
from star.mcp import tools

AUTH = {"Authorization": "Bearer t"}

# The real shape, copied from the BROWNOUT room's stored bible. Blockquote,
# bold label, italic sub-label, citation markers — one of five formats seen
# across stored rooms, and the one carrying the premise catch.
BROWNOUT = """## 1. Setting & Atmosphere

Prose about the heat.

> **Verify before writing:**
> - *Date Discrepancy:* The story intake notes reference a "September 1977"
blackout, whereas historical research confirms the citywide blackout occurred
on July 13-14, 1977 [1, 2].

#### Section Sources
1. Something — https://example.com
"""


def _room(bible_text: str) -> dict:
    return {"research_bible": bible_text, "categories": {}}


# --- what counts as a note ---------------------------------------------------


def test_the_premise_catch_is_lifted_out_of_the_bible():
    notes = bible.verify_notes(_room(BROWNOUT))

    assert len(notes) == 1
    assert notes[0].startswith("Date Discrepancy:")
    assert "September 1977" in notes[0] and "July 13-14" in notes[0]


def test_the_markdown_it_arrived_wearing_does_not_come_with_it():
    """`> - *Date Discrepancy:*` loses its opening marker to the prefix strip,
    which leaves the closing one unpaired — and it reached a reader as
    "Date Discrepancy:*"."""
    assert "*" not in bible.verify_notes(_room(BROWNOUT))[0]


def test_citation_markers_are_left_alone():
    """A reader is better off seeing [1, 2] than seeing it removed: it is how
    they find the source behind a caution in the bible itself."""
    assert "[1, 2]" in bible.verify_notes(_room(BROWNOUT))[0]


def test_a_note_reporting_nothing_is_not_a_note():
    for empty in (
        "> **Verify before writing:** None noted in field findings.",
        "Verify before writing: None noted by field researchers.",
        "### Verify Before Writing\n- *Verify before writing:* None.",
        "> - *Verify before writing:* No specific setting uncertainties flagged.",
    ):
        assert bible.verify_notes(_room(empty)) == [], empty


def test_a_nothing_note_wearing_a_label_is_still_nothing():
    """`Note for writer:* No active setting uncertainty flags were noted` reads
    as a caution from the start, and an unpaired marker sits between the colon
    and the word. Both had to be seen through; this one shipped past two
    earlier versions of the filter."""
    # INSIDE a block, which is the only place these appear. The first version
    # of this test passed a line carrying no "Verify before writing" marker at
    # all, so it proved that an unrelated line yields no notes — true, and
    # nothing to do with the filter it claimed to guard. Mutation testing found
    # it by deleting the branch and watching the test stay green.
    text = (
        "> **Verify before writing:**\n"
        "> - *Note for writer:* No active setting uncertainty flags were noted."
    )

    assert bible.verify_notes(_room(text)) == []


def test_a_label_is_short_or_it_is_not_a_label():
    """A real caution whose own sentence happens to contain a colon, followed
    by a word the nothing-filter recognises. Treating everything before a colon
    as a label would test "none of the three bridges..." against that filter
    and drop a caution the department went and found.

    The earlier version of this used the premise catch, where what follows the
    colon starts "The story intake" and matches nothing — so widening the label
    limit changed no outcome and the test held nothing."""
    text = (
        "> **Verify before writing:**\n"
        "> - The department checked every crossing it could find and reports "
        "this: none of the three bridges carried vehicle traffic that night."
    )

    notes = bible.verify_notes(_room(text))

    assert len(notes) == 1
    assert "three bridges" in notes[0]


def test_a_heading_ends_the_block_even_with_no_blank_line_before_it():
    """Every stored room happens to leave a blank line between a note and the
    source list under it, which meant the heading rule could be deleted without
    a test noticing. A document that does not is entirely plausible, and the
    failure would print a URL to the reader as a thing to verify."""
    text = (
        "> **Verify before writing:**\n"
        "> - A real caution here.\n"
        "#### Section Sources\n"
        "1. Something — https://example.com"
    )

    assert bible.verify_notes(_room(text)) == ["A real caution here."]


def test_every_format_the_editor_actually_uses_is_read():
    """Five shapes seen across stored rooms. The editor writes these however it
    likes, and a parser that only knew one of them would silently return
    nothing for four rooms in five."""
    shapes = [
        "> **Verify before writing:**\n> - A real caution here.",
        "### Verify Before Writing\n- A real caution here.",
        "Verify before writing: A real caution here.",
        "#### Verify before writing\nA real caution here.",
        "> *Verify before writing:* A real caution here.",
    ]
    for shape in shapes:
        assert bible.verify_notes(_room(shape)) == ["A real caution here."], shape


def test_the_same_caution_twice_is_reported_once():
    """Synthesis repeats a note under more than one section often enough to
    matter, and a summary that says the same thing twice reads as two problems.
    """
    doubled = (
        "> **Verify before writing:** A real caution here.\n\n"
        "## 2. Objects\n\n"
        "> **Verify before writing:** A real caution here.\n"
    )

    assert bible.verify_notes(_room(doubled)) == ["A real caution here."]


def test_a_room_with_no_bible_has_no_notes():
    assert bible.verify_notes(_room("")) == []
    assert bible.verify_notes(None) == []


def test_the_block_stops_at_the_source_list_that_follows_it():
    """Every stored room puts a source list directly under the note. Reading
    into it would print a URL as a caution."""
    notes = bible.verify_notes(_room(BROWNOUT))

    assert not any("example.com" in note for note in notes)


# --- where they show up ------------------------------------------------------


def test_the_agent_door_names_the_cautions_rather_than_counting_them():
    """"3 cautions" would make a caller fetch the document to learn whether any
    of them mattered, and one of these is routinely the department telling a
    writer their own premise is dated wrong."""
    report = tools._room_report("complete", _room(BROWNOUT))

    assert "verify before writing" in report.lower()
    assert "September 1977" in report


def test_one_caution_is_spoken_of_in_the_singular():
    report = tools._room_report("complete", _room(BROWNOUT))

    assert "flagged one thing" in report


def test_a_room_with_nothing_flagged_says_nothing():
    """No empty clause on the common case: a clean room's report should read
    exactly as it did before this existed."""
    report = tools._room_report("complete", _room("## 1. Setting\nprose"))

    assert "verify" not in report.lower()


def test_the_room_payload_carries_the_notes_for_the_browser():
    """One extraction, both doors. Parsing the bible again in JS would be a
    second implementation of one fact in a second language — how web/consent.js
    came to say "four calls" the day a fifth tool landed."""
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "r",
        "status": "complete",
        "story_profile": {"title": "t"},
        "research_bible": BROWNOUT,
        "search_count": 3,
        "categories": {},
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        body = client.get("/api/rooms/r", headers=AUTH).json()

    notes = body["result"]["verify_notes"]
    assert len(notes) == 1
    assert "September 1977" in notes[0]


def test_a_clean_room_ships_no_empty_key():
    """Absent rather than empty. The browser renders nothing for a missing key
    and nothing for an empty list, but an empty caution block in a payload is
    an invitation for some future reader to render an empty caution block."""
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "r",
        "status": "complete",
        "story_profile": {"title": "t"},
        "research_bible": "## 1. Setting\nprose",
        "search_count": 3,
        "categories": {},
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        body = client.get("/api/rooms/r", headers=AUTH).json()

    assert "verify_notes" not in body["result"]
