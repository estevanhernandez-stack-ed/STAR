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
import secrets
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

from star import tokens  # noqa: E402
from star.agents.pipelines import build_room, check_scene  # noqa: E402
from star.agents.script_check import check_state  # noqa: E402
from star.auth import linked_provider, verify_claims, verify_token  # noqa: E402
from star.findings import parse_findings  # noqa: E402
from star.guards import DailyCap, RateLimiter  # noqa: E402
from star.ledger import SourceLedger, ledger_from_room  # noqa: E402
from star.models import Category, ClaimSet, ScriptCheckResult  # noqa: E402
from star.store import (  # noqa: E402
    RoomStore,
    TokenStore,
    document_to_room,
    document_to_scene,
    room_to_document,
    scene_to_document,
)
from star.verdicts import annotate  # noqa: E402

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
# A second store rather than a second collection under the first, because MCP
# tokens live at the top level and RoomStore's every method opens with a uid.
# Both share one Firestore client — see star/store.py's _default_client.
_token_store = TokenStore()

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
    """Scope a request to its caller. No token, no data.

    Every /api route calls this EXCEPT stream_events, which cannot: an
    EventSource sends no custom headers, so there is no Authorization to
    read. That route is guarded by a per-run capability instead — see its
    docstring. This docstring used to claim the universal, and that claim
    is how the stream shipped with no check at all for most of this
    project's life: it is the first thing anyone auditing the auth posture
    reads, and it told them the answer they were looking for.
    """
    uid = verify_token(authorization)
    if uid is None:
        raise HTTPException(401, "Sign-in required.")
    return uid


def _require_claims(authorization: str | None) -> dict:
    """Scope a request to its caller AND hand back what was verified about it.

    One route needs more than a uid. `POST /api/tokens` refuses to issue a
    credential to an account whose only proof of ownership is a `localStorage`
    entry, and that question is answered by the claim set rather than by the
    uid — see star/auth.py's linked_provider.

    The 401 is duplicated from `_require_uid` rather than `_require_uid` being
    rewritten to call this, on purpose. Every other route reaches verification
    through `verify_token`, which is the name the whole test suite patches to
    stand in for Firebase; routing them through a second seam would change how
    dozens of tests reach the server for no behavioural gain. Two lines is the
    cheaper cost.
    """
    claims = verify_claims(authorization)
    if claims is None:
        raise HTTPException(401, "Sign-in required.")
    return claims


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

    `created_at` is read off the run rather than minted here, and that is a
    correctness point, not tidiness. This function writes the same document
    twice for every build — once at creation with status "running", once at
    the terminal status — and `.set()` replaces the whole document, so a
    fresh `now()` on the second write moved created_at to the moment the run
    FINISHED. The browser stamps that value on every receipt as the day the
    sources came back (web/clip.js's `RET`), and a build that starts at 23:58
    and lands at 00:03 would have stamped the wrong date on real sources.
    One timestamp, taken once, at creation.

    The fallback exists for a run dict assembled outside create_room (the
    tests do this). Stamping now is worse than stamping the creation time and
    better than raising out of a function whose whole contract is that it
    never costs anything but durability.
    """
    try:
        _store.save(
            run["uid"],
            run_id,
            room_to_document(
                run_id,
                run.get("result"),
                status,
                run.get("created_at")
                or datetime.now(timezone.utc).isoformat(),  # noqa: UP017
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
    the browser can actually show.

    Two rewrites, both for the same reason — this sentence keeps promising
    more than the run can guarantee:

    1. It used to end "they'll be readable here once the room view for them
       ships", honest while `_salvage`'s `categories` had nowhere to render.
       That view shipped in Task 6, so the deferral became the false part.
    2. Its replacement said "Every researcher's findings and the sources
       behind them were gathered". Neither half survives inspection. `_salvage`
       returns True when ANY category has findings, so a ceiling that trips
       while two researchers are still working produces this exact message
       over two empty categories — "every researcher" is asserted, never
       checked. And `parse_findings` keeps a Finding whose every cited URL
       failed to resolve, with `citations=[]`; `_maybe_warn_empty_ledger`
       above exists because a whole run can land that way, so "the sources
       behind them" is not guaranteed for a single fact, let alone all of
       them.

    What is true without qualification, in every branch that reaches here, is
    that whatever did get filed is saved and reachable. This says that and
    stops. "did file" is doing the work: it scopes the sentence to what exists
    instead of asserting a set. The room view itself counts the categories and
    states the number (web/app.js's noBibleCopy), which is the right place for
    a count: it has the payload, and this function has only a cause string.
    """
    return (
        f"{cause} The findings the researchers did file are saved in this "
        "room's drawers."
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
        # The capability that guards this run's SSE stream. See stream_events
        # for why the stream cannot use the Authorization header every other
        # route does, and why this is a per-run secret rather than the
        # caller's ID token. Full 32 hex characters, unlike run_id's truncated
        # 12: run_id is an identifier that appears in URLs and logs, this is a
        # secret, and they should not have the same entropy.
        #
        # Deliberately NOT persisted. _persist builds its document from
        # room_to_document(run["result"], …), never from this dict, and
        # get_room's in-memory branch returns only status and result — so this
        # key lives and dies in this process, with the run it guards. If a
        # future change ever serialises the run dict wholesale, this field is
        # the one that must be stripped first.
        "stream_key": secrets.token_hex(16),
        "search_count": 0,
        "ledger": SourceLedger(),
        "uid": uid,
        # Taken once, here, and reused by every _persist call this run makes
        # and by get_room's in-memory branch. See _persist for what a second
        # timestamp cost.
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
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
    return {"run_id": run_id, "stream_key": _runs[run_id]["stream_key"]}


@app.get("/api/rooms/{run_id}/events")
async def stream_events(
    run_id: str,
    k: str | None = None,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream one run's progress, to the caller who started it.

    This is the only /api route that cannot use the Authorization header, and
    that is a browser constraint rather than a choice: EventSource sends no
    custom headers, so `_require_uid` has nothing to read. For most of this
    project's life the route consequently checked nothing at all, while
    `_require_uid`'s own docstring asserted the universal it was the sole
    exception to — anyone holding a run_id could stream someone else's
    research: their objectives, their query strings, their agents' progress.
    That docstring now names this exception explicitly, because it is the
    first thing anyone auditing the auth posture reads.

    `k` is a per-run capability minted in create_room and returned to the
    caller that started the run, alongside run_id. The alternative was passing
    the Firebase ID token as a query parameter, which would have written a
    live, replayable credential into Cloud Run's access logs and every
    Referer header — the same class of mistake star/auth.py was being fixed
    for in the same breath. A per-run key is narrower than the identity it
    stands in for: it grants exactly one run's event stream, and it dies with
    the process that holds the run.

    It is a query parameter too, so it lands in Cloud Run's requestUrl field
    like any other. That exposure is REDUCED, not avoided, and the difference
    is the whole argument: a leaked ID token is a live credential for one
    person's entire account until it expires, while a leaked stream key buys
    one already-finished run's event log on an instance that has since
    restarted.

    A bad key 404s rather than 403ing, and with the same detail as an unknown
    run. 403 would confirm that a guessed run_id exists, turning this check
    into an oracle for the thing it protects.

    compare_digest rather than `!=` because this is a secret comparison and
    the timing of a mismatch should not describe the secret. `or ""` because
    compare_digest raises on None.
    """
    run = _runs.get(run_id)
    if run is None or not secrets.compare_digest(k or "", run["stream_key"]):
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
        # `created_at` is merged in rather than left to the pipeline, because
        # `run["result"]` is built from ADK session state (see _run_pipeline
        # and _salvage) and that state has never held a wall-clock time. The
        # stored branch below carries the field inside `result`
        # (star/store.py's document_to_room), and these two branches serve the
        # SAME room minutes apart — a just-finished build reads through here,
        # the same room read from the rail tomorrow reads through Firestore.
        # If only one of them carried the date, a receipt's `RET` stamp would
        # appear or vanish depending on which path answered, which is the kind
        # of drift a provenance claim cannot afford.
        result = run["result"]
        if result is not None:
            result = {**result, "created_at": run.get("created_at") or ""}
        return {"status": run["status"], "result": result}

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


# --- Pipeline B: Script Check ----------------------------------------------
#
# A check is answered inside the request that asked for it. No run_id, no
# stream_key, no SSE, no entry in `_runs` — spec.md's Decision 5, and the
# argument is arithmetic rather than taste. Everything above exists because a
# build runs 146s to 420s+ and no client holds a request open that long; a
# check is one extraction plus one verification with at most eight searches.
# Reusing that apparatus would import its capability key, its resume cursor,
# its eviction rules, and its four terminal statuses to solve a problem this
# pipeline does not have. It also makes check_scene a normal blocking MCP
# tool, which is what an agent expects.

_CHECK_APP = "star"
# A second runner because it runs a second root agent. It carries its own
# InMemorySessionService, so nothing a check puts in state can be read by
# _salvage, which looks its sessions up through _runner.
_check_runner = InMemoryRunner(agent=check_scene, app_name=_CHECK_APP)

# Pipeline A passes user_id="web", naming the door the run came through. A
# check has two doors onto one code path, so this names the pipeline instead.
# Nothing reads it: the sessions are per-process and dropped when the check
# ends.
_CHECK_USER = "check"
# The run's user message, and deliberately not the scene. The scene travels in
# session state so it always renders inside claim_extractor's <scene> markers
# (star/agents/script_check.py's check_state). A scene posted as the user turn
# arrives in instruction position, which is the one thing those delimiters
# exist to prevent, and a scene is a longer and more adversarial paste than a
# treatment.
_CHECK_TURN = "Check the scene on file against this room."


def _room_files(document: dict) -> str:
    """Assemble a stored room's own research for the verifier's prompt.

    Server-side, deliberately. "The room is consulted before a search is
    spent" is enforced by putting the room's files in front of the verifier
    before it can reach a tool at all, and that only means something if the
    block is built from the stored document rather than asked for.

    Only findings carrying at least one citation are printed, which is the
    load-bearing choice here. The verifier may cite only URLs it actually saw,
    so a fact with no URL behind it gives it nothing it is allowed to name;
    a verdict resting on one comes back with an empty sources field and
    star/verdicts.py downgrades it to unverifiable regardless. Printing those
    facts would spend prompt on evidence the grammar cannot carry. It also
    keeps one measurement meaning one thing: this block is empty exactly when
    `ledger_from_room` is empty, because both are built from the same
    citations, so "the room's files were empty" is a single fact rather than
    two that can disagree.
    """
    categories = (document or {}).get("categories")
    if not isinstance(categories, dict):
        return ""

    blocks: list[str] = []
    for category, doc in categories.items():
        lines: list[str] = []
        for finding in (doc or {}).get("findings") or []:
            cited = (finding or {}).get("citations") or []
            citations = [c for c in cited if c.get("url")]
            fact = str((finding or {}).get("fact") or "").strip()
            if not citations or not fact:
                continue
            lines.append(f"- {fact} :: {', '.join(c['url'] for c in citations)}")
            for citation in citations:
                # Collapsed to one line because the block is read as a list of
                # facts and a multi-line excerpt would look like three more
                # findings.
                excerpt = " ".join(str(citation.get("excerpt") or "").split())
                if excerpt:
                    title = citation.get("title") or citation["url"]
                    lines.append(f'    {title}: "{excerpt}"')
        if lines:
            blocks.append("\n".join([category.upper().replace("_", " "), *lines]))

    return "\n\n".join(blocks)


def _cover_note(claims: list, room_files: str) -> str:
    """The one line a thin result needs so it does not read as a failure.

    Two results are legitimately thin. A scene of pure interior dialogue
    asserts nothing about the world and comes back with an empty claim set,
    which is a result. A partial or interrupted room filed nothing, and a
    check against it runs on fresh search alone, which is also a result. Both
    reach a reader as a blank panel unless something says what happened, and
    neither is a failure.

    The no-claims line wins when both are true. A check with nothing to check
    did not lean on a search either, so describing what it worked from would
    be describing work that never happened.

    Nothing here asserts that a search ran. The room being empty is known
    before the pipeline starts; whether the room or a fresh search answered is
    a per-claim fact, and it is already computed per claim in
    `citation_sources`.
    """
    if not claims:
        return (
            "Nothing in this scene made a claim about the world, so there was "
            "nothing for the department to check."
        )
    if not room_files:
        return (
            "This room filed no sources of its own, so the check had nothing "
            "to work from but a fresh search."
        )
    return ""


async def _check_events(session_id: str, run_ledger: SourceLedger) -> dict:
    """Run the check to its end and hand back the session state it left.

    The ledger is fed here, by the server, out of
    `event.get_function_responses()` — the same path `_run_pipeline` uses for
    a build. That is what gives a citation hydrated during a check the
    identical trust property as one hydrated during a build: it is in the
    ledger only because parallel_search returned it, and nothing the verifier
    writes can put a source there.

    Raises on failure and owns no outcome; `_run_check` decides what the
    caller is told. Kept separate so the whole pipeline sits under one
    wall-clock ceiling.
    """
    message = types.Content(role="user", parts=[types.Part(text=_CHECK_TURN)])

    async for event in _check_runner.run_async(
        user_id=_CHECK_USER, session_id=session_id, new_message=message
    ):
        for response in event.get_function_responses() or []:
            run_ledger.record(
                getattr(event, "author", None) or "verifier",
                getattr(response, "response", None),
            )

    session = await _check_runner.session_service.get_session(
        app_name=_CHECK_APP, user_id=_CHECK_USER, session_id=session_id
    )
    return session.state if session else {}


async def _forget_check_session(session_id: str) -> None:
    """Drop the ADK session a finished check ran on.

    Two reasons, and the second is the one that matters. The session holds the
    scene verbatim, and the scene is the paste this surface promises can be
    deleted — a copy of it living in this process for the life of the instance
    would make that promise smaller than it sounds. And checks are admitted on
    `_require_uid` alone, so unlike builds nothing bounds how many run in a
    day; an InMemorySessionService that only ever grows is a leak with no
    ceiling on a service pinned to min-instances=1.

    Never raises: the check already succeeded or already failed by the time
    this runs, and losing the cleanup must not change either answer.
    """
    try:
        await _check_runner.session_service.delete_session(
            app_name=_CHECK_APP, user_id=_CHECK_USER, session_id=session_id
        )
    except Exception:
        logger.exception("Failed to drop the session for check %s", session_id)


async def _run_check(uid: str, run_id: str, scene: str) -> ScriptCheckResult:
    """Check one scene against one filed room, and file what comes back.

    Transport-free on purpose. The endpoint below and the MCP `check_scene`
    tool call this same function object, so "one department, two doors" is
    mechanical rather than asserted (spec.md's Decision 4).

    Cross-uid isolation holds by construction rather than by a check anyone
    has to remember to write. The room is read through
    `_store.get(uid, run_id)`, whose path is rooted at `users/{uid}`, so
    another caller's room is not *found and refused* — it is not found, which
    is the same answer a room that never existed gets, down to the string.

    Refusals raise HTTPException because both doors want the same three
    things: a status, a message, and nothing else. The browser gets them for
    free and the MCP router reads `.detail` to build its CallToolResult.
    """
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    # A room still being built has filed nothing yet, so a check against it
    # would spend up to eight live searches to produce a check leaning on
    # nothing. The status is read from `_runs` rather than from the document
    # because the document says "running" in two different situations: a build
    # genuinely in flight, and one whose asyncio task did not survive a restart.
    # get_room recovers the second as "interrupted", and a check against an
    # interrupted room is a supported case that runs on fresh search alone.
    # Refusing on the stored status alone would refuse both, and the second one
    # forever. The uid comparison mirrors get_room's in-memory branch, for the
    # same reason: `_runs` is keyed by run_id and is not scoped by uid.
    live = _runs.get(run_id)
    if live is not None and live.get("uid") == uid and live.get("status") == "running":
        raise HTTPException(
            409,
            "This room is still being built. Give the department a moment to "
            "finish filing, then check the scene against it.",
        )

    room_files = _room_files(document)
    run_ledger = SourceLedger()
    timeout = config.check_timeout_seconds()
    session = await _check_runner.session_service.create_session(
        app_name=_CHECK_APP,
        user_id=_CHECK_USER,
        state=check_state(scene, room_files),
    )
    try:
        try:
            state = await asyncio.wait_for(
                _check_events(session.id, run_ledger), timeout=timeout
            )
            # ADK leaves the extractor's output in state as a plain dict. A
            # claim set that fails validation is a failure worth seeing rather
            # than one to paper over with an empty list — an empty list reaches
            # the reader as "nothing in this scene made a claim about the
            # world", and a silent lie that looks like a result is the exact
            # failure the missing-`?` guard on {scene} exists to prevent.
            claims = ClaimSet.model_validate(state.get("claims")).claims
        except TimeoutError:
            logger.warning("Check on room %s exceeded its %ss ceiling", run_id, timeout)
            raise HTTPException(
                504,
                f"The check ran past its {timeout}-second limit and was "
                "stopped. Try it again with a shorter scene.",
            ) from None
        except Exception:
            # Same posture as _execute: the detail goes to the log and the
            # reader gets plain language with none of our vocabulary in it.
            # This surface is public, and `f"{type(exc).__name__}: {exc}"` once
            # handed a stranger library names, table names, and a stray
            # credential out of an error string.
            logger.exception("Check on room %s failed", run_id)
            raise HTTPException(
                502,
                "The department hit an unexpected problem and could not "
                "finish the check. The details are in the server log.",
            ) from None
    finally:
        await _forget_check_session(session.id)

    searches = int(state.get("search_count") or 0)
    # The fifth-envelope failure in the only form Pipeline B can see it: the
    # tool ran, the ledger stayed empty, and every citation this check produces
    # will come back unsourced. _maybe_warn_empty_ledger pushes that as a
    # visible SSE event for a build; a check has no stream, so it goes to the
    # log.
    if searches > 0 and len(run_ledger) == 0:
        logger.warning(
            "Check on room %s ran %s searches and recorded no sources — the ADK "
            "function-response envelope may have changed shape",
            run_id,
            searches,
        )

    result = annotate(
        state.get("verdicts"),
        claims,
        ledger_from_room(document),
        run_ledger,
        # The server's own fact, never the model's. parallel_search holds the
        # ceiling and counts every allowed spend into session state, so this is
        # the count of searches that actually ran measured against the ceiling
        # they ran under. The verifier's `budget:` prefix is a claim about the
        # same thing, and star/verdicts.py honours it only where this agrees.
        searches >= config.max_searches_per_check(),
        scene_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        search_count=searches,
    )
    result = result.model_copy(update={"cover_note": _cover_note(claims, room_files)})

    # Off the event loop; see list_rooms for why. Best-effort for the same
    # reason _persist is: the answer was decided above and a Firestore hiccup
    # should cost durability, never correctness. The cost is named rather than
    # hidden — the caller holds a scene_id the GET below will not find — and it
    # is the cheaper of the two failures, because the alternative discards a
    # check that already spent real searches to produce.
    try:
        await asyncio.to_thread(
            _store.save_scene,
            uid,
            run_id,
            result.scene_id,
            scene_to_document(jsonable_encoder(result), scene),
        )
    except Exception:
        logger.exception("Failed to file check %s on room %s", result.scene_id, run_id)

    return result


class SceneRequest(BaseModel):
    scene: str


@app.post("/api/rooms/{run_id}/scenes")
async def create_scene(
    run_id: str, req: SceneRequest, authorization: str | None = Header(None)
) -> dict:
    uid = _require_uid(authorization)
    scene = req.scene.strip()
    # An empty scene is refused here because it cannot be refused upstream.
    # claim_extractor's `{scene}` carries no `?`, so a scene the server never
    # seeded raises rather than rendering an empty block — but an empty *string*
    # seeds fine, renders an empty block, and returns zero claims, which reads
    # on screen as "nothing in this scene made a claim about the world". That
    # guard cannot see this case; this is where it is caught.
    if not scene:
        raise HTTPException(400, "Paste a scene for the department to check.")
    if len(scene) > config.max_scene_chars():
        raise HTTPException(
            400,
            f"Scenes are capped at {config.max_scene_chars()} characters — "
            "send the department a scene, not the script.",
        )
    # Note what is NOT here: a rate limiter. A check spends real searches, but
    # `_ip_limiter` and `_daily_cap` both count rooms, and the per-uid limiter
    # the MCP door needs does not exist yet. Admission for a check is
    # `_require_uid` alone today, and that is a gap rather than a decision.
    return jsonable_encoder(await _run_check(uid, run_id, scene))


@app.get("/api/rooms/{run_id}/scenes")
async def list_scenes(run_id: str, authorization: str | None = Header(None)) -> dict:
    # An unknown room and another caller's room both answer with an empty list
    # rather than a 404. The path is rooted at `users/{uid}`, so there is
    # nothing to find in either case and no read that could tell the two apart
    # — the no-oracle posture get_room and stream_events already take, arrived
    # at here by construction instead of by a decision.
    uid = _require_uid(authorization)
    # Off the event loop; see list_rooms for why.
    scenes = await asyncio.to_thread(_store.list_scenes, uid, run_id)
    return {"scenes": scenes}


@app.get("/api/rooms/{run_id}/scenes/{scene_id}")
async def get_scene(
    run_id: str, scene_id: str, authorization: str | None = Header(None)
) -> dict:
    """Read one filed check back, in the shape the check itself returned.

    Replayable without re-running: the claims are exact substrings of the
    stored scene rather than offsets into it, so the surface can mark the same
    scene the same way from this payload alone.
    """
    uid = _require_uid(authorization)
    document = await asyncio.to_thread(_store.get_scene, uid, run_id, scene_id)
    if document is None:
        raise HTTPException(404, "Unknown check")
    return document_to_scene(document)


@app.delete("/api/rooms/{run_id}/scenes/{scene_id}")
async def delete_scene(
    run_id: str, scene_id: str, authorization: str | None = Header(None)
) -> Response:
    """Remove one filed check, and with it the scene text it stored.

    The whole document goes, not a flag on it. Soft deletion is right for a
    revoked token, which has to be *told* it was revoked; it is wrong for a
    writer's script pages, where the promise made above the paste box is that
    the text stops being kept.
    """
    uid = _require_uid(authorization)
    if not await asyncio.to_thread(_store.delete_scene, uid, run_id, scene_id):
        raise HTTPException(404, "Unknown check")
    return Response(status_code=204)


# --- The card: issued tokens ------------------------------------------------
#
# Three routes, each scoped to its caller before it does anything: two through
# the `_require_uid` every other /api route uses, and POST through
# `_require_claims`, which needs one thing more than a uid. Linking itself
# needs no endpoint — it is client-side against Identity Toolkit — so this is
# the whole server side of the account surface.


class TokenRequest(BaseModel):
    # Defaulted, not required, and that is deliberate on two counts. A reader
    # issuing their first token has nothing to call it yet, and an empty label
    # is a truthful blank on the card rather than a name the department made up
    # for them. It also keeps this route inside the reach of the route-audit
    # test in tests/test_server.py, which posts one body at every POST route
    # and reads a 422 as "did not require auth".
    label: str = ""


@app.post("/api/tokens")
async def create_token(
    req: TokenRequest, authorization: str | None = Header(None)
) -> dict:
    """Issue one MCP token. The only moment its plaintext exists on the wire.

    The refusal below is the coupling that put identity ahead of the agent
    door: an anonymous account's only proof of ownership is a `localStorage`
    entry, so a long-lived token pointing at one is a credential to an account
    nobody can recover — not by the reader, and not by anyone helping them.
    The message names that reason rather than leaving a 403 to explain itself,
    because a bare refusal over a control the card renders as available is the
    kind of answer a reader reads as a bug in the department.

    What the guard keys on, and why it is not the field the spec names, is
    argued in full at star/auth.py's linked_provider. Short version: the spec
    says `firebase.sign_in_provider == "anonymous"`, nobody has measured what
    that field reads after a link, and if it keeps describing how the SESSION
    began then that check refuses exactly the accounts it exists to admit.
    """
    claims = _require_claims(authorization)
    if linked_provider(claims) is None:
        raise HTTPException(
            403,
            "This session has no account attached, so there is nothing to issue "
            "a token against. Attach a Google account from Your card first — a "
            "token issued to a browser-only session would be a key to rooms "
            "nobody could ever sign back in to.",
        )
    label = req.label.strip()
    if len(label) > tokens.MAX_LABEL_CHARS:
        raise HTTPException(
            400,
            f"Token labels are capped at {tokens.MAX_LABEL_CHARS} characters — "
            f"that one is {len(label)}. Name the agent, not the errand.",
        )
    plaintext, token = await tokens.issue(claims["uid"], label, _token_store)
    # The metadata shape GET returns, plus the one field that will never appear
    # again. Same shape both ways so the card has one renderer, and the field
    # that differs is the one it has to announce before it draws.
    return {"token": plaintext, **jsonable_encoder(token)}


@app.get("/api/tokens")
async def list_tokens(authorization: str | None = Header(None)) -> dict:
    """Every token this account has issued. Metadata, never the credential.

    There is no route that returns a token's plaintext or its hash, and that is
    the shape of the promise rather than a filter applied on the way out: the
    plaintext was never stored, and `star/tokens.py`'s to_metadata builds the
    payload field by field so the hash cannot ride along on a later change.
    """
    uid = _require_uid(authorization)
    return {"tokens": jsonable_encoder(await tokens.list_for(uid, _token_store))}


@app.delete("/api/tokens/{token_id}")
async def revoke_token(
    token_id: str, authorization: str | None = Header(None)
) -> Response:
    """Revoke one token. Soft, so its next call can be told what happened.

    A token that is not this uid's answers exactly as a token that does not
    exist, down to the string — the no-oracle posture `get_room` and
    `stream_events` already take. Unlike those two it cannot be reached by
    construction: `/mcp_tokens` is a top-level collection with no uid in its
    path, so the ownership comparison is explicit, and it lives next to the
    write in star/store.py rather than here.
    """
    uid = _require_uid(authorization)
    if not await tokens.revoke(uid, token_id, _token_store):
        raise HTTPException(404, "Unknown token")
    return Response(status_code=204)


@app.get("/config.js")
async def browser_config() -> Response:
    """The Firebase web key is a public project identifier, not a secret.

    The OAuth client id is public in the same sense: it names the client, it
    does not authenticate one. It is served here rather than validated at boot
    on purpose. `config.validate_env()` fails the process on anything whose
    absence would be SILENT, and this one's absence is loud by construction:
    the empty string reaches `web/auth.js`, `linkingAvailable()` reads false,
    the card renders the offer as unavailable and says why, and every other
    path in the app keeps working. That is
    `prd.md > Identity That Outlives The Browser`'s fourth criterion satisfied
    by the shape of the config rather than by a code path someone has to
    remember to write.
    """
    payload = {
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    }
    google = {"clientId": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")}
    return Response(
        f"export const FIREBASE = {json.dumps(payload)};\n"
        f"export const GOOGLE = {json.dumps(google)};",
        media_type="application/javascript",
    )


_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
