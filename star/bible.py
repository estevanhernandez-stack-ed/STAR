"""What the research bible actually covers, measured against its own room.

A room reports `complete` when the pipeline reached its end. That is not the
same claim as "the bible is whole", and for a stretch of this app's life the
two came apart: `max_output_tokens` on a thinking model bounds thinking PLUS
output, so a room with more research to weigh deliberated longer, left less
budget for the writing, and the document stopped mid-word with a normal finish
and nothing raised. `config.synthesis_thinking_level` carries the replay that
finally pinned it, and the correction — the control being set was the one this
model ignores.

That should make truncation rare. It does not make this module unnecessary,
and the reason is the whole point: seven of the fourteen rooms stored on
2026-08-11 carried a short bible, and every one of them said `complete`
anyway. Whatever the editor turns out to produce, the app has to describe it
accurately rather than assume the good case.

THE MARK IS DERIVED, NEVER AUTHORED. Nothing here is a length threshold or a
quality judgement — both would be this file inventing a standard. The only
question asked is one the room can answer about itself: the researchers filed
findings in these drawers, and the editor was told to write a section for each
one, so which of those sections are in the document? A bible covering three of
four filed drawers is missing one, and that is a count, not an opinion.

Two rules keep the count honest:

  * Only drawers that FILED something are expected. A partial build whose
    logistics researcher came back empty has no logistics section to miss, and
    marking it short would be the app inventing a failure.
  * Only the document's own top-level headings count. `### Escudo Currency &
    Physical Cash Logistics` is a subheading inside section 1, not section 3
    arriving late, and counting it moved a genuinely 1-of-4 room to 2-of-4 in
    the first pass at this.
"""

from __future__ import annotations

import re

from star.models import SECTION_TITLES, Category

_HEADING = re.compile(r"^(#+)\s*(.*)$")


def _section_levels(bible: str, titles: list[str]) -> dict[str, int]:
    """Every heading that names a section, and how deep it sits.

    No CRLF normalisation, deliberately, and this is the one place in the repo
    where leaving it out is right. The usual trap is a pattern anchored to
    `\\n` that passes on one checkout and fails on another; here the match is a
    title looked for INSIDE a stripped heading line, so a trailing `\\r` cannot
    reach it. A `.replace("\\r\\n", "\\n")` was written here first and then
    removed: mutation testing showed the test guarding it could not be made to
    fail, which means the line did nothing and the test was proving it.
    """
    found: dict[str, int] = {}
    for raw in bible.split("\n"):
        match = _HEADING.match(raw.strip())
        if not match:
            continue
        depth, text = len(match.group(1)), match.group(2).casefold()
        for title in titles:
            if title.casefold() in text:
                found.setdefault(title, depth)
                found[title] = min(found[title], depth)
    return found


def _at_section_depth(found: dict[str, int]) -> set[str]:
    """Which of those headings are sections, and which are inside one.

    The document's own outline answers it, not a fixed heading level. The
    editor is a model writing markdown, and it does not use the same depth
    every time: replayed against the same room, one setting produced `##
    1. Setting & Atmosphere` and another produced `### 1. Setting &
    Atmosphere`, both with all four sections and both entirely healthy.

    A `#{1,2}` rule was written here first and scored that second document
    **0 of 4** — a whole bible marked as stopping before its own first
    section, which is the expensive direction for this measurement to be
    wrong in. Caught by replaying a real room, not by a test.

    So depth is read relatively: the shallowest heading that names any
    section is the level this document keeps its sections at, and anything
    deeper is inside one. That still excludes the case the absolute rule
    existed for — `### Escudo Currency & Physical Cash Logistics` sits under
    `## 1. Setting & Atmosphere` in a real stored room, and counting it as
    section three scored that room 2 of 4 instead of 1 of 4.
    """
    if not found:
        return set()
    top = min(found.values())
    return {title for title, depth in found.items() if depth == top}


def coverage(result: object) -> dict | None:
    """Which of the room's filed drawers reached the bible.

    Returns `None` when the question does not apply — no payload, or no bible
    at all. An absent bible is a different fact with its own copy on both
    surfaces, and answering "0 of 4 sections" there would describe a missing
    document as a damaged one.
    """
    if not isinstance(result, dict):
        return None
    bible = result.get("research_bible") or ""
    if not bible.strip():
        return None

    categories = result.get("categories") or {}
    if not isinstance(categories, dict):
        return None

    expected: list[str] = []
    for category in Category:
        drawer = categories.get(category.value) or {}
        if not isinstance(drawer, dict) or not drawer.get("findings"):
            continue
        expected.append(SECTION_TITLES[category])

    present = _at_section_depth(_section_levels(bible, expected))
    missing = [title for title in expected if title not in present]

    if not expected:
        return None
    return {
        "covered": len(expected) - len(missing),
        "expected": len(expected),
        "missing": missing,
        # First-hand, and only for rooms built after the editor's own verdict
        # started being recorded. It catches what counting headings cannot: a
        # document that reached all four sections and still stopped mid-
        # sentence inside the last one. One stored room is exactly that — four
        # sections, ending on the word "outside" — and the heading count calls
        # it whole, correctly, because by its own question it is.
        "truncated": result.get("bible_finish_reason") == "MAX_TOKENS",
    }


def closing_clause(result: object) -> str:
    """How a room's inventory should finish when it gets to the bible.

    A clause rather than a following sentence, deliberately. The first draft
    claimed "and the research bible." and then added a correction after the
    full stop, which is the app asserting something false and taking it back
    in the same breath — a reader skimming the first sentence gets the wrong
    answer, and a reader who reads both learns the app does not know what it
    holds. There is one claim here, and it is either true or it is narrower.

    Says what is observable and stops. It does not name a cause: the output
    ceiling explains the rooms measured on 2026-08-11 and would be a guess
    about any room measured after, and a confident wrong cause is worse for a
    reader than none. What it does carry is the part that changes what the
    reader does next — the findings those sections were written from are still
    in the room, so the research is not lost, only the summary of it.
    """
    counts = coverage(result)
    if not counts:
        return "the research bible."
    if not counts["missing"]:
        if not counts["truncated"]:
            return "the research bible."
        # Every section arrived and the document still stopped short. Said
        # separately because the reader's situation is different: nothing is
        # absent, so there is no list to give them, and the loss is the end of
        # the last section rather than whole subjects.
        return (
            "a research bible that reached all "
            f"{counts['expected']} of its sections and then stopped before it "
            "finished, mid-sentence. Nothing is missing from the room, and "
            "the findings behind every section are filed with their sources."
        )
    missing = counts["missing"]
    names = missing[0] if len(missing) == 1 else _join(missing)
    return (
        f"a research bible that stops early. It covers {counts['covered']} of "
        f"the {counts['expected']} drawers this room filed and never reaches "
        f"{names}. The findings those sections would have been written from "
        "are filed and carry their sources, so what is missing is the "
        "summary, not the research."
    )


def _join(names: list[str]) -> str:
    """`a, b and c`. English, not a comma-joined list, because this sentence
    is read by a person as often as by a model."""
    return f"{', '.join(names[:-1])} and {names[-1]}"
