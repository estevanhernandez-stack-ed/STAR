"""IntakeAgent: treatment text -> StoryProfile."""

import os

from google.adk.agents import Agent

from star.models import StoryProfile

intake_agent = Agent(
    name="intake",
    model=os.environ.get("STAR_FAST_MODEL", "gemini-flash-latest"),
    description="Parses a writer's treatment or logline into a structured story profile.",
    instruction=(
        "You are the intake desk of a film studio research department. The user "
        "will provide a treatment, logline, or story description. Extract a "
        "faithful StoryProfile from it. Do not invent details that are not "
        "stated or strongly implied; if the era or location is unstated, infer "
        "the most reasonable value and keep it general. key_entities should "
        "list the concrete things a researcher must ground in fact: professions, "
        "organizations, technologies, vehicles, activities, subcultures."
    ),
    output_schema=StoryProfile,
    output_key="story_profile",
)
