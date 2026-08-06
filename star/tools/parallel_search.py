"""Parallel Search API tool — the required partner integration.

This is the runtime integration for the hackathon's Parallel track:
the official `parallel-web` SDK, imported and called here, and used by
the researcher agents on every room build and script check.
"""

import os

from parallel import Parallel

_client: Parallel | None = None
_search_count: int = 0


def _get_client() -> Parallel:
    global _client
    if _client is None:
        _client = Parallel(api_key=os.environ["PARALLEL_API_KEY"])
    return _client


def reset_search_budget() -> None:
    """Call at the start of each pipeline run."""
    global _search_count
    _search_count = 0


def parallel_search(objective: str, search_queries: list[str]) -> list[dict]:
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
        per-build search budget is exhausted.
    """
    global _search_count
    budget = int(os.environ.get("STAR_MAX_SEARCHES_PER_BUILD", "30"))
    if _search_count >= budget:
        return [{"error": f"Search budget of {budget} exhausted for this build."}]
    _search_count += 1

    search = _get_client().search(
        objective=objective,
        search_queries=search_queries,
    )
    return [
        {"title": r.title, "url": r.url, "excerpts": list(r.excerpts)}
        for r in search.results
    ]
