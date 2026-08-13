"""The two halves of a check, run apart, so a whole draft costs one budget.

`check_scene` is a SequentialAgent: extract the claims a scene makes, then
verify them. That is right for one scene and wrong for twenty-four, because it
binds one extraction to one verification and therefore to one search budget and
one slot of the writer's hourly window. Twenty-four scenes that way is
twenty-four budgets and five hours of waiting.

The two agents are used here UNCHANGED and simply not joined. Extraction runs
once per scene — schema'd, no tools, no searches, so a whole feature costs
model time and nothing else. star/sweep.py collapses what comes back to the
distinct set. Then the verifier runs ONCE over that set, with one budget, and
that single call is the only thing anybody pays for.

No new prompt, no third agent. A sweep that reasoned differently from a check
would be a second opinion about the same draft, and a writer holding two would
have to decide which department to believe.
"""

from google.adk.runners import InMemoryRunner

from star import config
from star.agents.script_check import claim_extractor, verifier

EXTRACT_APP = "star-sweep-extract"
VERIFY_APP = "star-sweep-verify"
USER = "sweep"

# The turns that start each half. Neither carries content: the scene and the
# claims travel in state so they land inside their own markers, which is the
# whole of star/agents/script_check.py's argument about a writer's text never
# arriving in instruction position.
EXTRACT_TURN = "Pull the claims this scene makes about the world."
VERIFY_TURN = "Check these claims against the room and the record."

extract_runner = InMemoryRunner(agent=claim_extractor, app_name=EXTRACT_APP)
verify_runner = InMemoryRunner(agent=verifier, app_name=VERIFY_APP)


def extract_state(scene: str) -> dict:
    """State for one scene's extraction.

    No `search_budget`, and that is not an omission. The claim desk holds no
    tools (star/agents/script_check.py), so there is nothing here to spend and
    seeding a budget would imply otherwise to the next reader.
    """
    return {"scene": scene}


def verify_state(claims: object, room_files: str = "", era: str = "") -> dict:
    """State for the one verification a sweep runs.

    `claims` is the deduped set, already gathered across every scene. The
    verifier is told nothing about scenes and should not be: its question is
    whether a claim holds, which is not a question about where in a draft it
    was said. star/sweep.py's `attach` puts the scenes back afterwards.

    `search_budget` is the sweep's own, and it is the only ceiling in the
    feature. One number for a whole draft rather than a number per scene, which
    is the difference between a writer bounding what a sweep may cost and
    hoping twenty-four independent budgets add up to something they can afford.
    """
    return {
        "claims": claims,
        "room_files": room_files,
        # Both builders feed the SAME verifier agent, so the era has to arrive
        # by both roads or a sweep judges by a standard a scene check does not.
        "era": era,
        "search_budget": config.max_searches_per_sweep(),
    }
