"""STAR pipelines — deterministic multi-step ADK workflow agents.

Pipeline A ("Build the Room"): treatment -> cited research bible.
Pipeline B ("Script Check"): one scene -> a verdict per claim, with receipts.

Both are re-exported here so callers name one module for "the pipelines"
rather than reaching into the agent that happens to define each one.
"""

from google.adk.agents import SequentialAgent

from star.agents.intake import intake_agent
from star.agents.planner import planner_agent
from star.agents.researchers import research_fanout
from star.agents.script_check import check_scene
from star.agents.synthesis import synthesis_agent

__all__ = ["build_room", "check_scene"]

build_room = SequentialAgent(
    name="build_the_room",
    description=(
        "STAR Pipeline A: parse a treatment, plan research across four "
        "categories, fan out cited web research via Parallel Search, and "
        "synthesize a writer-ready research bible."
    ),
    sub_agents=[
        intake_agent,
        planner_agent,
        research_fanout,
        synthesis_agent,
    ],
)
