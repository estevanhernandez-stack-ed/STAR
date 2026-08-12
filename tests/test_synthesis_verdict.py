"""The editor's own account of its turn, captured while the turn is happening.

THE BUG THIS EXISTS BECAUSE OF. `max_output_tokens` on a thinking model bounds
thinking PLUS output, and thinking runs first, so a room with more research to
weigh deliberates longer and leaves less budget for the writing. The document
stops mid-word with a normal finish and nothing raised.

That was diagnosed on 2026-08-10 and "fixed" with `thinking_budget=4000` — the
Gemini 2.5 control, which `gemini-3.6-flash` ignores. The setting was present,
wrong, and invisible, and bibles kept arriving in pieces for another day and a
half while the config said the problem was solved. Replayed against a real
room's own findings on 2026-08-11, one call per row:

    thinking_budget=4000   MAX_TOKENS   15,358 thinking    638 out   1 of 4
    thinking_level=MEDIUM  MAX_TOKENS   15,356 thinking    640 out   0 of 4
    thinking_level=LOW     STOP          7,400 thinking  4,096 out   4 of 4

Two facts settle that, and both were on the ADK event all along, read by
nobody: `finish_reason` says whether the document ended or was cut off, and the
token counts say what ate the ceiling. Every diagnosis before this was
archaeology — counting headings in stored text weeks later and reasoning
backwards to a cause. These tests hold the capture, so the next room proves it
from its own run.

The seam is the ADK runner, swapped out whole, for the reason
tests/test_scenes.py gives: what a real model returns is not the thing under
test, and paying for a live build to observe an event field is not a test.
"""

from __future__ import annotations

import asyncio
from unittest import mock

from google.genai.types import ThinkingLevel

from star import config
from star.agents.synthesis import synthesis_agent


class _FakeEvent:
    """One ADK event, carrying only what the capture reads."""

    def __init__(self, author, finish_reason=None, usage=None):
        self.author = author
        self.finish_reason = finish_reason
        self.usage_metadata = usage
        self.content = None

    def get_function_calls(self):
        return []

    def get_function_responses(self):
        return []

    def is_final_response(self):
        return True


class _Usage:
    def __init__(self, thinking, output):
        self.thoughts_token_count = thinking
        self.candidates_token_count = output


class _Reason:
    """`finish_reason` arrives as an enum member, not a string."""

    def __init__(self, name):
        self.name = name


class _FakeSession:
    id = "session-1"

    def __init__(self):
        self.state: dict = {}


class _FakeSessionService:
    async def create_session(self, **_kwargs):
        return _FakeSession()

    async def get_session(self, **_kwargs):
        return _FakeSession()


class _FakeRunner:
    def __init__(self, events):
        self._events = events
        self.session_service = _FakeSessionService()

    async def run_async(self, **_kwargs):
        for event in self._events:
            yield event


def _drive(events) -> dict:
    """Run the pipeline over canned events and hand back the run dict."""
    from star import server

    run = {
        "events": [],
        "status": "running",
        "search_count": 0,
        "ledger": server.SourceLedger(),
        "result": None,
        "uid": "uid-one",
        "created_at": "2026-08-11T00:00:00Z",
    }
    with (
        mock.patch.dict(server._runs, {"r": run}, clear=True),
        mock.patch("star.server._runner", _FakeRunner(events)),
    ):
        asyncio.run(server._run_pipeline("r", "a treatment"))
    return run


def test_the_editors_finish_reason_is_captured_while_it_happens():
    run = _drive([_FakeEvent("synthesis", _Reason("MAX_TOKENS"), _Usage(15358, 638))])

    assert run["bible_finish_reason"] == "MAX_TOKENS"
    assert run["bible_tokens"] == {"thinking": 15358, "output": 638}


def test_the_token_split_is_kept_because_it_is_what_names_the_cause():
    """`MAX_TOKENS` alone says the document was cut off. Only the split says
    WHY — 15,358 thinking against 638 written is the whole diagnosis, and
    without it the next person reasons backwards from headings again."""
    run = _drive([_FakeEvent("synthesis", _Reason("STOP"), _Usage(7400, 4096))])

    assert run["bible_tokens"]["thinking"] == 7400
    assert run["bible_tokens"]["output"] == 4096


def test_another_agents_verdict_is_not_the_bible_s():
    """Four researchers and a planner run in the same loop and finish their own
    turns. Recording any of them here would attribute a researcher's ceiling to
    the editor's document."""
    run = _drive(
        [
            _FakeEvent("researcher_setting", _Reason("MAX_TOKENS"), _Usage(9, 9)),
            _FakeEvent("planner", _Reason("MAX_TOKENS"), _Usage(9, 9)),
        ]
    )

    assert run.get("bible_finish_reason") is None
    assert run.get("bible_tokens") is None


def test_the_verdict_reaches_the_result_the_room_is_built_from():
    run = _drive([_FakeEvent("synthesis", _Reason("MAX_TOKENS"), _Usage(15358, 638))])

    assert run["result"]["bible_finish_reason"] == "MAX_TOKENS"
    assert run["result"]["bible_tokens"] == {"thinking": 15358, "output": 638}


def test_a_run_with_no_verdict_records_none_rather_than_a_guess():
    """An older model, or an event that carries no usage at all. Absence has to
    stay absent: `truncated` reads off this field, and a default would mark
    rooms on a fact nobody measured."""
    run = _drive([_FakeEvent("synthesis")])

    assert run["result"]["bible_finish_reason"] is None
    assert run["result"]["bible_tokens"] is None


# --- the control itself ------------------------------------------------------


def test_the_editor_is_configured_with_the_control_this_model_honours():
    """The defect in one assertion. `thinking_budget` is accepted, ignored, and
    invisible on this model; sending it and believing it is what cost a day and
    a half. This does not pin WHICH level — that is a judgement call in
    config.py — only that the knob being turned is one the model reads."""
    thinking = synthesis_agent.generate_content_config.thinking_config

    assert thinking.thinking_level is not None
    assert thinking.thinking_budget is None


def test_a_level_this_sdk_does_not_know_fails_at_boot():
    """The genai client takes an unrecognised level with a UserWarning and
    carries on with the model's default — the exact shape of the original bug,
    available to anyone who typos an env var. A misconfigured ceiling on the
    one call that writes the product is not a thing to warn about."""
    with mock.patch.dict("os.environ", {"STAR_SYNTHESIS_THINKING_LEVEL": "TURBO"}):
        try:
            config.synthesis_thinking_level()
        except ValueError as error:
            assert "TURBO" in str(error)
        else:
            raise AssertionError("a bogus thinking level should not be accepted")


def test_every_level_this_sdk_knows_is_accepted():
    """The other half: the check must not reject a valid level, or it becomes
    the outage it was written to prevent."""
    for member in ThinkingLevel:
        with mock.patch.dict(
            "os.environ", {"STAR_SYNTHESIS_THINKING_LEVEL": member.name}
        ):
            assert config.synthesis_thinking_level() == member.name
