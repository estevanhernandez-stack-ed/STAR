"""Researchers publish real source titles into session state for synthesis.

The server's SourceLedger is the authority for the API payload, but it lives
outside the ADK run and synthesis can only see session state. Without this,
synthesis is asked for source titles it was never given and invents them.

One state key per researcher, never a shared one: the four run concurrently
under ParallelAgent and share session state, so a single accumulating key
would carry the same lost-update race the search counter documents.
"""

import pytest
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils.instructions_utils import inject_session_state

from star.agents.synthesis import synthesis_agent
from star.tools.parallel_search import _publish_sources, _sources_key

STAX = {
    "title": "Stax Records — Wikipedia",
    "url": "https://en.wikipedia.org/wiki/Stax_Records",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}
FENDER = {
    "title": "Fender Jazzmaster",
    "url": "https://fender.example/jazzmaster",
    "excerpts": ["Introduced in 1958."],
}


class _FakeToolContext:
    def __init__(self, agent_name):
        self.agent_name = agent_name
        self.state = {}


def test_each_researcher_gets_its_own_key():
    assert _sources_key("researcher_setting") == "sources_setting"
    assert _sources_key("researcher_objects_props") == "sources_objects_props"
    assert _sources_key("researcher_logistics") == "sources_logistics"
    assert _sources_key("researcher_forces_conflicts") == "sources_forces_conflicts"


def test_non_researcher_agents_publish_nothing():
    for name in ("synthesis", "planner", "intake", "", None):
        assert _sources_key(name or "") is None


def test_publish_records_title_and_url():
    ctx = _FakeToolContext("researcher_setting")

    _publish_sources(ctx, [STAX])

    assert ctx.state["sources_setting"] == (
        "- Stax Records — Wikipedia :: https://en.wikipedia.org/wiki/Stax_Records\n"
    )


def test_publish_accumulates_across_calls_without_duplicating():
    ctx = _FakeToolContext("researcher_setting")

    _publish_sources(ctx, [STAX])
    _publish_sources(ctx, [STAX, FENDER])

    recorded = ctx.state["sources_setting"]
    assert recorded.count("https://en.wikipedia.org/wiki/Stax_Records") == 1
    assert "Fender Jazzmaster" in recorded


def test_two_researchers_never_write_the_same_key():
    setting = _FakeToolContext("researcher_setting")
    props = _FakeToolContext("researcher_objects_props")

    _publish_sources(setting, [STAX])
    _publish_sources(props, [FENDER])

    assert set(setting.state) == {"sources_setting"}
    assert set(props.state) == {"sources_objects_props"}


def test_a_source_without_a_title_falls_back_to_its_url():
    ctx = _FakeToolContext("researcher_logistics")

    _publish_sources(ctx, [{"url": "https://a.example/x", "title": "", "excerpts": []}])

    assert ctx.state["sources_logistics"] == "- https://a.example/x :: https://a.example/x\n"


def test_publish_skips_the_budget_error_dict():
    ctx = _FakeToolContext("researcher_setting")

    _publish_sources(ctx, [{"error": "Search budget exhausted"}])

    assert ctx.state["sources_setting"] == ""


def test_publish_is_a_no_op_without_a_tool_context():
    """Direct script calls pass no context; publishing must not explode."""
    _publish_sources(None, [STAX])


# --- end of chain: published sources must reach the synthesis prompt ---


class _FakeInvocationContext:
    def __init__(self, state):
        self.session = type("_S", (), {"state": state})()
        self.artifact_service = None


async def _render(state):
    return await inject_session_state(
        synthesis_agent.instruction, ReadonlyContext(_FakeInvocationContext(state))
    )


@pytest.mark.asyncio
async def test_published_sources_reach_the_synthesis_prompt():
    """Verified live 2026-08-09: a real run writes exactly these keys."""
    state = {
        "story_profile": {"title": "1962 Memphis"},
        "sources_setting": f"- {STAX['title']} :: {STAX['url']}\n",
        "sources_objects_props": f"- {FENDER['title']} :: {FENDER['url']}\n",
    }

    block = (await _render(state)).split("<sources>")[1].split("</sources>")[0]

    assert STAX["title"] in block
    assert FENDER["title"] in block
    assert STAX["url"] in block


@pytest.mark.asyncio
async def test_synthesis_renders_when_no_sources_were_published():
    """Every sources_* key is optional; an empty block must not raise."""
    block = (await _render({"story_profile": {"title": "x"}})).split("<sources>")[1]

    assert block.split("</sources>")[0].strip() == ""
