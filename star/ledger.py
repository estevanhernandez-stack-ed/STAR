"""Per-run ledger of every source the Parallel Search API actually returned.

The researchers write findings as prose and cite URLs. Where `star/findings.py`
builds the `categories` payload, titles and excerpts are never taken from the
model — they are hydrated from this ledger, which records only what
`parallel_search` genuinely returned. A cited URL absent from the ledger came
from nowhere, and gets flagged rather than rendered as a source. (This
guarantee does not reach `research_bible`, a separate synthesis path — see
`star/findings.py`'s module docstring.)

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
