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

app = FastAPI(
    title="STAR — Story & Treatment Agentic Research",
    # Public, unauthenticated endpoint. The schema exposes no secrets, but it
    # hands an attacker a map of every route and shape for free.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

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
    max_per_window=config.max_rooms_per_ip_per_hour(),
    window_seconds=3600,
    max_keys=config.max_rate_limiter_keys(),
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
    left-to-right chain, and proxies APPEND to it — they do not replace it.
    The *leftmost* entry is whatever the incoming request already had in
    that header, which for a direct client is nothing but for an attacker is
    anything they feel like typing: it is not even validated as an IP.
    Demonstrated 2026-08-09: 50 requests with a rotating leftmost value were
    all allowed past a 5/hour limit, and `X-Forwarded-For: totally-not-an-ip`
    was accepted verbatim as the rate-limit key. The old docstring here
    asserted the leftmost entry was correct and cited no verification — that
    claim is how this got shipped.

    The *rightmost* entry is the one GCP's load balancer itself appended as
    the request's last hop, which is correct whether or not Cloud Run
    preserves or replaces whatever the client sent — no experiment needed to
    justify it, because it holds either way. Take the last entry when the
    header is present; fall back to `request.client.host` for direct/local
    traffic that never passed through a proxy.

    Neither key is a strong identity, and this function does not pretend
    otherwise. Anonymous Firebase sign-in is open to anyone, and the browser
    Firebase API key is public by design (see docs/INFRASTRUCTURE.md) — a
    determined attacker can rotate `uid`s as freely as they can rotate
    source addresses, and nothing here stops that. This limiter's job is to
    make casual and semi-automated abuse expensive, not to authenticate the
    caller. The real ceiling against a determined, identity-rotating
    attacker is `_daily_cap` (see Finding 1 in star/guards.py and
    scripts/deploy.sh) — that is why min-instances=1 keeping it alive
    matters more than this key ever could.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _resume_cursor(last_event_id: str | None, total_events: int) -> int:
    """Compute the SSE resume point from an incoming Last-Event-ID header.

    EventSource sets this automatically on every reconnect, to the `id:`
    line of the last event it actually received — but it is still a
    client-controlled header, and `int()` alone is too permissive to trust
    with it. `int("1_000")` succeeds (Python accepts underscore-grouped
    digits), and `int()` also accepts non-ASCII Unicode digits — `_push`
    never emits either shape, so both are signs of a header this endpoint
    did not produce. `int()` places no upper bound on the result either: a
    large value used to push `cursor` past every event that exists yet, and
    since the replay loop below only fires once `cursor < len(events)`, that
    silently starved the client of every event until the run ended, with no
    error and no visible symptom besides a stuck-looking progress view.

    `str.isdigit()` accepts only what `_push` actually emits: an
    ASCII-rendered non-negative int. Clamping to `total_events` means a
    cursor claiming to be past events that do not exist yet resumes at the
    current tip instead of going dark.
    """
    if last_event_id is None or not last_event_id.isdigit():
        return 0
    return min(int(last_event_id) + 1, total_events)


def _build_categories(state: dict, ledger: SourceLedger) -> dict:
    """Parse every category's researcher prose against the run's ledger."""
    return {
        c.value: parse_findings(state.get(f"findings_{c.value}"), c, ledger)
        for c in Category
    }


class RoomRequest(BaseModel):
    treatment: str


def _push(run: dict, event_type: str, **data) -> None:
    # The id is the event's position in `run["events"]`, which is append-only
    # for the life of a run — so it doubles as the SSE `id:` line stream_events
    # emits, letting a reconnecting EventSource resume from Last-Event-ID
    # instead of replaying the whole history.
    event_id = len(run["events"])
    run["events"].append({"id": event_id, "type": event_type, **data})


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
            args = call.args or {}
            objective = args.get("objective", "")
            # The literal query strings this call sent to Parallel Search.
            # star/tools/parallel_search.py's contract is one objective plus
            # 2-4 supporting queries, so these are the most concrete evidence
            # the run can offer while it is still running: not "searching…"
            # but the exact words that went over the wire. The model fills
            # `search_queries`, so its type is not guaranteed — anything that
            # is not a list of strings is dropped rather than trusted.
            raw_queries = args.get("search_queries")
            queries = (
                [q for q in raw_queries if isinstance(q, str) and q.strip()]
                if isinstance(raw_queries, list)
                else []
            )
            run["search_count"] += 1
            _push(
                run,
                "search",
                agent=label,
                objective=objective,
                queries=queries,
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
                # Carries `category` for the same reason "search" does: the
                # browser routes this to one of four drawers, and without it
                # the client has to reverse-map the friendly English label
                # back to a category. That made _FRIENDLY's wording a load-
                # bearing API contract — rewording "Props researcher" would
                # silently stop that drawer ever filing, with nothing to
                # catch it. `agent` stays for display; `category` is what
                # the UI routes on.
                _push(
                    run,
                    "agent_done",
                    agent=label,
                    category=category.value if category else None,
                )

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


def _evict_old_runs(exclude: str | None = None) -> None:
    """Cap `_runs` at config.max_runs_in_memory() once it grows past that.

    Each entry carries a SourceLedger holding every excerpt from up to 30
    searches, plus a task reference — nothing else ever shrinks `_runs`, so
    left alone it grows for the life of the instance. Persistence makes
    dropping a finished run from memory safe: get_room's Firestore fallback
    can still read it back.

    A `running` entry is never a candidate, no matter how old: evicting one
    would orphan its in-flight asyncio task and break its SSE stream, which
    reads the run out of this same dict. `_runs` preserves insertion order
    (plain dict, Python 3.7+), so walking it front-to-back visits oldest
    first; only terminal entries are removed, oldest first, until the count
    is back at the bound or no terminal entries remain.

    `exclude` protects one more case: `_execute` pushes a run's own terminal
    event and calls this in the same synchronous stretch, with no `await` in
    between, so that run can be the *oldest* terminal entry in `_runs` at the
    exact moment it finishes — a slow build often is. Evicting it here, before
    its own SSE stream's next poll has had a chance to observe it, would drop
    the terminal event the client is waiting on. `_execute` passes its own
    run_id so this pass can never take that run, no matter how old.
    """
    excess = len(_runs) - config.max_runs_in_memory()
    if excess <= 0:
        return
    for run_id in list(_runs):
        if excess <= 0:
            break
        if run_id == exclude:
            continue
        if _runs[run_id]["status"] not in _TERMINAL_RUN_STATUSES:
            continue
        del _runs[run_id]
        excess -= 1


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
    except Exception:  # nothing about this reaches the client; see below
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

    # Every branch above lands on a terminal status; this is the one place
    # in the run's lifecycle where eviction can never orphan a live build.
    # Excluding this run's own id keeps this exact call from evicting the
    # run whose terminal event it just pushed — see _evict_old_runs.
    _evict_old_runs(exclude=run_id)


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
    #
    # Order matters (Finding 3): the per-IP check must run first, and
    # DailyCap.check() must be the last thing before this request is
    # actually allowed to run. DailyCap.check() increments on the allow
    # path — it is a spend, not a peek — so checking it before the per-IP
    # limiter meant every request the IP limiter went on to refuse had
    # already spent a daily slot. Verified: 10 POSTs from one IP against a
    # per-IP limit of 1 produced one build and consumed all 10 daily slots;
    # at production settings (5/hour, 100/day) that is the whole day's
    # budget gone in about two seconds, from one caller, before a single
    # legitimate user is served. Checking the free, in-memory per-IP limiter
    # first means only a request that is actually going to run ever touches
    # the shared daily budget.
    if not _ip_limiter.check(_caller_key(request)):
        raise HTTPException(
            429,
            "That is a lot of rooms in one hour. Give the department a moment "
            "and try again shortly.",
        )
    if not _daily_cap.check():
        raise HTTPException(
            429, "STAR has hit its daily research limit. Try again tomorrow."
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
async def stream_events(
    run_id: str, last_event_id: str | None = Header(None, alias="Last-Event-ID")
) -> StreamingResponse:
    if run_id not in _runs:
        raise HTTPException(404, "Unknown run")

    async def generate():
        # Event ids are 0-based and match their index in run["events"] (see
        # _push), so the next unseen event is simply one past the last one
        # seen. See _resume_cursor for why this is not just `int(header)`.
        initial = _runs.get(run_id)
        cursor = _resume_cursor(
            last_event_id, len(initial["events"]) if initial else 0
        )
        while True:
            run = _runs.get(run_id)
            if run is None:
                break
            while cursor < len(run["events"]):
                event = run["events"][cursor]
                yield f"id: {event['id']}\ndata: {json.dumps(event, default=str)}\n\n"
                cursor += 1
            if run["status"] in _TERMINAL_RUN_STATUSES:
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/rooms")
async def list_rooms(authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)
    # Off the event loop: the Firestore client is blocking, and this handler
    # runs on the same single-threaded loop as every other request and every
    # open SSE stream on the instance. Left inline, a slow list call stalls
    # all of them, not just this caller.
    rooms = await asyncio.to_thread(_store.list_rooms, uid)
    return {"rooms": rooms}


@app.get("/api/rooms/{run_id}")
async def get_room(run_id: str, authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)

    run = _runs.get(run_id)
    if run is not None and run.get("uid") == uid:
        return {"status": run["status"], "result": run["result"]}

    # Off the event loop; see list_rooms above for why.
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    # Stored as running but absent from memory: the in-flight asyncio task did
    # not survive a restart, and nothing will ever finish it. Say so once
    # rather than letting the UI spin forever.
    if document.get("status") == "running":
        # False means the document was deleted between the _store.get() call
        # above and this update — a race Task 1's creation-time write made
        # reachable. Report the room as gone rather than a status this
        # request never actually managed to set.
        if not await asyncio.to_thread(_store.mark_interrupted, uid, run_id):
            raise HTTPException(404, "Unknown run")
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
