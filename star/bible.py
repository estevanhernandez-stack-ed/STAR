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


_VERIFY = re.compile(r"(?i)verify\s+before\s+writing")

#: Lines that ARE the block's opener rather than its content. A heading or a
#: bare label carries no note, and the note is whatever comes after it.
_LABEL_ONLY = re.compile(r"(?i)^[>#*\-\s]*verify\s+before\s+writing[:\s*]*$")

#: The empty case, and the reason this filter exists at all. Synthesis is asked
#: for a "Verify before writing" note per section and answers every time, so
#: most sections carry "None noted in field findings" — six of the eight blocks
#: in one stored room. Surfacing those as warnings would train a reader to skim
#: past the one that matters, which is the exact failure this feature exists to
#: prevent. Deliberately NARROW: it drops only unambiguous nothing-to-report
#: statements, because a false negative here is a caution silently withheld and
#: a false positive is one line of noise.
#: Tested against the CLEANED note, never the raw line. The first version
#: matched the raw one and leaked every time, because stripping the label off a
#: single-line block leaves a colon the prefix class did not cover — "None
#: noted in field findings." reached the summary as a caution. Matching what a
#: reader would actually see removes the whole class of that mistake.
_NOTHING = re.compile(r"(?i)^(?:none|no\b|n/?a|nothing)\b[^.]*\.?$")


def verify_notes(result: object) -> list[str]:
    """The cautions the researchers flagged, lifted out of the bible's prose.

    THE PROBLEM THIS SOLVES. Synthesis is instructed to preserve researchers'
    uncertainty flags in a "Verify before writing" note per section, and it
    does — one stored room carries four, including the one that named a false
    premise in its own writer's treatment: the intake said a September 1977
    blackout, the research says July 13-14. That is the single most valuable
    line in the document and it sits five screens down inside section one. A
    writer who skims the drawers and never reads the bible top to bottom misses
    the one line that saves them a rewrite.

    PARSED FROM MODEL PROSE, WHICH IS A COMPROMISE AND IS WORTH NAMING. There
    is no structured field for these; the editor writes them into the document
    in whatever shape it likes, and across stored rooms that has been a
    blockquote, an h3, an h4, a list item, and a bare line. So this reads
    loosely and forgives formatting, and it errs toward INCLUDING a note it is
    unsure about. The cost of a wrongly-included line is one line; the cost of
    a wrongly-dropped one is a caution the department found and then withheld.
    """
    if not isinstance(result, dict):
        return []
    bible = result.get("research_bible") or ""
    if not bible.strip():
        return []

    notes: list[str] = []
    lines = bible.split("\n")
    for index, raw in enumerate(lines):
        if not _VERIFY.search(raw):
            continue
        # The note is either on this line after the label, or on the lines
        # under it. A heading-only opener means look below.
        if _LABEL_ONLY.match(raw.strip()):
            body = _join_wrapped(_collect(lines, index + 1))
        else:
            body = [_VERIFY.sub("", raw, count=1)]
        for line in body:
            text = _clean(line)
            if text and not _says_nothing(text) and text not in notes:
                notes.append(text)
    return notes


def _collect(lines: list[str], start: int) -> list[str]:
    """The lines belonging to a block that opened with a bare label.

    Stops at the first heading or the first blank line that is not inside a
    blockquote — the editor separates a note from the source list that follows
    it with exactly one of those, in every stored room checked.
    """
    body: list[str] = []
    for raw in lines[start : start + 12]:
        stripped = raw.strip()
        if stripped.startswith("#"):
            break
        if not stripped:
            if body:
                break
            continue
        body.append(raw)
    return body


def _join_wrapped(body: list[str]) -> list[str]:
    """One note per bullet, however many lines the editor spread it over.

    Markdown source is usually not hard-wrapped and every stored room's notes
    sit on one line each, so this is protection rather than a fix for observed
    data. It is worth having anyway because the failure is loud and ugly: a
    wrapped caution became three separate cautions, each a sentence fragment,
    printed as three things to check. Found by a test fixture that happened to
    wrap where the real document did not.

    A line starting a new bullet starts a new note. Anything else continues the
    one before it.
    """
    joined: list[str] = []
    for raw in body:
        content = re.sub(r"^>\s*", "", raw.strip())
        if not joined or re.match(r"^[-*+]\s+", content):
            joined.append(content)
        else:
            joined[-1] = f"{joined[-1]} {content}".strip()
    return joined


def _says_nothing(text: str) -> bool:
    """Is this a note reporting that there is nothing to report?

    Checked twice: on the whole note, and on whatever follows a short leading
    label. The editor writes both `None noted in field findings.` and
    `Note for writer: No active setting uncertainty flags were noted`, and only
    the first is caught by reading from the start. A label is any short run
    before a colon — long enough to hold "Note for writer", too short to
    swallow "Date Discrepancy: The story intake notes reference…", where the
    text after the colon is the caution itself and must never be tested.
    """
    if _NOTHING.match(text):
        return True
    label, colon, rest = text.partition(":")
    # The remainder gets its own strip. `Note for writer:* No active flags` puts
    # an unpaired italic marker between the colon and the word, and testing
    # from a `*` never matches anything — so the note read as a caution.
    rest = rest.strip().lstrip("*").strip()
    return bool(colon) and len(label) <= 24 and bool(_NOTHING.match(rest))


def _clean(line: str) -> str:
    """One note, without the markdown it arrived wearing."""
    text = line.strip()
    text = re.sub(r"^[>\-*\s]+", "", text)
    text = _VERIFY.sub("", text, count=1)
    text = text.lstrip(":*- ").strip()
    # Every asterisk goes, paired or not. Two regexes unwrapping `**bold**` and
    # `*italic*` stood here first and mutation testing could not make either
    # fail — correctly, because this line already does their whole job. What it
    # also does is the part they could not: `*Date Discrepancy:* The story
    # intake…` loses its opening marker to the prefix strip above, leaving the
    # closing one with nothing to pair against, and it reached a reader as
    # "Date Discrepancy:*". A trailing one was likewise enough to defeat the
    # end-anchor on the nothing-to-report filter, so "None.*" printed as a
    # caution.
    #
    # Links and citation markers are left alone. A reader is better off seeing
    # "[1, 2]" than seeing it removed: it is how they find the source behind a
    # caution once they open the bible itself.
    return text.replace("*", "").strip()


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
