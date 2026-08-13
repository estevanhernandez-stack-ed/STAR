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

import re
from urllib.parse import urlparse

# WHAT THE ADDRESS SAYS ABOUT ITSELF, and nothing beyond that.
#
# A card printed off a real room quoted a Beatles Bible forum post — a reader's
# complaint that the boots did not fit him — under a fact about the shoemakers
# who made them. The quotation was real, the address was real, and the sheet
# gave a writer no way to see that the words were some stranger's rather than
# the site's own reporting. Handing that to a producer as a receipt is the
# failure this project exists to avoid, one level below where it usually looks
# for it: not an invented source, a real source misread.
#
# These match segments a publisher chose for software whose entire purpose is
# posts by readers. They are NOT a quality judgement — a forum thread is
# frequently the only place a detail survives, and the Gdansk tram timetable is
# exactly that — and they are not an inference about content. The url says
# `/forum/`; the card says the url says `/forum/`.
#
# HIGH CONFIDENCE ONLY, because the costly error is the false positive. Telling
# a writer to distrust a newspaper is worse than failing to flag a forum, since
# the flag is advice they will act on. Measured against all 567 distinct
# addresses in the account on 2026-08-12: 8 marked, every one genuinely a
# forum, none missed among the ambiguous.
#
# `talk`, `board`, `discussion`, `answers` and `questions` are deliberately
# absent. A TED talk lives under /talks/, a company's /board/ is its directors,
# and an /answers/ path is as often an official FAQ as a Q&A site.
_USER_WRITTEN_HOSTS = re.compile(
    r"(^|\.)(reddit\.com|quora\.com|stackexchange\.com|stackoverflow\.com|"
    r"serverfault\.com|superuser\.com|answers\.yahoo\.com)$",
    re.IGNORECASE,
)
_USER_WRITTEN_HOST_PREFIX = re.compile(r"^(forum|forums|boards|community)\.", re.IGNORECASE)
_USER_WRITTEN_PATH = re.compile(
    r"(^|/)(forum|forums|viewtopic|viewthread|showthread|thread|threads|"
    r"comments|phpbb|smf|vbulletin)(/|$|\.php)",
    re.IGNORECASE,
)


def address_is_user_written(url: object) -> bool:
    """Does this address say, in its own path or host, that readers write here?

    False is not a claim that a page is editorial. It is the absence of a
    marker, which is why every surface that prints this says so — a forum whose
    url does not announce itself is invisible here, and copy implying otherwise
    would turn a partial signal into a guarantee.
    """
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return False
    return bool(
        _USER_WRITTEN_HOSTS.search(parsed.netloc)
        or _USER_WRITTEN_HOST_PREFIX.search(parsed.netloc)
        or _USER_WRITTEN_PATH.search(parsed.path)
    )


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
                # Read off the address, never off the text. See the note above
                # `address_is_user_written`: the point is to stop a writer
                # handing over a stranger's forum post believing it is the
                # site's own reporting, without this file ever ranking one
                # source against another.
                "user_written": address_is_user_written(
                    (citation or {}).get("url") or ""
                ),
            }
            for citation in finding.get("citations") or []
        ],
        # Kept and named rather than dropped. A url the researcher wrote that
        # no search result carried is not a source, and the one place it must
        # not silently vanish is the sheet someone is about to cite from.
        "unsourced_urls": list(finding.get("unverified_urls") or []),
    }
