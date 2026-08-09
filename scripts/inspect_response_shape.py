"""Print the raw ADK function-response envelope for one parallel_search call.

ADK wraps a function tool's return value before placing it on the response
part. `star.ledger.unwrap_results` handles every plausible wrapping; this
script establishes which one actually fires so it can be pinned by test.

Run from the repo root:
    .venv\\Scripts\\python.exe scripts/inspect_response_shape.py
"""

import asyncio
import json

from dotenv import load_dotenv

load_dotenv()

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from star.agents.researchers import make_researcher  # noqa: E402
from star.ledger import unwrap_results  # noqa: E402
from star.models import Category  # noqa: E402

TREATMENT = (
    "Establish what a working recording studio in Memphis looked like in 1962: "
    "the room, the gear, and the people in it."
)

# make_researcher's instruction embeds `{research_plan}` from session state (the
# real pipeline fills this via planner_agent's output_key="research_plan"). This
# script calls the researcher standalone, so it seeds the same state key here,
# shaped like a real ResearchPlan scoped to the setting category.
RESEARCH_PLAN_STATE = {
    "research_plan": {
        "questions": [
            {
                "category": "setting",
                "question": (
                    "What did a working recording studio in Memphis look like "
                    "in 1962 -- room layout, acoustic treatment, and visible gear?"
                ),
                "why": "Establishes the physical space for scenes set in the studio.",
            },
            {
                "category": "setting",
                "question": (
                    "Who worked in a Memphis recording studio in 1962 -- "
                    "engineers, session musicians, producers -- and what did "
                    "they wear and do day to day?"
                ),
                "why": "Grounds the cast of background characters and their routines.",
            },
        ]
    }
}


async def main() -> None:
    researcher = make_researcher(Category.SETTING)
    runner = InMemoryRunner(agent=researcher, app_name="shape-probe")
    session = await runner.session_service.create_session(
        app_name="shape-probe", user_id="probe", state=RESEARCH_PLAN_STATE
    )
    message = types.Content(role="user", parts=[types.Part(text=TREATMENT)])

    seen = 0
    async for event in runner.run_async(
        user_id="probe", session_id=session.id, new_message=message
    ):
        for response in event.get_function_responses() or []:
            seen += 1
            payload = getattr(response, "response", None)
            print(f"\n=== function response {seen} ===")
            print("name:          ", getattr(response, "name", None))
            print("python type:   ", type(payload).__name__)
            if isinstance(payload, dict):
                print("top-level keys:", sorted(payload))
            print("raw (truncated):")
            print(json.dumps(payload, default=str)[:1200])
            print("unwrapped count:", len(unwrap_results(payload)))
            if seen >= 2:
                return


if __name__ == "__main__":
    asyncio.run(main())
