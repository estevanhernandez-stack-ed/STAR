"""STAR web service.

FastAPI app that runs Pipeline A ("Build the Room") via the ADK Runner and
streams live progress to the browser over SSE.

Run from the repo root:
    uvicorn star.server:app --reload
"""

import asyncio
import json
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from star import config  # noqa: E402

config.validate_env()

from star.agents.pipelines import build_room  # noqa: E402

app = FastAPI(title="STAR — Story & Treatment Agentic Research")

_runner = InMemoryRunner(agent=build_room, app_name="star")
_runs: dict[str, dict] = {}

_FRIENDLY = {
    "intake": "Intake desk",
    "planner": "Head of research",
    "researcher_setting": "Setting researcher",
    "researcher_objects_props": "Props researcher",
    "researcher_logistics": "Logistics researcher",
    "researcher_forces_conflicts": "Forces & conflicts researcher",
    "synthesis": "Editor",
}


class RoomRequest(BaseModel):
    treatment: str


def _push(run: dict, event_type: str, **data) -> None:
    run["events"].append({"type": event_type, **data})


async def _execute(run_id: str, treatment: str) -> None:
    run = _runs[run_id]
    try:
        # Budget is per-run: it lives in the ADK session state (see
        # star/tools/parallel_search.py), and every run gets a fresh session.
        session = await _runner.session_service.create_session(
            app_name="star", user_id="web"
        )
        message = types.Content(role="user", parts=[types.Part(text=treatment)])
        _push(run, "started")

        async for event in _runner.run_async(
            user_id="web", session_id=session.id, new_message=message
        ):
            author = getattr(event, "author", None) or "system"
            label = _FRIENDLY.get(author, author)

            for call in event.get_function_calls() or []:
                objective = (call.args or {}).get("objective", "")
                run["search_count"] += 1
                _push(run, "search", agent=label, objective=objective)

            content = getattr(event, "content", None)
            if content and getattr(content, "parts", None):
                text = "".join(
                    p.text or "" for p in content.parts if getattr(p, "text", None)
                )
                is_final = getattr(event, "is_final_response", lambda: True)()
                if text.strip() and is_final:
                    _push(run, "agent_done", agent=label)

        final = await _runner.session_service.get_session(
            app_name="star", user_id="web", session_id=session.id
        )
        state = final.state if final else {}
        run["result"] = jsonable_encoder(
            {
                "story_profile": state.get("story_profile"),
                "research_plan": state.get("research_plan"),
                "research_bible": state.get("research_bible"),
                "search_count": run["search_count"],
            }
        )
        run["status"] = "complete"
        _push(run, "complete", search_count=run["search_count"])
    except Exception as exc:  # surface real errors to the UI during dev
        run["status"] = "error"
        _push(run, "error", message=f"{type(exc).__name__}: {exc}")


@app.post("/api/rooms")
async def create_room(req: RoomRequest) -> dict:
    treatment = req.treatment.strip()
    if len(treatment) < 40:
        raise HTTPException(400, "Give the research department a bit more to work with.")
    if len(treatment) > config.max_treatment_chars():
        raise HTTPException(
            400,
            f"Treatments are capped at {config.max_treatment_chars()} characters — "
            "send the department a treatment, not the novel.",
        )
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {
        "events": [],
        "status": "running",
        "result": None,
        "search_count": 0,
    }
    # Hold a strong reference so the event loop can't garbage-collect the
    # in-flight pipeline (asyncio keeps only weak refs to bare tasks).
    _runs[run_id]["task"] = asyncio.create_task(_execute(run_id, treatment))
    return {"run_id": run_id}


@app.get("/api/rooms/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    if run_id not in _runs:
        raise HTTPException(404, "Unknown run")

    async def generate():
        cursor = 0
        while True:
            run = _runs.get(run_id)
            if run is None:
                break
            while cursor < len(run["events"]):
                yield f"data: {json.dumps(run['events'][cursor], default=str)}\n\n"
                cursor += 1
            if run["status"] in ("complete", "error"):
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/rooms/{run_id}")
async def get_room(run_id: str) -> dict:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run")
    return {"status": run["status"], "result": run["result"]}


_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
