"""PlannerAgent: StoryProfile -> ResearchPlan (the fan-out work order)."""

import os

from google.adk.agents import Agent

from star.models import ResearchPlan

planner_agent = Agent(
    name="planner",
    model=os.environ.get("STAR_SMART_MODEL", "gemini-flash-latest"),
    description="Turns a story profile into a concrete research plan across four categories.",
    instruction=(
        "You are the head of research at a film studio. Given this story profile:\n\n"
        "{story_profile}\n\n"
        "Produce a ResearchPlan of 8-20 specific, answerable, factual questions a "
        "researcher could resolve with web sources, spread across all four "
        "categories:\n"
        "- setting: period/place atmosphere — light, sound, smell, culture, dress, "
        "money, daily texture\n"
        "- objects_props: the things characters hold, use, wear — makes, models, "
        "era-correct details\n"
        "- logistics: how people and things move — routes, distances, travel times, "
        "schedules, procedures\n"
        "- forces_conflicts: what opposes the characters — institutions, rivals, "
        "laws, dangers, and how they actually operated\n\n"
        "Every question must name the era and place explicitly (a researcher sees "
        "one question at a time, with no other context). Prioritize questions "
        "whose answers a writer would touch in more than one scene."
    ),
    output_schema=ResearchPlan,
    output_key="research_plan",
)
