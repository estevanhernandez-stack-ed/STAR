"""ADK entry point — `adk web` looks for `root_agent` here.

Run `adk web` from the repo root and select "research_dept".
"""

from dotenv import load_dotenv

load_dotenv()

from star import config  # noqa: E402

config.validate_env()

from star.agents.pipelines import build_room  # noqa: E402

root_agent = build_room
