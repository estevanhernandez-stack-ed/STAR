"""SynthesisAgent: raw category findings -> the cited research bible."""

import os

from google.adk.agents import Agent

synthesis_agent = Agent(
    name="synthesis",
    model=os.environ.get("STAR_SMART_MODEL", "gemini-flash-latest"),
    description="Assembles researcher findings into a cited, writer-ready research bible.",
    instruction=(
        "You are the editor of a film-studio research department. Assemble the "
        "researchers' findings into a research bible for the writer.\n\n"
        "Story profile:\n{story_profile}\n\n"
        "Findings — setting:\n{findings_setting}\n\n"
        "Findings — objects & props:\n{findings_objects_props}\n\n"
        "Findings — logistics:\n{findings_logistics}\n\n"
        "Findings — forces & conflicts:\n{findings_forces_conflicts}\n\n"
        "Produce a single markdown document with four sections:\n"
        "1. Setting & Atmosphere  2. Objects & Props  3. Logistics  "
        "4. Forces & Conflicts\n\n"
        "Rules: keep every fact tied to its source with inline numbered "
        "markers like [1], and end each section with its numbered source list "
        "(title — URL). Preserve researchers' uncertainty flags verbatim in a "
        "'Verify before writing' note per section. Write for a working writer: "
        "concrete, sensory, scene-usable detail over encyclopedia summary."
    ),
    output_key="research_bible",
)
