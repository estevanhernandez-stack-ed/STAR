"""Parallel Search API tool — the required partner integration.

This is the runtime integration for the hackathon's Parallel track:
the official `parallel-web` SDK, imported and called here, and used by
the researcher agents on every room build and script check.

Budget (review fixes M1 + part of H3): when invoked by an ADK agent, the
search count lives in the run's session state, so every run gets its own
budget — no shared global counter to reset or race. The module-level
counter remains only as a fallback for direct script calls.
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
    for result in results:
        url = str(result.get("url") or "").strip()
        if not url or url in recorded:
            continue
        title = str(result.get("title") or "").strip()
        recorded += f"- {title or url} :: {url}\n"
    tool_context.state[key] = recorded


def _spend_budget(tool_context: ToolContext | None) -> bool:
    """Returns True if a search may proceed; counts the spend."""
    global _fallback_count
    budget = config.max_searches_per_build()
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
        return [
            {
                "error": (
                    f"Search budget of {config.max_searches_per_build()} exhausted "
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
