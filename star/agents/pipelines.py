"""STAR pipelines — deterministic multi-step ADK workflow agents.

Pipeline A ("Build the Room"): treatment -> cited research bible.
Pipeline B ("Script Check") lands in week 3 (see build plan).
"""

from google.adk.agents import SequentialAgent

from star.agents.intake import intake_agent
from star.agents.planner import planner_agent
from star.agents.researchers import research_fanout
from star.agents.synthesis import synthesis_agent

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
