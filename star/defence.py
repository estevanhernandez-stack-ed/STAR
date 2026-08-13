"""One filed fact, with everything the department can honestly say about it.

The shape a writer hands to whoever is challenging a detail: the fact, the
sources behind it, the page's own words, the date those pages came back, and
whether the build filed it or the writer went and got it afterwards.

HERE RATHER THAN IN star/mcp/tools.py, which is where it started, because both
doors need the identical answer. The browser prints this card and an agent
returns it, and a second implementation of "which finding did they mean" is how
the printed sheet and the agent's reply come to disagree about what a room
says — in front of the one person in the process who is already sceptical.

Pure. No IO, no clock, no model. Everything below is selection and reshaping of
a document that already exists.
"""


def normalised(text: object) -> str:
    """One fact, comparable. Case and runs of whitespace only.

    Deliberately not the tokeniser `ask_room` ranks with. That one is looking
    for the findings that BEAR on a question and is right to be loose; this is
    looking for the same sentence the caller is holding, and a loose match here
    defends a claim the writer did not make. Punctuation stays in for the same
    reason: two facts differing only in a number are two facts.
    """
    return " ".join(str(text or "").split()).casefold()


def locate(result: dict, fact: str) -> tuple[str, dict] | None:
    """The one finding a caller means, or None. Never a ranked guess.

    Exact match first, then a fragment contained in exactly one finding. Both
    are cases with a right answer; everything else is not.

    Containment earns its place rather than being generosity: an agent holding
    a fact from `ask_room` has the sentence exactly, but a writer typing what
    an executive just read off a page has a piece of it. The fragment has to
    single out one finding, though — two findings sharing it is an ambiguous
    ask, and answering it by storage order would present whichever the
    researcher happened to write first as the one they meant.

    Returning None is the useful answer in every other case. A card built
    around the nearest match puts real sources, real excerpts and a real
    retrieval date behind a sentence the room never filed, and hands it to the
    writer in the exact conversation where being confidently wrong costs most.
    """
    wanted = normalised(fact)
    if not wanted:
        return None

    contained: list[tuple[str, dict]] = []
    for name, drawer in (result.get("categories") or {}).items():
        for finding in (drawer or {}).get("findings") or []:
            have = normalised((finding or {}).get("fact"))
            if have == wanted:
                return name, finding
            if wanted in have:
                contained.append((name, finding))
    return contained[0] if len(contained) == 1 else None


def card(result: dict, category: str, finding: dict, run_id: str) -> dict:
    """One located finding, in the shape both doors render."""
    profile = result.get("story_profile") or {}
    requisition = str(finding.get("requisition") or "").strip()
    # The finding's own date when it has one, the room's otherwise. A build's
    # searches all ran while the room was being made, so `created_at` is the
    # honest answer for those; a finding requisitioned later was retrieved then
    # and carries its own. The same rule web/clip.js applies to the RET stamp,
    # and it matters most here — the fact a writer went and got because someone
    # doubted the room is the one most likely to be challenged again.
    retrieved = str(finding.get("retrieved_at") or "").strip() or (
        result.get("created_at") or ""
    )
    return {
        "run_id": run_id,
        "room": {
            "title": profile.get("title") or "Untitled room",
            "era": profile.get("era") or "",
            "genre": profile.get("genre") or "",
        },
        "category": category,
        "fact": finding.get("fact") or "",
        "retrieved_at": retrieved,
        # How this fact came to be in the room, and what was asked if a writer
        # asked for it. The question is part of the provenance a challenger is
        # owed: it says the room was interrogated on this exact point.
        "filed_by": "requisition" if requisition else "build",
        "requisition": requisition,
        "sources": [
            {
                "url": (citation or {}).get("url") or "",
                "title": (citation or {}).get("title") or "",
                "excerpt": (citation or {}).get("excerpt") or "",
            }
            for citation in finding.get("citations") or []
        ],
        # Kept and named rather than dropped. A url the researcher wrote that
        # no search result carried is not a source, and the one place it must
        # not silently vanish is the sheet someone is about to cite from.
        "unsourced_urls": list(finding.get("unverified_urls") or []),
    }
