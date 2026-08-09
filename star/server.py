"""STAR web service.

FastAPI app that runs Pipeline A ("Build the Room") via the ADK Runner and
streams live progress to the browser over SSE.

Run from the repo root:
    uvicorn star.server:app --reload
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from fastapi.responses import Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from star import config  # noqa: E402

config.validate_env()

from star.agents.pipelines import build_room  # noqa: E402
from star.auth import verify_token  # noqa: E402
from star.findings import parse_findings  # noqa: E402
from star.guards import DailyCap, RateLimiter  # noqa: E402
from star.ledger import SourceLedger  # noqa: E402
from star.models import Category  # noqa: E402
from star.store import RoomStore, document_to_room, room_to_document  # noqa: E402

logger = logging.getLogger(__name__)

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

_CATEGORY_BY_AUTHOR = {f"researcher_{c.value}": c for c in Category}

# Single source of truth for "this run will never produce another event."
# stream_events polls until run["status"] lands in this tuple; every place
# that assigns a terminal status must have its value listed here, or the SSE
# generator spins forever with nothing left to send.
_TERMINAL_RUN_STATUSES = ("complete", "partial", "error")

_store = RoomStore()

# Abuse guards. In-memory is correct, not a compromise — see star/guards.py's
# module docstring for why, and what breaks if this ever runs on more than
# one instance.
_ip_limiter = RateLimiter(
    max_per_window=config.max_rooms_per_ip_per_hour(), window_seconds=3600
)
_daily_cap = DailyCap(max_per_day=config.max_rooms_per_day())


def _require_uid(authorization: str | None) -> str:
    """Every /api route is scoped to a caller. No token, no data."""
    uid = verify_token(authorization)
    if uid is None:
        raise HTTPException(401, "Sign-in required.")
    return uid


def _caller_key(request: Request) -> str:
    """Identify the caller for rate limiting.

    Cloud Run sits behind a load balancer, so `request.client.host` is the
    load balancer's address, not the caller's. `X-Forwarded-For` is a
    left-to-right chain: each proxy the request passes through appends its
    own address to the end, so the *first* entry is the one the load
    balancer itself put there — the original client — and every entry after
    it is a proxy, not a caller. Take the first entry when the header is
    present; fall back to `request.client.host` for direct/local traffic
    that never passed through a proxy.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _build_categories(state: dict, ledger: SourceLedger) -> dict:
    """Parse every category's researcher prose against the run's ledger."""
    return {
        c.value: parse_findings(state.get(f"findings_{c.value}"), c, ledger)
        for c in Category
    }


class RoomRequest(BaseModel):
    treatment: str


def _push(run: dict, event_type: str, **data) -> None:
    run["events"].append({"type": event_type, **data})


def _maybe_warn_empty_ledger(run: dict) -> None:
    """Surface the fifth-envelope failure `unwrap_results` can't rule out.

    `SourceLedger.record` skips anything without a URL, so an ADK upgrade
    that quietly changes the function-response envelope makes every response
    unwrap to `[]` — searches ran, nothing landed, every citation this run
    produces reads as unverified, and nothing raises. This is the one signal
    the ledger being pure can't self-report; push it as a visible event
    instead of letting the run look clean.
    """
    if run["search_count"] > 0 and len(run["ledger"]) == 0:
        _push(
            run,
            "warning",
            message=(
                "Searches ran but the source ledger came back empty — the ADK "
                "response envelope may have changed shape. Every citation in "
                "this run will show as unverified."
            ),
        )


def _persist(run: dict, run_id: str, status: str) -> None:
    """Best-effort persistence. Must never affect the in-memory run state:
    the outcome was already decided by the caller before this runs, and a
    Firestore hiccup here should cost only durability, never correctness.
    """
    try:
        _store.save(
            run["uid"],
            run_id,
            room_to_document(
                run_id,
                run.get("result"),
                status,
                datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            ),
        )
    except Exception:
        logger.exception("Failed to persist %s run %s", status, run_id)


async def _salvage(run: dict, run_id: str) -> bool:
    """Recover whatever research survived a run that did not finish.

    A build costs four researchers, a dozen or more live web searches, and
    several minutes. Discarding all of that because the editor was still
    writing is the wrong trade: the findings and their citations are already
    parsed and paid for, and they are most of the value. Only the bible needs
    synthesis — and even that may already exist if synthesis wrote its
    output_key before the ceiling tripped, in which case this keeps it rather
    than discarding a real bible.

    Contract: never raises. Every caller (`_execute`'s `except TimeoutError`
    and `except Exception` blocks) invokes this unguarded, and an exception
    escaping from inside one except branch cannot be caught by a sibling
    except branch — that would leave the run stuck at status "running"
    forever with no terminal SSE event. The whole body below the session_id
    guard is therefore wrapped, not just the network call. `CancelledError`
    is a `BaseException`, not an `Exception`, so it still propagates —
    shutdown cancellation must not be swallowed here.

    Returns True if anything worth showing was recovered.
    """
    session_id = run.get("session_id")
    if not session_id:
        return False
    try:
        session = await _runner.session_service.get_session(
            app_name="star", user_id="web", session_id=session_id
        )
        state = session.state if session else {}
        categories = _build_categories(state, run["ledger"])
        if not any(doc.findings for doc in categories.values()):
            return False

        run["result"] = jsonable_encoder(
            {
                "story_profile": state.get("story_profile"),
                "research_plan": state.get("research_plan"),
                "research_bible": state.get("research_bible") or "",
                "search_count": run["search_count"],
                "categories": categories,
                "source_count": len(run["ledger"]),
            }
        )
        return True
    except Exception:
        logger.exception("Failed to salvage run %s", run_id)
        return False


async def _run_pipeline(run_id: str, treatment: str) -> None:
    """Run the build and populate run["result"].

    Raises on failure and owns no outcome state — `_execute` decides status,
    persistence, and what the client is told. Kept separate so the whole build
    can be wrapped in a single wall-clock ceiling.
    """
    run = _runs[run_id]

    # Budget is per-run: it lives in the ADK session state (see
    # star/tools/parallel_search.py), and every run gets a fresh session.
    session = await _runner.session_service.create_session(
        app_name="star", user_id="web"
    )
    # Remembered so a run that overruns its ceiling can still be salvaged. The
    # researchers' findings live in this session's state the moment they file;
    # only the bible needs synthesis to finish. See _salvage.
    run["session_id"] = session.id
    message = types.Content(role="user", parts=[types.Part(text=treatment)])
    _push(run, "started")

    async for event in _runner.run_async(
        user_id="web", session_id=session.id, new_message=message
    ):
        author = getattr(event, "author", None) or "system"
        label = _FRIENDLY.get(author, author)

        category = _CATEGORY_BY_AUTHOR.get(author)

        for call in event.get_function_calls() or []:
            objective = (call.args or {}).get("objective", "")
            run["search_count"] += 1
            _push(
                run,
                "search",
                agent=label,
                objective=objective,
                category=category.value if category else None,
            )

        for response in event.get_function_responses() or []:
            # Key by the raw author, not the friendly label, so found_by
            # joins cleanly against _CATEGORY_BY_AUTHOR (which is also
            # keyed by raw author). The friendly label stays user-facing,
            # in the SSE "search" event above.
            run["ledger"].record(author, getattr(response, "response", None))

        content = getattr(event, "content", None)
        if content and getattr(content, "parts", None):
            text = "".join(
                p.text or "" for p in content.parts if getattr(p, "text", None)
            )
            is_final = getattr(event, "is_final_response", lambda: True)()
            if text.strip() and is_final:
                _push(run, "agent_done", agent=label)

    _maybe_warn_empty_ledger(run)

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
            "categories": _build_categories(state, run["ledger"]),
            "source_count": len(run["ledger"]),
        }
    )


def _partial_message(cause: str) -> str:
    """Shared by both salvage sites so the promise stays consistent with what
    the browser can actually show. `_salvage`'s payload does carry
    `categories`, but web/app.js's showResults only ever renders
    story_profile, research_plan, and research_bible — there is no tab for
    categories yet. Claiming the findings are "here" overclaims what the
    user can see right now; say what is true instead.
    """
    return (
        f"{cause} There is no research bible to read yet, but every "
        "researcher's findings and sources were gathered and are safely "
        "saved — they'll be readable here once the room view for them ships."
    )


async def _execute(run_id: str, treatment: str) -> None:
    """Own the run's outcome: bound it, decide its status, tell the client.

    The timeout is not optional. On 2026-08-09 a build sat for nine minutes
    with the UI spinning and no error, because synthesis was generating toward
    the model's output ceiling and nothing bounded it. A cap on that one agent
    fixes that one cause; this bounds every cause, including the next one.
    """
    run = _runs[run_id]
    timeout = config.run_timeout_seconds()
    try:
        await asyncio.wait_for(_run_pipeline(run_id, treatment), timeout=timeout)
        run["status"] = "complete"
        _persist(run, run_id, "complete")
        _push(run, "complete", search_count=run["search_count"])
    except TimeoutError:
        logger.warning("Run %s exceeded its %ss ceiling", run_id, timeout)
        salvaged = await _salvage(run, run_id)
        if salvaged:
            run["status"] = "partial"
            _persist(run, run_id, "partial")
            _push(
                run,
                "partial",
                search_count=run["search_count"],
                message=_partial_message(
                    "The editor ran past the time limit before it could finish "
                    "writing the bible."
                ),
            )
        else:
            run["status"] = "error"
            _persist(run, run_id, "error")
            _push(
                run,
                "error",
                message=(
                    f"The department ran past its {timeout // 60}-minute limit and "
                    "was stopped before anything could be filed. Try again — a "
                    "shorter treatment usually finishes faster."
                ),
            )
    except Exception as exc:  # surface real errors to the UI during dev
        # A Gemini 5xx (or any other mid-pipeline failure) during synthesis
        # used to discard the same filed research the timeout path goes out
        # of its way to preserve. Salvage here too before falling back to a
        # bare error.
        #
        # The client only ever sees a generic message below — this endpoint
        # is public now, and `f"{type(exc).__name__}: {exc}"` used to hand a
        # stranger our stack vocabulary (library names, table names, even a
        # stray credential in an error string). The real detail still needs
        # to exist somewhere, so it goes to the server log instead.
        logger.exception("Run %s failed", run_id)
        salvaged = await _salvage(run, run_id)
        if salvaged:
            run["status"] = "partial"
            _persist(run, run_id, "partial")
            _push(
                run,
                "partial",
                search_count=run["search_count"],
                # No exception class name here either. It is a thinner leak
                # than a full message, but it is still our vocabulary in a
                # stranger's browser, and it reads worse to a human than
                # plain language does. The type is in the log line above.
                message=_partial_message(
                    "The editor hit a problem before it could finish writing "
                    "the bible."
                ),
            )
        else:
            run["status"] = "error"
            _persist(run, run_id, "error")
            _push(
                run,
                "error",
                message=(
                    "The department hit an unexpected problem and stopped. "
                    "The details are in the server log."
                ),
            )


@app.post("/api/rooms")
async def create_room(
    req: RoomRequest, request: Request, authorization: str | None = Header(None)
) -> dict:
    uid = _require_uid(authorization)
    treatment = req.treatment.strip()
    if len(treatment) < 40:
        raise HTTPException(400, "Give the research department a bit more to work with.")
    if len(treatment) > config.max_treatment_chars():
        raise HTTPException(
            400,
            f"Treatments are capped at {config.max_treatment_chars()} characters — "
            "send the department a treatment, not the novel.",
        )
    # One room build spends real money — a dozen or more live web searches
    # plus several Gemini calls. Refuse before any of that runs, not after.
    if not _daily_cap.check():
        raise HTTPException(
            429, "STAR has hit its daily research limit. Try again tomorrow."
        )
    if not _ip_limiter.check(_caller_key(request)):
        raise HTTPException(
            429,
            "That is a lot of rooms in one hour. Give the department a moment "
            "and try again shortly.",
        )
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {
        "events": [],
        "status": "running",
        "result": None,
        "search_count": 0,
        "ledger": SourceLedger(),
        "uid": uid,
    }
    # Best-effort, written before the task starts: if this Cloud Run instance
    # recycles mid-build, the run vanishes from memory but this document
    # survives, and get_room's "stored running but absent from memory" branch
    # can recover it as "interrupted" instead of 404ing a room out of
    # existence. Same durability-only contract as _persist elsewhere — a
    # Firestore hiccup here must never stop a build from starting.
    #
    # Off the event loop deliberately. The Firestore client is blocking, and
    # this is the only persistence call sitting in front of a response rather
    # than inside a background task — left inline, a *slow* Firestore (not a
    # failing one, which the try/except already covers) would stall the whole
    # single-threaded loop and delay every other request and SSE stream on the
    # instance before this caller even learns its run_id.
    await asyncio.to_thread(_persist, _runs[run_id], run_id, "running")
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
            if run["status"] in _TERMINAL_RUN_STATUSES:
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/rooms")
async def list_rooms(authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)
    return {"rooms": _store.list_rooms(uid)}


@app.get("/api/rooms/{run_id}")
async def get_room(run_id: str, authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)

    run = _runs.get(run_id)
    if run is not None and run.get("uid") == uid:
        return {"status": run["status"], "result": run["result"]}

    document = _store.get(uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    # Stored as running but absent from memory: the in-flight asyncio task did
    # not survive a restart, and nothing will ever finish it. Say so once
    # rather than letting the UI spin forever.
    if document.get("status") == "running":
        _store.mark_interrupted(uid, run_id)
        document["status"] = "interrupted"

    return {"status": document.get("status", "complete"), "result": document_to_room(document)}


@app.get("/config.js")
async def browser_config() -> Response:
    """The Firebase web key is a public project identifier, not a secret."""
    payload = {
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    }
    return Response(
        f"export const FIREBASE = {json.dumps(payload)};",
        media_type="application/javascript",
    )


_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
