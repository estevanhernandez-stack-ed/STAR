"""The README is read by people who cannot run the code, so it has to be true.

THE BUG. `README.md` advertised "Four tools and no fifth: list_rooms, get_room,
build_room, check_scene" for a day after `ask_room` and `delete_room` shipped.
That is the identical defect `web/consent.js` shipped when it said "four calls"
on the day a fifth tool landed — a count living in prose that cannot see the
list it counts. The repo learned that lesson, fixed it in one file, and left it
standing in the file a stranger reads first.

A markdown file cannot derive anything at read time. A test is the only thing
that can keep a static claim honest, so the claim gets one.

The assertions here are deliberately narrow: that every tool the door serves is
NAMED, and that no stale count-word sits next to the list. They do not pin
wording, because prose should be free to improve. What they pin is the property
that failed.
"""

from __future__ import annotations

import re
from pathlib import Path

from star.mcp import tools

README = Path(__file__).resolve().parent.parent / "README.md"


def _readme() -> str:
    # Normalised at read: the working copy is CRLF and CI is not, and a pattern
    # anchored to either passes on one checkout and fails on the other.
    return README.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_readme_names_every_tool_the_door_serves():
    """Looked for as a backticked token, not as a substring. The first version
    of this searched for the bare name and mutation testing walked straight
    through it: `delete_room` is inside `delete_roomXX`, so a corrupted name
    still read as present. A test that cannot fail is worse than none, because
    it is also a claim that the thing is checked."""
    text = _readme()
    missing = [
        tool["name"] for tool in tools.TOOLS if f"`{tool['name']}`" not in text
    ]

    assert not missing, (
        f"README.md does not name {missing}. A reader wiring up this server "
        "learns what it can do from that file, and a tool it omits is a tool "
        "that does not exist as far as they know."
    )


def test_the_readme_does_not_claim_a_tool_count_that_can_go_stale():
    """`Four tools and no fifth` was true when written and false the day a
    fifth shipped. A number word in front of `tools` is the shape of that
    mistake, so the shape is what is refused — including the currently correct
    one, because `six` will be wrong the same way on the same day."""
    text = _readme().casefold()
    stale = [
        word
        for word in ("three", "four", "five", "six", "seven", "eight")
        if re.search(rf"\b{word}\b[^.\n]{{0,20}}\btools?\b", text)
    ]

    assert not stale, (
        f"README.md counts the tools in prose: {stale}. Name them instead — "
        "the list is the count, and it cannot disagree with itself."
    )


def test_the_authorization_claim_is_dated():
    """The paragraph this replaced said "measured rather than assumed" and then
    described a server that answered 404 on every discovery path. True when
    written, false by the time a judge read it, and claiming rigor while it was
    wrong. A date does not keep a measurement fresh; it makes staleness
    visible, which is the most a static file can do."""
    text = _readme()
    section = text[text.index("## The MCP server") :]

    assert re.search(r"measured against the live service on \d{4}-\d{2}-\d{2}", section), (
        "the authorization paragraph should carry the date it was measured, so "
        "a reader can weigh it against how old it is"
    )
