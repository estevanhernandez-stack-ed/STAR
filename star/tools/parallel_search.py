"""Parallel Search API tool — the required partner integration.

This is the runtime integration for the hackathon's Parallel track:
the official `parallel-web` SDK, imported and called here, and used by
the researcher agents on every room build and script check.

Budget (review fixes M1 + part of H3): when invoked by an ADK agent, the
search count lives in the run's session state, so every run gets its own
budget — no shared global counter to reset or race. The module-level
counter remains only as a fallback for direct script calls.

The ceiling itself now comes from session state too, seeded when the session
is created: a build seeds nothing and gets max_searches_per_build(), a check
seeds max_searches_per_check() (see star/agents/script_check.py). One tool,
two pipelines, and neither has to know what the other spends.
"""

import os

from google.adk.tools import ToolContext
from parallel import Parallel

from star import config

_client: Parallel | None = None
_fallback_count: int = 0


def _get_client() -> Parallel:
    global _client
    if _client is None:
        _client = Parallel(api_key=os.environ["PARALLEL_API_KEY"])
    return _client


def reset_search_budget() -> None:
    """Reset the fallback counter (direct/script calls only)."""
    global _fallback_count
    _fallback_count = 0


def _sources_key(agent_name: str) -> str | None:
    """State key a researcher publishes its sources under, or None.

    One key per researcher, never a shared list. The four researchers run
    concurrently under ParallelAgent and share session state, so a single
    accumulating key would carry the same lost-update race the search counter
    already documents. Per-category keys mean no two writers ever touch the
    same key.
    """
    if not agent_name or not agent_name.startswith("researcher_"):
        return None
    return "sources_" + agent_name.removeprefix("researcher_")


def _publish_sources(tool_context: ToolContext | None, results: list[dict]) -> None:
    """Record real titles into session state so synthesis can cite them.

    The server's SourceLedger is the authority for the API payload, but it
    lives outside the ADK run and synthesis can only see session state. Without
    this, synthesis is asked for source titles it was never given and invents
    every one. Failure here is silent by design: the categories payload is
    unaffected, and the bible simply falls back to bare URLs.
    """
    if tool_context is None:
        return
    key = _sources_key(getattr(tool_context, "agent_name", "") or "")
    if key is None:
        return

    recorded = tool_context.state.get(key) or ""
    cap = config.max_sources_per_category()

    for result in results:
        # Capped deliberately. Every title published here is a title synthesis
        # may enumerate back out, and an uncapped list drove a nine-minute
        # runaway generation on 2026-08-09. A researcher rarely cites more
        # than a dozen sources usefully; the rest are noise that costs output
        # tokens. The ledger still holds every source for the API payload —
        # only synthesis's view is trimmed.
        if recorded.count("\n") >= cap:
            break
        url = str(result.get("url") or "").strip()
        if not url or url in recorded:
            continue
        title = " ".join(str(result.get("title") or "").split())[:120]
        recorded += f"- {title or url} :: {url}\n"

    tool_context.state[key] = recorded


def _budget(tool_context: ToolContext | None) -> int:
    """How many searches this run is allowed, in total.

    Whoever creates the ADK session decides: `star.server` seeds nothing for a
    build and a check seeds `search_budget` (star/agents/script_check.py).

    ABSENT AND ZERO ARE DIFFERENT ANSWERS, which is why this tests `is None`
    rather than the truthiness the spec's one-liner used
    (`state.get("search_budget") or config.max_searches_per_build()`). Absent
    means nobody set a ceiling, so the build default applies. Zero means
    somebody set one, and the value they chose was "spend nothing" —
    `STAR_MAX_SEARCHES_PER_CHECK=0` is the first thing a reader reaches for to
    stop a check spending money. Under `or`, that variable does the opposite of
    what it says: it hands the run the BUILD budget, 30 searches instead of 0.
    A knob that inverts at its safest setting is the same class of defect as
    the admission-order bug in star/server.py, where getting the daily cap and
    the per-IP check backwards cost a whole day's budget in about two seconds.

    Zero is not a lockout. `_spend_budget` refuses the first search, the tool
    returns its budget-exhausted error, and the verifier finishes the list from
    the room's own files with `budget:` notes on what it could not reach — which
    is exactly what a zero ceiling should produce, and it says so on screen
    rather than pretending it looked.
    """
    if tool_context is not None:
        seeded = tool_context.state.get("search_budget")
        if seeded is not None:
            return int(seeded)
    return config.max_searches_per_build()


def _spend_budget(tool_context: ToolContext | None) -> bool:
    """Returns True if a search may proceed; counts the spend."""
    global _fallback_count
    budget = _budget(tool_context)
    if tool_context is not None:
        used = tool_context.state.get("search_count", 0)
        if used >= budget:
            return False
        tool_context.state["search_count"] = used + 1
        return True
    if _fallback_count >= budget:
        return False
    _fallback_count += 1
    return True


def parallel_search(
    objective: str,
    search_queries: list[str],
    tool_context: ToolContext = None,
) -> list[dict]:
    """Search the live web for cited factual research via Parallel's Search API.

    Use this to answer research questions with real sources. Prefer one call
    with a clear objective and 2-4 targeted queries over many vague calls.

    Args:
        objective: What you are trying to establish, stated fully — include
            the era and place, e.g. "Establish what portable radios working
            homicide detectives in Chicago carried in 1987, with specifics."
        search_queries: 2-4 specific web search queries supporting the objective.

    Returns:
        A list of sources: {"title": str, "url": str, "excerpts": [str, ...]}.
        Cite these by URL in your findings. Returns an error dict if the
        per-run search budget is exhausted.
    """
    if not _spend_budget(tool_context):
        # The number names this run's own ceiling, not the build default. A
        # check that ran out at 8 and was told "budget of 30 exhausted" is
        # telling its agent something false about what it just hit.
        return [
            {
                "error": (
                    f"Search budget of {_budget(tool_context)} exhausted "
                    "for this run. Report which questions remain unresearched."
                )
            }
        ]

    search = _get_client().search(
        objective=objective,
        search_queries=search_queries,
    )
    results = [
        {"title": r.title, "url": r.url, "excerpts": list(r.excerpts)}
        for r in search.results
    ]
    _publish_sources(tool_context, results)
    return results
