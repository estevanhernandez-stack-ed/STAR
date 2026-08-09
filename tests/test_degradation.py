"""A dead researcher must not kill the room build (adversarial review M4).

The four researchers run under ParallelAgent, so they are independent by
design. But ADK's instruction templating raises KeyError on a missing state
key, and a researcher that dies never writes its `output_key`. Without the
optional marker on every `{findings_*}` reference, one dead branch aborts
synthesis and discards the other three researchers' work.

These tests exercise ADK's real templating, not a reimplementation of it.
"""

import pytest
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils.instructions_utils import inject_session_state

from star.agents.synthesis import synthesis_agent
from star.models import Category

ALL_FINDINGS = {f"findings_{c.value}": f"- a {c.value} fact :: https://a.example/x" for c in Category}
STORY_PROFILE = {"story_profile": {"title": "1962 Memphis"}}


class _FakeInvocationContext:
    """Minimal stand-in exposing only what inject_session_state reads."""

    def __init__(self, state):
        self.session = type("_S", (), {"state": state})()
        self.artifact_service = None


def _ctx(state):
    return ReadonlyContext(_FakeInvocationContext(state))


async def _render(state):
    return await inject_session_state(synthesis_agent.instruction, _ctx(state))


@pytest.mark.asyncio
async def test_synthesis_renders_when_every_researcher_filed():
    rendered = await _render({**STORY_PROFILE, **ALL_FINDINGS})

    assert "a setting fact" in rendered
    assert "a forces_conflicts fact" in rendered


@pytest.mark.asyncio
async def test_synthesis_survives_one_dead_researcher():
    """The M4 case: setting died, so its output_key was never written."""
    survivors = {k: v for k, v in ALL_FINDINGS.items() if k != "findings_setting"}

    rendered = await _render({**STORY_PROFILE, **survivors})

    # The dead branch renders empty rather than raising.
    assert "<findings_setting>\n\n</findings_setting>" in rendered
    # The survivors' work is still there — that is the whole point.
    assert "a objects_props fact" in rendered
    assert "a logistics fact" in rendered
    assert "a forces_conflicts fact" in rendered


@pytest.mark.asyncio
async def test_synthesis_survives_all_four_researchers_dying():
    rendered = await _render(STORY_PROFILE)

    assert "1962 Memphis" in rendered
    for category in Category:
        assert f"<findings_{category.value}>\n\n</findings_{category.value}>" in rendered


@pytest.mark.asyncio
async def test_a_researcher_that_filed_nothing_is_not_the_same_as_one_that_died():
    """An empty string is a real filing; a missing key is a death. Both render."""
    rendered = await _render({**STORY_PROFILE, **ALL_FINDINGS, "findings_setting": ""})

    assert "<findings_setting>\n\n</findings_setting>" in rendered
    assert "a logistics fact" in rendered
