"""The search budget is per-run and its ceiling comes from session state.

A build seeds nothing and gets `max_searches_per_build()`. A check seeds
`search_budget` (star/agents/script_check.py's `check_state`) and gets
`max_searches_per_check()`. The module-level counter stays as it was, for
direct script calls that have no ADK session at all.

No network here: every assertion below is against the refusal path, which
returns before `parallel_search` ever builds a client.
"""

import os
from unittest import mock

from star import config
from star.tools.parallel_search import (
    _budget,
    _spend_budget,
    parallel_search,
    reset_search_budget,
)


class _FakeToolContext:
    """Stands in for ADK's ToolContext: a state dict is all this code reads."""

    def __init__(self, state=None):
        self.agent_name = "verifier"
        self.state = dict(state or {})


def test_an_unseeded_session_gets_the_build_budget():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert _budget(_FakeToolContext()) == config.max_searches_per_build()


def test_a_seeded_session_gets_what_it_seeded():
    ctx = _FakeToolContext({"search_budget": 8})

    assert _budget(ctx) == 8


def test_a_seeded_budget_actually_stops_the_spend():
    ctx = _FakeToolContext({"search_budget": 2})

    assert _spend_budget(ctx) is True
    assert _spend_budget(ctx) is True
    assert _spend_budget(ctx) is False
    assert ctx.state["search_count"] == 2


def test_the_exhaustion_message_names_this_runs_ceiling_not_the_builds():
    """A check that ran out at 8 and was told '30 exhausted' is telling its
    agent something false about what it just hit."""
    ctx = _FakeToolContext({"search_budget": 1, "search_count": 1})

    result = parallel_search("objective", ["query"], ctx)

    assert len(result) == 1
    assert "budget of 1 exhausted" in result[0]["error"]


def test_a_seeded_zero_means_zero_and_not_the_build_default():
    """`STAR_MAX_SEARCHES_PER_CHECK=0` is what a reader sets to stop a check
    spending money. Under the truthiness read this started with, that variable
    did the opposite of what it says and handed the run 30 searches. Absent and
    zero are different answers; only absent falls back."""
    with mock.patch.dict(os.environ, {}, clear=True):
        ctx = _FakeToolContext({"search_budget": 0})

        assert _budget(ctx) == 0


def test_a_zero_ceiling_refuses_the_first_search_rather_than_locking_up():
    """Zero is a real ceiling, not a lockout. The tool refuses and says why, so
    the verifier finishes from the room's files with `budget:` notes instead of
    reporting claims as looked-for-and-not-found."""
    ctx = _FakeToolContext({"search_budget": 0})

    result = parallel_search("objective", ["query"], ctx)

    assert len(result) == 1
    assert "budget of 0 exhausted" in result[0]["error"]
    assert ctx.state.get("search_count", 0) == 0


def test_two_sessions_do_not_share_a_ceiling():
    build = _FakeToolContext()
    check = _FakeToolContext({"search_budget": 8})

    with mock.patch.dict(os.environ, {}, clear=True):
        assert _budget(build) == config.max_searches_per_build()
        assert _budget(check) == 8


# -- the fallback path, for direct script calls with no ADK session --


def test_a_direct_call_still_uses_the_module_level_counter():
    reset_search_budget()
    with mock.patch.dict(os.environ, {"STAR_MAX_SEARCHES_PER_BUILD": "2"}):
        assert _spend_budget(None) is True
        assert _spend_budget(None) is True
        assert _spend_budget(None) is False

        reset_search_budget()
        assert _spend_budget(None) is True
    reset_search_budget()


def test_the_fallback_ceiling_is_the_build_budget_and_ignores_session_state():
    """Nothing seeds state without a context, so this path has no session to
    read — it must keep answering with the build default."""
    reset_search_budget()
    with mock.patch.dict(os.environ, {}, clear=True):
        assert _budget(None) == config.max_searches_per_build()
