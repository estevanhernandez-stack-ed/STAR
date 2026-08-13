"""Per-run ledger of every source the Parallel Search API actually returned.

The researchers write findings as prose and cite URLs. Where `star/findings.py`
builds the `categories` payload, titles and excerpts are never taken from the
model — they are hydrated from this ledger, which records only what
`parallel_search` genuinely returned. A cited URL absent from the ledger came
from nowhere, and gets flagged rather than rendered as a source. The
`research_bible` reaches the same standard through `sources_<category>`
session state rather than through this ledger — see `star/findings.py`'s
module docstring.

ADK wraps a function tool's return value before placing it on the response
part. `unwrap_results` handles the four wrappings observed against a live ADK
2.6.2 run (see `tests/test_response_shape.py`). It is not proof against every
future envelope: a wrapping this function doesn't recognize returns `[]`
rather than raising, so an ADK upgrade that changes the shape again empties
the ledger silently instead of breaking loudly. `star.server._execute` guards
that specific failure by checking for a nonzero search count against a still
empty ledger and pushing a warning event.
"""

from dataclasses import dataclass, field

_WRAPPER_KEYS = ("result", "results", "response", "output")


@dataclass
class LedgerEntry:
    """One source, merged across every researcher that found it."""

    url: str
    title: str = ""
    excerpts: list[str] = field(default_factory=list)
    found_by: set[str] = field(default_factory=set)


def unwrap_results(payload: object) -> list[dict]:
    """Pull `parallel_search`'s `list[dict]` return value out of ADK's wrapping."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        if "url" in payload:
            return [payload]
        for key in _WRAPPER_KEYS:
            if key in payload:
                return unwrap_results(payload[key])
    return []


class SourceLedger:
    """Accumulates search results for a single run. No I/O, no model calls."""

    def __init__(self) -> None:
        self._entries: dict[str, LedgerEntry] = {}

    def record(self, agent: str, payload: object) -> int:
        """Record one tool response. Returns how many sources were taken in.

        Results without a URL are skipped, which quietly drops the budget-
        exhausted error dict `parallel_search` returns when a run runs dry.
        """
        taken = 0
        for result in unwrap_results(payload):
            url = str(result.get("url") or "").strip()
            if not url:
                continue

            entry = self._entries.get(url)
            if entry is None:
                entry = LedgerEntry(url=url)
                self._entries[url] = entry

            title = str(result.get("title") or "").strip()
            if title and not entry.title:
                entry.title = title

            for excerpt in result.get("excerpts") or []:
                if excerpt and excerpt not in entry.excerpts:
                    entry.excerpts.append(excerpt)

            entry.found_by.add(agent)
            taken += 1
        return taken

    def get(self, url: str) -> LedgerEntry | None:
        return self._entries.get(url)

    def has(self, url: str) -> bool:
        return url in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def urls(self) -> list[str]:
        return list(self._entries)


def ledger_from_room(document: dict) -> SourceLedger:
    """Rebuild a ledger from a filed room, so a check can consult it.

    Pipeline B asks the room before it spends a search, and "the room
    answered" has to mean the same thing "a fresh search answered" means: a
    URL with a real title and a real excerpt behind it. The citations in a
    stored room already meet that bar — `star/findings.py` hydrated every one
    of them out of the build's own ledger, so nothing in this walk was ever
    authored by a model.

    The walk goes back through `record()` rather than filling `_entries`
    directly. That function is the only place in the project that decides what
    counts as a source, how two sightings of a URL merge, and when an excerpt
    is a duplicate; a second accumulator here would be a second set of those
    rules, drifting quietly from the first.

    `categories` is a dict keyed by category value (`star/store.py:36`, filled
    by `star/server.py:_build_categories`). A document missing that block, or
    carrying something other than a dict there, yields an empty ledger rather
    than raising: an empty room is a supported state — a partial or
    interrupted build files nothing and a check against it runs on fresh
    search alone — and taking a whole check down over the shape of a room is a
    worse answer than running it without the files.
    """
    ledger = SourceLedger()
    _record_room(ledger, document)
    return ledger


def _record_room(ledger: SourceLedger, document: dict) -> None:
    """Walk one stored room's citations into an existing ledger.

    Factored out so `ledger_from_chain` can fill ONE ledger from several rooms
    without a second copy of this walk, and without either of them reaching
    into `_entries`. `record()` stays the only thing that decides what counts
    as a source and how two sightings of a url merge.
    """
    categories = (document or {}).get("categories")
    if not isinstance(categories, dict):
        return

    for category, doc in categories.items():
        results = [
            {
                "url": citation.get("url"),
                "title": citation.get("title"),
                "excerpts": [citation.get("excerpt")],
            }
            for finding in (doc or {}).get("findings") or []
            for citation in (finding or {}).get("citations") or []
        ]
        if results:
            ledger.record(f"room:{category}", results)


def ledger_from_chain(documents) -> SourceLedger:
    """One ledger holding every source in a story's chain of rooms.

    A check against a room that FOLLOWS another is given the whole chain's
    files, so the verifier may cite a url it only ever saw in the parent. That
    url has to be findable when the verdict is hydrated, or `annotate` finds it
    in neither ledger and star/verdicts.py downgrades a correct answer to
    unverifiable — telling the reader the source is in neither the room's files
    nor this check's searches, when it was in the room next door all along.

    Stacking without this makes answers WORSE rather than better, which is a
    louder failure than the feature simply not working, and it is invisible:
    the check comes back looking like an honest "we could not settle this".

    Two rooms citing the same page merge into one entry carrying both excerpts,
    because `record()` already decides that and this does not get its own rules.

    `documents` is an iterable of stored room documents. Order does not matter —
    a ledger is a lookup, not a list.
    """
    merged = SourceLedger()
    for document in documents or ():
        _record_room(merged, document)
    return merged
