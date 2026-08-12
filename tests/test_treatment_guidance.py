"""What a treatment is read for, said where a writer is about to write one.

THE GAP. The app took a treatment and never said what it did with one. A
writer pasting a 15,000-character production treatment — cast list, tone,
themes, per-character arcs — got thinner research than one who pasted four
sentences naming a year and a building, and nothing on the page explained why.
The difference is mechanical and was never written down: `star/agents/intake`
extracts a `StoryProfile` and the planner writes every question from that, so
anything not in those six fields costs input tokens and produces no search.

The guidance is not advice about writing. It is a description of what the
pipeline does, which is why these tests pin it against the model rather than
against a copy of the words.

Both doors, because both take treatments: the intake page for a person, and
`build_room`'s description for an agent that may compose one itself.
"""

from __future__ import annotations

from pathlib import Path

from star.mcp import tools
from star.models import StoryProfile

WEB = Path(__file__).resolve().parent.parent / "web"


def _index() -> str:
    # Normalised at read: working copies are CRLF and CI is not.
    return (WEB / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def _guide() -> str:
    """The disclosure block, not the whole page. A field name that happens to
    appear elsewhere in the markup would otherwise satisfy these tests.

    Whitespace collapsed, because these assertions are about words and the
    markup wraps where the column runs out. `key entities` broke across a line
    and read as absent, which would have sent someone editing the copy to
    satisfy a test that was measuring indentation.
    """
    text = _index()
    start = text.index('<details class="intake-guide">')
    block = text[start : text.index("</details>", start)]
    return " ".join(block.split())


def _human(field: str) -> str:
    return field.replace("_", " ")


def test_the_page_names_every_field_the_intake_actually_extracts():
    """Six fields, and the guidance names six. A page describing five would
    leave a writer silent about something the researchers read; a page
    describing seven would ask for something nothing reads."""
    guide = _guide().casefold()
    missing = [f for f in StoryProfile.model_fields if _human(f) not in guide]

    assert not missing, (
        f"the intake guidance does not mention {missing}. Every question the "
        "researchers ask is written from these fields, so a field the page "
        "does not name is research a writer never knows how to feed."
    )


def test_the_agent_door_names_them_too():
    """An agent composing a treatment has no page to read. The tool
    description is the whole of what it gets."""
    described = tools._TOOLS_BY_NAME["build_room"]["description"].casefold()
    missing = [f for f in StoryProfile.model_fields if _human(f) not in described]

    assert not missing, f"build_room's description does not mention {missing}"


def test_the_page_does_not_claim_a_field_count():
    """`six things` sits in the copy and would be wrong the day StoryProfile
    grows a seventh — the defect web/consent.js shipped when it advertised
    "four calls" the day a fifth tool landed. Here the number is allowed
    ONLY because this test fails when it stops matching the model."""
    guide = _guide().casefold()
    words = {
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
    }
    correct = words[len(StoryProfile.model_fields)]
    wrong = [w for n, w in words.items() if w != correct and f"{w} things" in guide]

    assert f"{correct} things" in guide, (
        f"the guidance should say '{correct} things' — StoryProfile has "
        f"{len(StoryProfile.model_fields)} fields"
    )
    assert not wrong, f"and should not also say {wrong}"


def test_the_guidance_says_what_earns_nothing():
    """The half a writer cannot infer. Tone and theme feel like the most
    important things in a treatment and are invisible to the pipeline, and
    saying only what to include leaves that unsaid."""
    guide = _guide().casefold()

    assert "tone" in guide and "theme" in guide
    assert "buy you nothing" in guide or "buy nothing" in guide


def test_the_guidance_ships_closed():
    """A disclosure, not a lecture. The hint above it is enough for most
    pastes, and an intake that opens with three paragraphs of instructions
    reads as an app apologising for itself."""
    assert "<details class=\"intake-guide\">" in _index()
    assert "<details class=\"intake-guide\" open>" not in _index()
