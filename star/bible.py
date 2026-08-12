"""What the research bible actually covers, measured against its own room.

A room reports `complete` when the pipeline reached its end. That is not the
same claim as "the bible is whole", and for a stretch of this app's life the
two came apart: `max_output_tokens` on a thinking model bounds thinking PLUS
output, so a room with more research to weigh deliberated longer, left less
budget for the writing, and the document stopped mid-word with a normal finish
and nothing raised. See `config.max_synthesis_thinking_tokens`, which splits
the budget and is why this is rarer than it was.

Rarer, not gone. Measured across the 13 stored `complete` rooms on 2026-08-11,
seven carried a bible missing at least one section, and three of those were
built hours after the split was serving. So this module exists for the half
that ships regardless of how good generation gets: whatever the bible turns
out to be, the app has to describe it accurately.

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

# `#` or `##` followed by something that is not another `#`. Markdown's own
# rule for a top-level heading, applied to a document written by a model that
# was asked for numbered sections and usually obliges.
_TOP_LEVEL = re.compile(r"^#{1,2}[^#]")


def _headings(bible: str) -> str:
    """Every top-level heading in the document, folded for comparison.

    No CRLF normalisation, deliberately, and this is the one place in the repo
    where leaving it out is right. The usual trap is a pattern anchored to
    `\\n` that passes on one checkout and fails on another; here the match is a
    title looked for INSIDE a stripped heading line, so a trailing `\\r` cannot
    reach it. A `.replace("\\r\\n", "\\n")` was written here first and then
    removed: mutation testing showed the test guarding it could not be made to
    fail, which means the line did nothing and the test was proving it.
    """
    return "\n".join(
        line.strip() for line in bible.split("\n") if _TOP_LEVEL.match(line.strip())
    ).casefold()


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

    headings = _headings(bible)
    expected: list[str] = []
    missing: list[str] = []
    for category in Category:
        drawer = categories.get(category.value) or {}
        if not isinstance(drawer, dict) or not drawer.get("findings"):
            continue
        title = SECTION_TITLES[category]
        expected.append(title)
        if title.casefold() not in headings:
            missing.append(title)

    if not expected:
        return None
    return {
        "covered": len(expected) - len(missing),
        "expected": len(expected),
        "missing": missing,
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
    if not counts or not counts["missing"]:
        return "the research bible."
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
