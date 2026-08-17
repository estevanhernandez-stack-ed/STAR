"""STAR web service.

FastAPI app that runs Pipeline A ("Build the Room") via the ADK Runner and
streams live progress to the browser over SSE.

Run from the repo root:
    uvicorn star.server:app --reload
"""

import asyncio
import functools
import html
import json
import logging
import mimetypes
import os
import secrets
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

from fastapi import (  # noqa: E402
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.encoders import jsonable_encoder  # noqa: E402
from fastapi.responses import (  # noqa: E402
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from star import bible, chain, config, defence, exports, sweep  # noqa: E402

config.validate_env()

from star import tokens  # noqa: E402
from star.agents import requisition  # noqa: E402
from star.agents import sweep as agent_sweep  # noqa: E402
from star.agents.pipelines import build_room, check_scene  # noqa: E402
from star.agents.script_check import check_state  # noqa: E402
from star.agents.synthesis import synthesis_agent  # noqa: E402
from star.auth import linked_provider, verify_claims, verify_token  # noqa: E402
from star.findings import parse_findings  # noqa: E402
from star.guards import DailyCap, RateLimiter  # noqa: E402
from star.ledger import (  # noqa: E402
    SourceLedger,
    ledger_from_chain,
)
from star.mcp.router import build_mcp_router  # noqa: E402
from star.models import Category, Claim, ClaimSet, ScriptCheckResult  # noqa: E402
from star.oauth import clients, codes, pkce  # noqa: E402
from star.oauth import metadata as oauth_metadata  # noqa: E402
from star.oauth import tokens as oauth_tokens  # noqa: E402
from star.oauth import validate as oauth_validate  # noqa: E402
from star.store import (  # noqa: E402
    CapStore,
    ClientStore,
    RoomStore,
    TokenStore,
    document_to_room,
    document_to_scene,
    document_to_sweep,
    room_to_document,
    scene_to_document,
    sweep_to_document,
)
from star.verdicts import annotate, count_unmatched  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(
    title="STAR — Story & Treatment Agentic Research",
    # Public, unauthenticated endpoint. The schema exposes no secrets, but it
    # hands an attacker a map of every route and shape for free.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def _deny_framing(request: Request, call_next):
    """Nothing this app serves may be rendered inside someone else's frame.

    Global rather than scoped to one path, because the rule is true of every
    surface here and a header that has to be remembered per-route is a header
    that will be forgotten on the next one.

    THE PATH THAT MADE IT NECESSARY is the OAuth consent screen. That page is
    the one place in the department where a human presses a control that hands
    something away, which makes an invisible frame positioned over `Approve`
    the classic attack on exactly this shape of page: the reader believes they
    are clicking something on the attacker's site and they are granting an
    agent access to their rooms.

    `web/consent.html` carries a meta CSP of its own as defence in depth, and
    it cannot carry this one: `frame-ancestors` is **ignored** when it arrives
    in a `<meta>` tag rather than a real response header (CSP Level 3 forbids
    it there). So the page genuinely cannot supply this control and the server
    has to. Both headers are sent because `X-Frame-Options` is what older
    engines honour and `frame-ancestors` is what supersedes it.
    """
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

    # REVALIDATE, ALWAYS, unless the handler already said something stricter.
    #
    # StaticFiles sends an `etag` and a `last-modified` and no `Cache-Control`
    # at all, which leaves a browser applying HEURISTIC freshness: it may serve
    # a stored copy for a while without asking whether it is still current.
    # This app has no build step, so nothing is content-hashed — `consent.js` is
    # `consent.js` forever — and the only signal a deploy happened is the etag
    # nobody was required to check.
    #
    # Measured 2026-08-10, and it cost a wrong diagnosis before it cost
    # anything else: a fix deployed correctly, `curl` returned the new file, and
    # the browser kept enforcing the old page's Content-Security-Policy. The
    # deploy had taken and the reader had not. On a demo that is a recording of
    # a version nobody shipped.
    #
    # `no-cache` is not `no-store`: the copy is kept and revalidated, so the
    # etag turns almost every request into a 304 with no body. Cheap for a
    # single-instance service and correct for one whose filenames never change.
    #
    # Never overwrite a handler that set its own. `/oauth/token` sends
    # `no-store` because its body is a bearer credential, and quietly relaxing
    # that to `no-cache` here would put an access token in a proxy's store.
    response.headers.setdefault("Cache-Control", "no-cache")
    return response

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
# The agent door's limiter, and the browser's limiter for scene checks. Same
# class, same ceiling, same key bound as `_ip_limiter` — what differs is what
# a key IS.
#
# `_ip_limiter`'s key is the rightmost X-Forwarded-For entry (see _caller_key),
# and for an MCP client that is one address for as long as the agent runs. A
# desktop agent behind CGNAT shares that address with strangers, so keying the
# agent door on it would let a stranger's traffic throttle a paying caller,
# while one address would also buy every account behind it a single shared
# budget. A token maps to exactly one uid, so the agent door has a better key
# available and uses it.
#
# `max_keys` is not decoration here. RateLimiter.check() sweeps every tracked
# key on every call, O(n), on the single-threaded loop every open SSE stream on
# the instance shares — star/guards.py:31-54 records why the bound stopped
# being incidental once Finding 3 reordered the admission checks. Two key
# spaces below ("build:" and "check:") mean up to two keys per account rather
# than one, which is why the bound matters more here and not less.
_uid_limiter = RateLimiter(
    max_per_window=config.max_rooms_per_ip_per_hour(),
    window_seconds=3600,
    max_keys=config.max_rate_limiter_keys(),
)
# PERSISTED, so a redeploy no longer hands the world a fresh hundred rooms.
# The in-memory version reset on every push and every instance recycle —
# see DailyCap's own docstring for what that was worth in searches.
_daily_cap = DailyCap(max_per_day=config.max_rooms_per_day(), store=CapStore())


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


async def _uid(authorization: str | None = Header(None)) -> str:
    """`_require_uid` as a dependency, for the routes that take a body.

    THE ORDER IS THE WHOLE REASON THIS EXISTS. A route that reads its header
    inside the handler is a route FastAPI has already validated the body of:
    the handler never runs when a body is malformed, so an anonymous caller
    sending `{}` got a 422 naming the field it was missing. Six write routes
    answered that way — `create_room`, `create_sweep`, `import_rooms`,
    `create_question`, `create_scene` and `annotate_sweep` — handing a stranger
    a schema for surfaces that spend a writer's money.

    Nothing executed and nothing leaked but the shape of a request body, so the
    severity is low and the class is not: `docs/smoke-2026-08-12.md` claimed
    "every new route answers 401 unauthenticated" on the strength of a suite
    that only ever tested GETs. It was the third passing test over an
    unasserted outcome in this build, and the other two are confessed in that
    same file.

    A dependency that raises is solved BEFORE the dependant's own body params
    are validated, so this short-circuits to 401. Measured rather than trusted
    — see `test_no_api_route_answers_a_stranger_with_its_schema`, which walks
    every declared route rather than a list somebody maintains.
    """
    return _require_uid(authorization)


async def _claims(authorization: str | None = Header(None)) -> dict:
    """`_require_claims` as a dependency. See `_uid` for the ordering it buys.

    `POST /api/tokens` takes a body whose fields are all optional, so `{}`
    parsed and reached the handler and answered 401 — while an unparseable body
    was refused with a 422 first. One route, two answers to the same stranger,
    depending on how badly they guessed the shape.
    """
    return _require_claims(authorization)


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


def _persist(run: dict, run_id: str, status: str, note: str = "") -> None:
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
                # What the run cost, taken from the run rather than from a
                # result it may not have. A build that failed still spent live
                # searches and a slot of the shared daily budget, and neither
                # is refunded — so the room has to be able to say so.
                spent={
                    "search_count": run.get("search_count") or 0,
                    "source_count": len(run.get("ledger") or ()),
                },
                # The same sentence the run pushed down the stream, kept for
                # the reader who was not watching it.
                note=note,
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
                # A salvaged run is the case where this matters most: the
                # bible is the half that did not arrive, so whatever the
                # editor managed to say about its own turn is the only
                # first-hand evidence of why.
                "bible_finish_reason": run.get("bible_finish_reason"),
                "bible_tokens": run.get("bible_tokens"),
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

        # What the model said about its own turn, kept for the one author
        # whose output IS the product. Every diagnosis of a truncated bible
        # before this was archaeology on stored text — counting headings weeks
        # later and reasoning backwards — because the two facts that settle it
        # were on the event all along and were read by nobody. `finish_reason`
        # says whether the document ended or was cut off; the token counts say
        # what ate the ceiling, which is how a thinking budget that was being
        # silently ignored went a day and a half without being noticed.
        if author == "synthesis":
            reason = getattr(event, "finish_reason", None)
            if reason is not None:
                run["bible_finish_reason"] = getattr(reason, "name", str(reason))
            usage = getattr(event, "usage_metadata", None)
            if usage is not None:
                run["bible_tokens"] = {
                    "thinking": getattr(usage, "thoughts_token_count", None) or 0,
                    "output": getattr(usage, "candidates_token_count", None) or 0,
                }

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

                # CHECKPOINT, and the reason a deploy stopped destroying a
                # build's research on 2026-08-16.
                #
                # `_persist` used to run exactly twice: once at creation with
                # an empty result, once at a terminal status. Nothing wrote in
                # between, so a build interrupted at ninety per cent filed
                # NOTHING — the writer opened the room to find `interrupted`
                # and an empty document, having paid for it with searches and
                # a slot of the daily cap that, since e715d61, correctly stays
                # spent.
                #
                # `_salvage` is the whole mechanism and it already existed for
                # the timeout path: it reads the ADK session state, builds the
                # categories filed so far, returns False when there is nothing
                # worth showing, and never raises. So this is that call plus a
                # write, not new machinery.
                #
                # It is safe to overwrite `run["result"]` here. `_run_pipeline`
                # rebuilds it from the final session state when the run ends,
                # and every `_persist` call writes the WHOLE document from
                # `room_to_document`, so a checkpoint adds fields rather than
                # erasing them.
                #
                # Per agent rather than per event: four writes across a build
                # that spends minutes and real money.
                if category is not None and await _salvage(run, run_id):
                    await asyncio.to_thread(_persist, run, run_id, "running")

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
            "bible_finish_reason": run.get("bible_finish_reason"),
            "bible_tokens": run.get("bible_tokens"),
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
            # One string, pushed and stored. Written twice it would drift, and
            # the copy that drifts is the stored one nobody is watching.
            message = _partial_message(
                "The editor ran past the time limit before it could finish "
                "writing the bible."
            )
            _persist(run, run_id, "partial", note=message)
            _push(run, "partial", search_count=run["search_count"], message=message)
        else:
            run["status"] = "error"
            message = (
                f"The department ran past its {timeout // 60}-minute limit and "
                "was stopped before anything could be filed. Try again — a "
                "shorter treatment usually finishes faster."
            )
            _persist(run, run_id, "error", note=message)
            _push(run, "error", message=message)
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
            # No exception class name here either. It is a thinner leak
            # than a full message, but it is still our vocabulary in a
            # stranger's browser, and it reads worse to a human than
            # plain language does. The type is in the log line above.
            #
            # That it is safe for a browser is also what makes it safe to
            # store: this string was written for a stranger before it was
            # written for the database.
            message = _partial_message(
                "The editor hit a problem before it could finish writing "
                "the bible."
            )
            _persist(run, run_id, "partial", note=message)
            _push(run, "partial", search_count=run["search_count"], message=message)
        else:
            run["status"] = "error"
            message = (
                "The department hit an unexpected problem and stopped. "
                "The details are in the server log."
            )
            _persist(run, run_id, "error", note=message)
            _push(run, "error", message=message)

    # Every branch above lands on a terminal status; this is the one place
    # in the run's lifecycle where eviction can never orphan a live build.
    # Excluding this run's own id keeps this exact call from evicting the
    # run whose terminal event it just pushed — see _evict_old_runs.
    _evict_old_runs(exclude=run_id)


# --- Admission: the one path both doors take --------------------------------
#
# `_start_build` is transport-free, and both doors call this same function
# object. `POST /api/rooms` calls it directly; the MCP `build_room` tool calls
# it through `_mcp_start_build` at the foot of this file, which is a
# functools.partial over it and reports `.func is _start_build`. That is what
# makes "one budget, one ceiling, one kill switch" a property of the wiring
# rather than a claim a comment makes (spec.md's Decision 4).
#
# The doors differ in exactly one thing: which free per-caller check runs
# before the shared daily budget is touched. A gate returns None to admit, or
# the sentence the caller should read. Returning the message rather than a bool
# keeps door-specific copy at the door — the browser's caller is an address and
# the agent's is an account, and those two refusals do not read the same —
# while `_start_build` stays the only place the ORDER is written down.


def _ip_gate(request: Request) -> Callable[[str], str | None]:
    """The browser door's per-caller check, keyed on the caller's address.

    Built per request because the key is read off the request; see
    `_caller_key` for why it is the rightmost X-Forwarded-For entry and for
    the honest account of how weak an identity that is. The uid is ignored
    here on purpose: a browser caller's ceiling has always been per address,
    and moving it to the account would let anyone mint a fresh anonymous uid
    for a fresh budget with one page load.
    """

    def gate(_uid: str) -> str | None:
        if _ip_limiter.check(_caller_key(request)):
            return None
        return (
            "That is a lot of rooms in one hour. Give the department a moment "
            "and try again shortly."
        )

    return gate


def _uid_gate(uid: str) -> str | None:
    """The agent door's per-caller check, keyed on the account.

    Same ceiling as the browser's, keyed on the one identity an MCP call
    actually carries. The key is namespaced so a writer's builds and their
    scene checks hold separate windows inside the same limiter: two different
    spends against one ceiling each, rather than one shared allowance where a
    build eats a check's slot.
    """
    if _uid_limiter.check(f"build:{uid}"):
        return None
    return (
        f"Builds are capped at {config.max_rooms_per_ip_per_hour()} an hour "
        "per account, and this account has reached that. The window is a "
        "rolling hour, so the next build is admitted an hour after the "
        "earliest one that counted. Reading rooms you have already filed "
        "costs nothing and is not limited."
    )


async def _start_build(
    uid: str, treatment: str, gate: Callable[[str], str | None]
) -> dict:
    """Admit a build, start it, and hand back what the caller needs to follow it.

    Everything `POST /api/rooms` used to do below `_require_uid`, moved here
    unchanged so the agent door reaches it without reimplementing a line of
    it. Nothing about the run lifecycle moved: `_runs`, the guards, `_execute`,
    and `_persist` all stay exactly where they were.
    """
    treatment = treatment.strip()
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
    # Order matters (Finding 3): the free per-caller check must run first, and
    # DailyCap.check() must be the last thing before this request is
    # actually allowed to run. DailyCap.check() increments on the allow
    # path — it is a spend, not a peek — so checking it before the per-caller
    # limiter meant every request that limiter went on to refuse had
    # already spent a daily slot. Verified: 10 POSTs from one IP against a
    # per-IP limit of 1 produced one build and consumed all 10 daily slots;
    # at production settings (5/hour, 100/day) that is the whole day's
    # budget gone in about two seconds, from one caller, before a single
    # legitimate user is served. Checking the free, in-memory per-caller
    # limiter first means only a request that is actually going to run ever
    # touches the shared daily budget.
    #
    # The gate is the only thing the two doors do differently, and it is the
    # cheap half. Which limiter answers changes; that it answers FIRST does
    # not, and neither does `_daily_cap` being the single thing behind it.
    refusal = gate(uid)
    if refusal is not None:
        raise HTTPException(429, refusal)
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


@app.post("/api/rooms")
async def create_room(
    req: RoomRequest, request: Request, uid: Annotated[str, Depends(_uid)]
) -> dict:
    """The browser door onto a build. Auth, then the shared admission path.

    `uid` arrives as a DEPENDENCY rather than being read off a header inside
    this function, and that is not style: a body param is validated before a
    handler runs, so the header check could only ever happen after `{}` had
    already been refused with a 422 naming `treatment`. See `_uid`.
    """
    return await _start_build(uid, req.treatment, gate=_ip_gate(request))


# --- Writing a bible for a room that has none -------------------------------
#
# A THIRD RUNNER, for the reason the check has a second one: it runs a
# different root agent, and its own InMemorySessionService means nothing this
# puts in state can be read by _salvage, which looks its sessions up through
# _runner.
_BIBLE_APP = "star-bible"
_BIBLE_USER = "bible"
_bible_runner = InMemoryRunner(agent=synthesis_agent, app_name=_BIBLE_APP)
# The user turn, and deliberately not the findings. They travel in session
# state so they always render inside synthesis_agent's own <findings_*>
# markers; research posted as the user turn would arrive in instruction
# position, which is the one thing those delimiters exist to prevent.
_BIBLE_TURN = "Write the research bible for the room on file."


def _bible_state(result: dict) -> dict:
    """A room's stored findings, in the state shape synthesis reads.

    The build seeds these from the researchers as they run. This seeds them
    from what was FILED, which is what makes the editor runnable a second time
    — over a room that arrived in a file and never had researchers at all.

    `findings_{category}` prefers the researcher's own markdown where the room
    kept it, and falls back to the facts themselves. An imported room has no
    markdown by construction, and a list of its facts is the same information
    the markdown carried.

    `sources_{category}` is rebuilt in parallel_search's exact format, `- title
    :: url`, and capped by the same knob. That cap is not tidiness: every title
    fed in is a title synthesis may enumerate back out, and an uncapped list
    drove a nine-minute runaway generation once already.
    """
    result = result or {}
    categories = result.get("categories") or {}
    state: dict = {"story_profile": result.get("story_profile") or {}}
    cap = config.max_sources_per_category()

    for category in Category:
        drawer = categories.get(category.value) or {}
        findings = drawer.get("findings") or []
        markdown = str(drawer.get("markdown") or "").strip()
        if not markdown:
            markdown = "\n".join(
                f"- {finding.get('fact') or ''}" for finding in findings if finding
            )
        state[f"findings_{category.value}"] = markdown

        seen: list[str] = []
        lines = ""
        for finding in findings:
            for citation in (finding or {}).get("citations") or []:
                url = str((citation or {}).get("url") or "").strip()
                if not url or url in seen or len(seen) >= cap:
                    continue
                seen.append(url)
                title = " ".join(str((citation or {}).get("title") or "").split())[:120]
                lines += f"- {title or url} :: {url}\n"
        state[f"sources_{category.value}"] = lines

    return state


async def _write_bible(uid: str, run_id: str) -> dict:
    """One editor pass over a room's filed research. Transport-free.

    NO SEARCHES. This is the whole reason it can be offered on a room somebody
    was handed: the expensive half of research — the live searches and the
    hydration that stands behind every citation — travelled in the file. What
    is left is the editor, one model call, over findings the room already
    holds. A bible written from the findings this room actually has is also
    the only kind that cannot describe research that did not survive the file.

    Refuses a room that already has one. Rewriting a bible is a destructive act
    on a document a build was paid for, and it is not what this is; a room
    whose bible came back truncated is a different problem with its own
    coverage warning already on the page.
    """
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")
    if str(document.get("status") or "") == "running":
        raise HTTPException(
            409, "This room is still being built. Its bible is on the way."
        )

    result = document_to_room(document)
    if str(result.get("research_bible") or "").strip():
        raise HTTPException(
            409,
            "This room already has a bible. Writing a second one over it would "
            "discard the document its build paid for.",
        )
    if not any(
        (drawer or {}).get("findings") for drawer in (result.get("categories") or {}).values()
    ):
        raise HTTPException(
            400,
            "This room has no findings to write a bible from. Nothing was spent.",
        )

    # After both refusals and before the model call, for the reason the check's
    # own limiter sits where it does: RateLimiter.check() records on the allow
    # path, so charging an account's window for a room that cannot be written
    # would ration the wrong thing. Its own key space — an editor pass is not a
    # build and not a check, and none of the three should eat another's slots.
    if not _uid_limiter.check(f"bible:{uid}"):
        raise HTTPException(
            429,
            f"Writing a bible is capped at {config.max_rooms_per_ip_per_hour()} "
            "an hour per account, and this account has reached that. The window "
            "is a rolling hour.",
        )

    session = await _bible_runner.session_service.create_session(
        app_name=_BIBLE_APP, user_id=_BIBLE_USER, state=_bible_state(result)
    )
    message = types.Content(role="user", parts=[types.Part(text=_BIBLE_TURN)])
    try:
        async for _ in _bible_runner.run_async(
            user_id=_BIBLE_USER, session_id=session.id, new_message=message
        ):
            pass
        state = await _bible_runner.session_service.get_session(
            app_name=_BIBLE_APP, user_id=_BIBLE_USER, session_id=session.id
        )
        written = str((state.state if state else {}).get("research_bible") or "").strip()
    except Exception:
        logger.exception("The editor failed writing a bible for room %s", run_id)
        raise HTTPException(
            502,
            "The editor could not finish. Nothing was changed, and the "
            "research in the drawers is untouched.",
        ) from None
    finally:
        try:
            await _bible_runner.session_service.delete_session(
                app_name=_BIBLE_APP, user_id=_BIBLE_USER, session_id=session.id
            )
        except Exception:
            logger.exception("Failed to drop a bible-writing session")

    if not written:
        raise HTTPException(
            502,
            "The editor came back with nothing. Nothing was changed, and the "
            "research in the drawers is untouched.",
        )

    # Written straight onto the stored document rather than through
    # room_to_document, which rebuilds the whole room from a result — and the
    # result this has is a READ shape, not the one a build produces. Two
    # fields, on a document already correct in every other respect.
    document["research_bible"] = written
    document["bible_written_at"] = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    await asyncio.to_thread(_store.save, uid, run_id, document)
    return {"run_id": run_id, "research_bible": written}


@app.post("/api/rooms/{run_id}/bible")
async def write_bible(run_id: str, authorization: str | None = Header(None)) -> dict:
    """Write a bible for a room that has none.

    The half of the import that is not free. Everything else about an imported
    room arrived in the file; the bible is a document ABOUT those findings and
    is written here, from the findings this room actually holds, so the two can
    never disagree. One model call, no searches.
    """
    uid = _require_uid(authorization)
    return await _write_bible(uid, run_id)


class RoomImport(BaseModel):
    csv: str
    apply: bool = False


def _as_download(export: dict) -> Response:
    """One `_export` result, as a file a browser saves rather than renders.

    `nosniff` and an attachment disposition on both, because a content type a
    browser can render is a content type it can be talked into executing, and
    every one of these carries text off the open web.
    """
    return Response(
        content=export["text"],
        media_type=export["media_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{export["filename"]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _export(uid: str, run_id: str, kind: str, sweep_id: str = "") -> dict:
    """One room's research, its story's, its bible or a sweep — as a file.

    Transport-free for the reason `_run_check` and `_run_sweep` are: two doors
    call it and neither should be reaching through the other's response class.
    Returns `{filename, media_type, text}` so the browser route can set its
    headers and the agent door can hand the text to a filesystem it has and
    this process does not.
    """
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    result = document_to_room(document)
    title = (result.get("story_profile") or {}).get("title") or "room"
    built = result.get("created_at")

    if kind == "bible":
        text = exports.bible_markdown(result, run_id)
        if not text:
            raise HTTPException(404, "This room has no bible to download.")
        return {
            "filename": exports.csv_filename(title, built, kind="bible", ext="md"),
            "media_type": "text/markdown; charset=utf-8",
            "text": text,
        }

    if kind == "sweep":
        swept = await asyncio.to_thread(_store.get_sweep, uid, run_id, sweep_id)
        if swept is None:
            raise HTTPException(404, "Unknown sweep")
        return {
            "filename": exports.csv_filename(
                (swept.get("room") or {}).get("title") or "sweep",
                swept.get("created_at"),
                unique=swept.get("sweep_id") or sweep_id,
            ),
            "media_type": "text/csv; charset=utf-8",
            "text": exports.sweep_to_csv(swept),
        }

    if kind == "story":
        documents = await _chain_documents(uid, run_id, document)
        text = exports.chain_to_csv(
            [(rid, document_to_room(doc)) for rid, doc in documents]
        )
        # A chain of one is a room. Naming that file `story` would promise a
        # reader rooms that are not in it.
        label = "story" if len(documents) > 1 else "research"
        return {
            "filename": exports.csv_filename(title, built, kind=label),
            "media_type": "text/csv; charset=utf-8",
            "text": text,
        }

    return {
        "filename": exports.csv_filename(title, built, kind="research"),
        "media_type": "text/csv; charset=utf-8",
        "text": exports.room_to_csv(result, run_id),
    }


async def _import_rooms(uid: str, text: str, apply: bool) -> dict:
    """A research export filed as rooms. Transport-free, for two doors.

    Everything the endpoint's own docstring says about provenance is enforced
    here rather than there, because the agent door reaches this function and
    not that route — and the property that an imported room can never pass for
    a built one must not depend on which door was used.
    """
    if len(text) > config.max_import_chars():
        raise HTTPException(
            400,
            f"That file is {len(text)} characters and the ceiling is "
            f"{config.max_import_chars()}. Import one story's research.",
        )

    rooms, complaints = await asyncio.to_thread(exports.read_room, text)
    cap = config.max_rooms_per_import()
    if len(rooms) > cap:
        raise HTTPException(
            400,
            f"That file holds {len(rooms)} rooms and one import files {cap}. "
            "Send a story rather than a library.",
        )

    now = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    # Minted before anything is written so `continues` can be remapped: the
    # link in the file names the SENDER'S room, which means nothing here, and
    # the only account that can resolve it is one holding both rooms at once.
    # That is exactly this request.
    minted = {sender: uuid.uuid4().hex[:12] for sender, _ in rooms}
    filed = []
    for sender, result in rooms:
        run_id = minted[sender]
        parent = minted.get(result.get("continues") or "", "")
        if result.get("continues") and not parent:
            complaints.append(
                f"“{result['story_profile']['title']}” follows a room "
                "that is not in this file, so it arrives unlinked. Set what it "
                "follows with Name and place."
            )
        filed.append(
            (
                run_id,
                {
                    **result,
                    "continues": parent,
                    "imported_at": now,
                    # NOT carried from the file, and this is the line that does
                    # the work. A count is a claim about searches this account
                    # ran, and it ran none.
                    "search_count": 0,
                },
            )
        )

    preview = [
        {
            "run_id": run_id,
            "title": (result.get("story_profile") or {}).get("title") or "",
            "era": (result.get("story_profile") or {}).get("era") or "",
            "continues": result.get("continues") or "",
            "findings": sum(
                len(drawer.get("findings") or [])
                for drawer in (result.get("categories") or {}).values()
            ),
            "sources": result.get("source_count") or 0,
            "drawers": sorted((result.get("categories") or {}).keys()),
        }
        for run_id, result in filed
    ]

    if apply and filed:
        for run_id, result in filed:
            await asyncio.to_thread(
                _store.save,
                uid,
                run_id,
                room_to_document(run_id, result, "complete", now),
            )

    return {"filed": bool(apply and filed), "rooms": preview, "complaints": complaints}


async def _link_room(uid: str, run_id: str, parent_id: str) -> dict:
    """Make one room follow another, or clear the link. Transport-free.

    Refused by name, each for its own reason, because "that did not work" on a
    link a writer just drew is the least useful sentence available. The room
    list is read once and answers all three.
    """
    parent_id = (parent_id or "").strip()
    if parent_id:
        if parent_id == run_id:
            raise HTTPException(400, "A room cannot continue from itself.")
        rooms = await asyncio.to_thread(_store.list_rooms, uid)
        known = {room["run_id"] for room in rooms}
        if parent_id not in known:
            raise HTTPException(
                404,
                "That room is not filed under this account, so it cannot be "
                "the one this room follows.",
            )
        if _chain_would_close(rooms, run_id, parent_id):
            raise HTTPException(
                400,
                "That room already follows this one, directly or through "
                "another, and a story cannot loop back into itself. Point this "
                "room at an earlier one instead.",
            )
    if not await asyncio.to_thread(_store.set_continues, uid, run_id, parent_id):
        raise HTTPException(404, "Unknown run")
    return {"run_id": run_id, "continues": parent_id}


async def _sweep_draft(uid: str, run_id: str, scenes: list[dict]) -> dict:
    """A whole draft swept against one room. Transport-free, for two doors.

    The BROWSER splits the draft (web/fountain.js) and sends the scenes, and so
    must an agent. No Fountain parser lives on this side, deliberately: a
    second one would be a second answer to "where does a scene begin", and the
    writer would be picking scenes out of one list while the department checked
    another.
    """
    scenes = [
        {
            "index": scene.get("index") or 0,
            "heading": str(scene.get("heading") or ""),
            "text": str(scene.get("text") or "").strip(),
            # Bounded like the check route bounds its own, because this is
            # client-supplied text that gets stored and handed back.
            "key": str(scene.get("key") or "").strip()[:64],
        }
        for scene in scenes
        if str(scene.get("text") or "").strip()
    ]
    if not scenes:
        raise HTTPException(400, "Send the department a draft with scenes in it.")

    cap = config.max_scenes_per_sweep()
    if len(scenes) > cap:
        raise HTTPException(
            400,
            f"That is {len(scenes)} scenes and one sweep reads {cap}. Send a "
            "stretch of the script rather than the whole series.",
        )
    total = sum(len(s["text"]) for s in scenes)
    ceiling = config.max_scene_chars() * cap
    if total > ceiling:
        raise HTTPException(
            400,
            f"That draft is {total} characters and one sweep reads {ceiling}. "
            "Send a stretch of it.",
        )

    return await _run_sweep(uid, run_id, scenes)


@app.post("/api/rooms/import")
async def import_rooms(
    req: RoomImport, uid: Annotated[str, Depends(_uid)]
) -> dict:
    """Somebody else's research, filed into this account.

    THE FIRST WAY A ROOM ENTERS AN ACCOUNT WITHOUT BEING RESEARCHED BY IT, and
    the whole design turns on saying so. Anyone can type a plausible fact and a
    real-looking url into a spreadsheet. If an imported room rendered like a
    built one, "a room reading as better-sourced than its research made it" —
    the property the annotation import refuses to break one claim at a time —
    would be broken wholesale at the room level, by anyone, in one press.

    So an imported room carries `imported_at`, spends no searches and claims
    none, and never gets a bible from the file. Every surface that makes a
    sourcing claim reads that field. The room is still worth having: a
    co-writer handing over a story's research is the case this exists for, and
    they are not attacking anybody.

    ARMED, like `delete_room` and the annotation import: the first call reports
    and writes nothing. This mints rooms in somebody's account and a reader
    should see what they are about to get before they get it.

    Costs nothing against the daily build ceiling, because it spends nothing —
    no searches, no model calls. The bible is where the spend is, and it is a
    separate press on `/api/rooms/{run_id}/bible`.
    """
    return await _import_rooms(uid, req.csv, req.apply)


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


async def _list_rooms_for(uid: str) -> list[dict]:
    """Every room filed under one account. Transport-free; both doors call it.

    Not rate-limited, here or at either door, and that is deliberate rather
    than an omission: a list costs one Firestore query and no searches, so
    rationing it would ration the one call an agent makes to find out what it
    already owns.
    """
    # Off the event loop: the Firestore client is blocking, and this runs on
    # the same single-threaded loop as every other request and every open SSE
    # stream on the instance. Left inline, a slow list call stalls all of
    # them, not just this caller.
    return await asyncio.to_thread(_store.list_rooms, uid)


@app.get("/api/rooms")
async def list_rooms(authorization: str | None = Header(None)) -> dict:
    uid = _require_uid(authorization)
    # Both lists in one answer. The rail draws them apart and a reader who
    # deleted something needs to find it again without knowing an id — without
    # this, the window is thirty days a person cannot reach, and every sentence
    # promising the room is "recoverable in the web app" is false.
    deleted = await asyncio.to_thread(_store.list_deleted_rooms, uid)
    return {
        "rooms": await _list_rooms_for(uid),
        "deleted": deleted,
        "retention_days": config.room_retention_days(),
    }


def _with_coverage(payload: dict) -> dict:
    """Attach what the bible actually covers, measured at read.

    Derived here rather than stored, for the reason a stamp is derived rather
    than authored: the measurement can get better, and a field written into
    fourteen documents on 2026-08-11 could not. Attached on the way OUT of the
    shared read so that both doors carry the same number and the browser never
    has to compute it a second time in a second language.
    """
    result = payload.get("result")
    # The cautions the researchers flagged, lifted out of the bible's prose so
    # a reader who never scrolls it still meets them. One stored room's first
    # note says the writer's own treatment dates its blackout two months wrong;
    # that line sits five screens down inside section one.
    notes = bible.verify_notes(result)
    if notes and isinstance(result, dict):
        result["verify_notes"] = notes
    counts = bible.coverage(result)
    if counts:
        # INSIDE the result, not beside it. The first version of this put the
        # count at the top level of the response and every source test on both
        # sides passed: the server test read `body["bible_coverage"]`, the
        # browser test read `result.bible_coverage`, and neither could see that
        # those were two different places. The live page rendered no note at
        # all. The count belongs to the room, so it travels with the room —
        # through this door, through `get_room`'s payload, and through any
        # projection that keeps the bible.
        result["bible_coverage"] = counts
    return payload


async def _read_room(uid: str, run_id: str) -> dict:
    """One room, live or filed. Transport-free; both doors call it.

    This is also `build_room`'s poll over MCP, which is why there is no fifth
    tool: a run still in flight answers `running` with whatever progress
    exists, a run that did not survive a restart answers `interrupted`, and
    neither is an error. Not rate-limited, for the reason `_list_rooms_for`
    gives.
    """
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
        elif run["status"] != "running" and run.get("search_count"):
            # A run that died before it built a result still spent live
            # searches and a slot of the shared daily budget, and neither is
            # refunded. Answering `null` here means the one window where a
            # caller is most likely to ask what happened — seconds after the
            # failure, while the run is still in memory — is the one window
            # where nothing can tell them what it cost. Terminal statuses
            # only: a `running` run answers `null` by contract and both
            # doors are written against that.
            result = {
                "created_at": run.get("created_at") or "",
                "search_count": run.get("search_count") or 0,
                "source_count": len(run.get("ledger") or ()),
            }
        return _with_coverage({"status": run["status"], "result": result})

    # Off the event loop; see list_rooms above for why.
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    # A deleted room answers as deleted rather than as missing, for the whole
    # window it is recoverable. 404 would be the app lying about what it still
    # holds — and it would make restore impossible for anyone holding the id,
    # which is the one thing the window exists to allow.
    deleted_at = document.get("deleted_at") or ""
    if deleted_at:
        return _with_coverage(
            {
                "status": "deleted",
                "deleted_at": deleted_at,
                "purges_after_days": config.room_retention_days(),
                "result": document_to_room(document),
            }
        )

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
        # The slot goes back. This run spent a search budget and a slot of the
        # shared daily cap and returned whatever had been checkpointed — the
        # process building it went away mid-flight, which is the department's
        # restart rather than the writer's doing. Charging for it is billing
        # for our own deploy.
        #
        # Here rather than anywhere else because this is the ONE place a run is
        # discovered to have died, and `mark_interrupted` returning True means
        # it flipped the document itself — so the refund happens once per run,
        # not once per read.
        _daily_cap.refund()

    return _with_coverage(
        {"status": document.get("status", "complete"), "result": document_to_room(document)}
    )


@app.get("/api/rooms/{run_id}.csv")
async def get_room_csv(
    run_id: str,
    # Aliased rather than named `chain`, because `chain` in this module is the
    # imported star/chain.py and a parameter of that name shadows it inside the
    # one function that most wants to call it.
    whole_chain: bool = Query(False, alias="chain"),
    authorization: str | None = Header(None),
) -> Response:
    """A whole room's research as a spreadsheet.

    A different question from a sweep's CSV: that one says what a draft claimed
    and how it held up, this says what the department FOUND. A writer asked for
    their research and a file that only exists after sweeping a screenplay is
    the wrong shape for the question.

    Registered ABOVE `/api/rooms/{run_id}`, because Starlette matches in
    declaration order and that route would otherwise claim `abc.csv` and 404 on
    a room whose id has no dot in it. The sweep CSV shipped with exactly that
    bug and a comment claiming it had been avoided.

    This room only by default; `?chain=true` widens it to every room this one
    follows. Two files for two questions — "my research" against "this story's
    research" — and the `room` column keeps them apart either way, so the wide
    file sorts back down into the narrow one.

    Narrow is the default because wide is the surprising answer. A writer's own
    research becoming indistinguishable from the room it follows is the outcome
    worth asking for rather than being handed.
    """
    uid = _require_uid(authorization)
    return _as_download(await _export(uid, run_id, "story" if whole_chain else "research"))


@app.get("/api/rooms/{run_id}.md")
async def get_room_bible(run_id: str, authorization: str | None = Header(None)) -> Response:
    """A room's bible as a file, so it can be handed to somebody.

    Until this existed the bible could be read on one screen and reached no
    further: no download, no print sheet, nothing to attach to an email. A
    document a writer paid a build for that cannot leave the tab it renders in
    is not a document they own.

    Registered ABOVE `/api/rooms/{run_id}` for the third time in this file,
    because Starlette matches in declaration order and that route would
    otherwise claim `abc.md` and 404 on a room whose id has no dot in it. The
    sweep CSV shipped with exactly that bug under a comment claiming it had
    been avoided; the room CSV did not, because the order was checked before
    the commit rather than after.

    Markdown rather than PDF: the stored bible IS markdown, so this is the
    document itself rather than a rendering of it, and a reader can open it in
    anything or paste it into their own script. The printable report is the
    other half of that pair and already prints.
    """
    uid = _require_uid(authorization)
    return _as_download(await _export(uid, run_id, "bible"))


@app.get("/api/rooms/{run_id}")
async def get_room(run_id: str, authorization: str | None = Header(None)) -> dict:
    """The browser door onto one room. Auth, then the shared read."""
    uid = _require_uid(authorization)
    return await _read_room(uid, run_id)


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


async def _chain_documents(
    uid: str, run_id: str, first: dict | None = None
) -> list[tuple[str, dict]]:
    """This room and every room it follows, nearest first.

    `first` is the room's document when the caller already holds it, which both
    callers do — they read it to decide whether to refuse. Passing it in is not
    a micro-optimisation: without it this re-read the same document a second
    time on every check, and the test that walks a check's Firestore calls
    caught it immediately.

    Fetched one at a time rather than in a batch, because a story is a handful
    of rooms and each read is uid-scoped by path — which is what keeps a chain
    from ever reaching a room this account cannot see. A `continues` pointing
    at somebody else's room simply ends the walk.
    """
    found: list[tuple[str, dict]] = []
    seen: set[str] = set()
    current = str(run_id or "")
    document = first
    while current and current not in seen and len(found) < chain.MAX_DEPTH:
        if document is None:
            document = await asyncio.to_thread(_store.get, uid, current)
        if document is None:
            break
        seen.add(current)
        found.append((current, document))
        current = chain.parents(document)
        document = None
    return found


def _chain_files(documents: list[tuple[str, dict]]) -> str:
    """Every room in a chain, as one block for the verifier.

    Each room's findings sit under its own name, so an answer can say WHICH
    room held the fact — a chain that cannot is a bigger room with worse
    provenance. Nearest first, so the room a writer is working in is the part
    the verifier reads before its attention is spent.

    THERE IS NO SIZE CEILING HERE, and this docstring claimed one until
    2026-08-17. `_room_files` emits every cited finding and its full excerpt
    with no cap, no slice and no knob; ordering is the only lever. The claim of
    a ceiling was load-bearing in the wrong direction — it made an unbounded
    block look bounded to anyone reading for the reason a catch-all page ends up
    cited for twenty unrelated claims.

    A single-room chain produces exactly what `_room_files` produced before any
    of this existed, which is the property that makes stacking safe to add: an
    unlinked room's checks do not change.
    """
    if len(documents) <= 1:
        return _room_files(documents[0][1]) if documents else ""

    blocks: list[str] = []
    for _, document in documents:
        files = _room_files(document)
        if files:
            blocks.append(
                f"=== FROM THE ROOM: {chain.label(document)} ===\n{files}"
            )
    return "\n\n".join(blocks)


def _draft_years(scenes: list[dict]) -> str:
    """Every year a draft states, oldest first, as one line. Pure.

    REPLACES `_chain_era`, which handed the desk the room's span and was the
    instrument of four wrong verdicts. Rendering the prompt with ADK's own
    injector on 2026-08-13 showed why: the era had a labelled block of its own
    while a claim's year was a key inside a dict repr, so the wrong number read
    like a fact and the right one read like debris. The era is not in the
    prompt at all now.

    The draft's whole set rather than one year, because a sweep crosses scenes
    and the desk should see the span it is working across. Each claim still
    carries the years of the scenes that assert IT, which are what decide it —
    this is context, not the judgement.

    Empty when a draft states no year anywhere, and `{years?}` renders nothing.
    The prompt then tells the desk to say so rather than reach for a period.
    """
    stated = sorted({year for year in sweep.scene_years(scenes).values() if year})
    return ", ".join(stated)


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

    AN IMPORTED ROOM SAYS SO HERE, and until 2026-08-13 it did not. The import
    brand was on every surface a person reads and on none that the verifier
    does: this function printed a typed-in fact and a researched one in the
    same shape, with the same grammar, and the verifier had no way to tell them
    apart. An agent walking the door proved what that costs — it typed "the Vox
    AC30 was accessible to British musicians in the late 1950s" into a
    spreadsheet, imported it, and got a 1958 scene stamped CONFIRMED against
    it, citing the room, with no search spent.

    That is the one thing this department exists to make impossible. Every
    other guard on the import path says the same sentence in its own words —
    `import_rooms` refuses to let the brand come off, the source count is
    counted rather than read, a bible is refused on arrival — and the guard
    stopped exactly where the evidence gets used.
    """
    categories = (document or {}).get("categories")
    if not isinstance(categories, dict):
        return ""

    imported = str((document or {}).get("imported_at") or "").strip()

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

    if not blocks:
        return ""

    if imported:
        # ABOVE the files rather than beside each line. A per-line marker is
        # something a long prompt learns to skip; a banner is the first thing
        # read about the block and stays true for every line under it.
        blocks.insert(
            0,
            "PROVENANCE OF THESE FILES\n"
            f"This room was IMPORTED from a spreadsheet on {imported[:10]}, not "
            "researched. Nobody here ran a search for any of it, and nothing "
            "below was checked when it arrived — a person typed the facts and "
            "the addresses, and either could be invented. Treat every line "
            "under this as a claim somebody made, not as a source.",
        )

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


async def _run_check(
    uid: str, run_id: str, scene: str, scene_key: str = ""
) -> ScriptCheckResult:
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

    # The check's own ceiling, and the reason it is HERE rather than at either
    # endpoint. Both doors reach a check through this one function, so a
    # limiter inside it is a limiter on both by construction, which is the same
    # property `_start_build` buys for a build.
    #
    # It closes a real hole rather than tidying one. Until this line, a check
    # was admitted on `_require_uid` alone: `_ip_limiter` and `_daily_cap` both
    # count ROOMS, so neither one saw a scene, and one check spends up to
    # config.max_searches_per_check() live searches. Anonymous accounts are
    # free and zero-click, so the shape was: mint an account, build one room,
    # then check unlimited scenes against it forever.
    #
    # The ceiling is the same 5/hour a build gets, because it is the same
    # limiter and a limiter carries one ceiling — a second RateLimiter for
    # checks would be a second thing to keep in step with the first, and this
    # is not a second kind of spend. The key is namespaced instead, so the two
    # windows are independent: five builds an hour do not cost a writer their
    # checks, and five checks do not cost them a build. At production settings
    # that bounds one account at 5 * 30 search-equivalents of build and 5 * 8
    # of check per hour. Five checks an hour is the tight end of defensible for
    # a writer working through a script, and it is chosen over unbounded rather
    # than over a measured number; if the harness runs show it biting, the fix
    # is a config knob on this limiter's ceiling, not a second limiter.
    #
    # It runs AFTER the two refusals above and before anything is spent. A
    # RateLimiter.check() records on the allow path — it is a spend, not a peek,
    # the same property Finding 3 turned on — so charging a caller's hourly
    # window for a room that does not exist, or for one still being built,
    # would ration the wrong thing. What this is rationing is searches, and
    # neither of those branches reaches one.
    if not _uid_limiter.check(f"check:{uid}"):
        raise HTTPException(
            429,
            f"Scene checks are capped at {config.max_rooms_per_ip_per_hour()} "
            "an hour per account, and this account has reached that. The "
            "window is a rolling hour, so the next check is admitted an hour "
            "after the earliest one that counted. Reading rooms and filed "
            "checks costs nothing and is not limited.",
        )

    documents = await _chain_documents(uid, run_id, document)
    room_files = _chain_files(documents)
    run_ledger = SourceLedger()
    timeout = config.check_timeout_seconds()
    session = await _check_runner.session_service.create_session(
        app_name=_CHECK_APP,
        user_id=_CHECK_USER,
        state=check_state(scene, room_files, sweep.scene_year(scene)),
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
        # THE WHOLE CHAIN, not this room alone. The verifier was handed
        # every room's files and may cite a url it only saw in the parent;
        # hydrating against one room finds it in neither ledger and
        # downgrades a correct answer to unverifiable.
        ledger_from_chain(document for _, document in documents),
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
            scene_to_document(jsonable_encoder(result), scene, scene_key),
        )
    except Exception:
        logger.exception("Failed to file check %s on room %s", result.scene_id, run_id)

    return result


def _file_findings(
    document: dict, category: Category, filed: list, spent: int
) -> dict:
    """Append findings to a stored room's drawer and move its counts. Pure.

    The drawer may not exist. A build files all four, but a room recovered
    from a failed run keeps only what `_salvage` could reach, and a
    requisition is exactly the tool a writer reaches for on a thin room —
    so the missing-drawer case is the normal one here, not the edge.

    `search_count` moves by the requisition's OWN spend rather than by the
    session's, and the two differ: the researcher may spend two searches and
    file one finding, or spend one and file three. The room's count is what
    the room cost, and the requisition cost what it spent, so the caller
    passes the spend and this adds it.

    `source_count` GROWS BY WHAT IS GENUINELY NEW, and neither of the two
    obvious alternatives is right. Adding this run's ledger size double-counts
    every source the room already held that the requisition also found. And
    recounting citations across the room replaces the stored number with a
    different quantity entirely: `_persist` files `len(run["ledger"])`, the
    distinct urls a build SAW, while a walk of the drawers counts citation
    entries, which misses every source no finding cited and counts twice any
    source two findings share. Measured on the first live requisition, that
    recount moved a real room from 99 to 74 — a room reporting fewer sources
    after research was added to it.

    So the delta is the urls this requisition cited that the room was not
    already citing. Monotonic, and it means what the field has always meant:
    how many distinct sources stand behind this room.
    """
    document = dict(document)
    categories = dict(document.get("categories") or {})

    def _urls(entries: dict) -> set[str]:
        return {
            url
            for entry in entries.values()
            for finding in (entry or {}).get("findings") or []
            for url in (
                str((citation or {}).get("url") or "")
                for citation in (finding or {}).get("citations") or []
            )
            if url
        }

    already = _urls(categories)
    drawer = dict(categories.get(category.value) or {})
    drawer["findings"] = list(drawer.get("findings") or []) + jsonable_encoder(filed)
    categories[category.value] = drawer
    document["categories"] = categories
    document["search_count"] = (document.get("search_count") or 0) + spent
    document["source_count"] = (document.get("source_count") or 0) + len(
        _urls(categories) - already
    )
    return document


async def _question_events(
    category: Category, session_id: str, run_ledger: SourceLedger
) -> dict:
    """Run one requisition to its end and hand back the session state.

    The ledger is fed here, by the server, out of `event.get_function_responses()`
    — the same path `_run_pipeline` and `_check_events` use. That is what gives
    a citation hydrated by a requisition the identical trust property as one
    hydrated by a build: it is in the ledger only because parallel_search
    returned it, and nothing the researcher writes can put a source there.
    """
    runner = requisition.RUNNERS[category]
    message = types.Content(role="user", parts=[types.Part(text=requisition.TURN)])

    async for event in runner.run_async(
        user_id=requisition.USER, session_id=session_id, new_message=message
    ):
        for response in event.get_function_responses() or []:
            run_ledger.record(
                getattr(event, "author", None) or "researcher",
                getattr(response, "response", None),
            )

    session = await runner.session_service.get_session(
        app_name=requisition.APP, user_id=requisition.USER, session_id=session_id
    )
    return session.state if session else {}


async def _forget_question_session(category: Category, session_id: str) -> None:
    """Drop the ADK session a finished requisition ran on.

    Same leak `_forget_check_session` closes, and the same posture: never
    raises, because the answer was already decided and losing the cleanup must
    not change it. A requisition is admitted on the hourly limiter rather than
    the daily cap, so nothing bounds these across a day either.
    """
    try:
        await requisition.RUNNERS[category].session_service.delete_session(
            app_name=requisition.APP, user_id=requisition.USER, session_id=session_id
        )
    except Exception:
        logger.exception("Failed to drop the session for a requisition on %s", session_id)


async def _run_requisition(
    uid: str, run_id: str, question: str, category: Category
) -> dict:
    """Research one question and file it into a room that already exists.

    Transport-free for the reason `_run_check` is: the endpoint below and the
    MCP `research_question` tool call this same function object, so "one
    department, two doors" stays mechanical rather than asserted.

    Cross-uid isolation holds the same way too — the room is read through
    `_store.get(uid, run_id)`, whose path is rooted at `users/{uid}`, so
    another caller's room is not found and refused, it is simply not found.

    Returns the filed finding and the room's new counts. Raises HTTPException
    on every refusal, because both doors want a status and a message.
    """
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    # A room still being built has not finished filing, and a requisition into
    # it would race the build's own terminal write: `_persist` calls `.set()`,
    # which replaces the whole document, so a finding filed here in the seconds
    # before that write would be silently overwritten by a room assembled from
    # session state that never knew about it. The reader would be told their
    # question was researched and filed, and it would be gone. Same in-memory
    # status read as `_run_check`, for the same reason it is not the stored one.
    live = _runs.get(run_id)
    if live is not None and live.get("uid") == uid and live.get("status") == "running":
        raise HTTPException(
            409,
            "This room is still being built. Wait for the department to finish "
            "filing, then ask — a question filed into a room mid-build would be "
            "overwritten when the build lands.",
        )

    # The same limiter builds and checks use, in a third namespace. One
    # requisition spends real searches, and until this line the only thing
    # standing between an agent holding a valid token and an unbounded spend
    # was that the endpoint did not exist yet. Namespaced so the three windows
    # are independent: questions do not cost a writer their builds.
    if not _uid_limiter.check(f"question:{uid}"):
        raise HTTPException(
            429,
            f"Questions filed into a room are capped at "
            f"{config.max_rooms_per_ip_per_hour()} an hour per account, and "
            "this account has reached that. The window is a rolling hour. "
            "Reading a room and asking what it already holds costs nothing "
            "and is not limited.",
        )

    run_ledger = SourceLedger()
    timeout = config.check_timeout_seconds()
    runner = requisition.RUNNERS[category]
    session = await runner.session_service.create_session(
        app_name=requisition.APP,
        user_id=requisition.USER,
        state=requisition.question_state(question, category),
    )
    try:
        try:
            state = await asyncio.wait_for(
                _question_events(category, session.id, run_ledger), timeout=timeout
            )
        except TimeoutError:
            logger.warning(
                "Requisition on room %s exceeded its %ss ceiling", run_id, timeout
            )
            raise HTTPException(
                504,
                f"The researcher ran past its {timeout}-second limit and was "
                "stopped. Nothing was filed. Try a narrower question.",
            ) from None
        except Exception:
            logger.exception("Requisition on room %s failed", run_id)
            raise HTTPException(
                502,
                "The department hit an unexpected problem and could not "
                "finish. Nothing was filed. The details are in the server log.",
            ) from None
    finally:
        await _forget_question_session(category, session.id)

    # Parsed by the same function a build's findings go through, against the
    # ledger this run just filled. A requisitioned finding is therefore cited
    # to the same standard or it is not cited at all.
    doc = parse_findings(state.get(f"findings_{category.value}"), category, run_ledger)
    # Stamped with when THESE sources came back, which is now and not when the
    # room was made. Every other finding in this drawer was retrieved while the
    # room was being built, so the room's `created_at` is their honest date and
    # they carry none of their own — see web/drawer.js on why a caller that
    # cannot supply a retrieval date gets no RET line rather than a borrowed one.
    retrieved = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    filed = [
        finding.model_copy(
            update={"requisition": question, "retrieved_at": retrieved}
        )
        for finding in doc.findings
    ]
    spent = int(state.get("search_count") or 0)
    if not filed:
        # The researcher came back with nothing a parser could read as a
        # finding. Said plainly rather than filed as an empty answer: a room
        # that grows a blank entry every time a question misses is worse than
        # one that stayed still, and the writer has spent their searches either
        # way, which is why the count comes back with the refusal.
        raise HTTPException(
            502,
            "The researcher came back without a citable answer to that "
            f"question, so nothing was filed. It spent {spent} live "
            f"search{'' if spent == 1 else 'es'} trying. A narrower, more "
            "factual question usually lands.",
        )

    document = _file_findings(document, category, filed, spent)
    try:
        await asyncio.to_thread(_store.save, uid, run_id, document)
    except Exception:
        # Named rather than hidden, and fatal here unlike in `_run_check`. A
        # check that fails to persist still hands its caller the answer; a
        # requisition whose whole product IS the write has nothing to return
        # but a claim that the room grew, which would be false.
        logger.exception("Failed to file a requisition on room %s", run_id)
        raise HTTPException(
            502,
            "The research came back but could not be filed into the room. "
            "Nothing was added. Try again.",
        ) from None

    return {
        "run_id": run_id,
        "category": category.value,
        "question": question,
        "findings": jsonable_encoder(filed),
        "search_count": document.get("search_count") or 0,
        "source_count": document.get("source_count") or 0,
    }


async def _extract_claims(scene: str) -> list[dict]:
    """One scene's claims. Spends nothing.

    The claim desk is schema'd and holds no tools, so this is model time and
    no searches — which is the fact the whole sweep is built on. A scene the
    extractor fails on comes back empty rather than raising: one bad scene in
    a feature must not cost the writer the other twenty-three.
    """
    runner = agent_sweep.extract_runner
    session = await runner.session_service.create_session(
        app_name=agent_sweep.EXTRACT_APP,
        user_id=agent_sweep.USER,
        state=agent_sweep.extract_state(scene),
    )
    try:
        message = types.Content(
            role="user", parts=[types.Part(text=agent_sweep.EXTRACT_TURN)]
        )
        async for _ in runner.run_async(
            user_id=agent_sweep.USER, session_id=session.id, new_message=message
        ):
            pass
        state = await runner.session_service.get_session(
            app_name=agent_sweep.EXTRACT_APP,
            user_id=agent_sweep.USER,
            session_id=session.id,
        )
        raw = (state.state if state else {}).get("claims")
        return [claim.model_dump() for claim in ClaimSet.model_validate(raw).claims]
    except Exception:
        logger.exception("Claim extraction failed on a scene")
        return []
    finally:
        try:
            await runner.session_service.delete_session(
                app_name=agent_sweep.EXTRACT_APP,
                user_id=agent_sweep.USER,
                session_id=session.id,
            )
        except Exception:
            logger.exception("Failed to drop a sweep extraction session")


async def _verify_claims(
    claims: list[dict], room_files: str, run_ledger: SourceLedger, years: str = ""
) -> dict:
    """The one verification a sweep runs, over the whole deduped set.

    The ledger is fed here, by the server, out of `event.get_function_responses()`
    — the same path every other pipeline uses, and what gives a citation from a
    sweep the identical trust property as one from a build.
    """
    runner = agent_sweep.verify_runner
    session = await runner.session_service.create_session(
        app_name=agent_sweep.VERIFY_APP,
        user_id=agent_sweep.USER,
        state=agent_sweep.verify_state({"claims": claims}, room_files, years),
    )
    try:
        message = types.Content(
            role="user", parts=[types.Part(text=agent_sweep.VERIFY_TURN)]
        )
        async for event in runner.run_async(
            user_id=agent_sweep.USER, session_id=session.id, new_message=message
        ):
            for response in event.get_function_responses() or []:
                run_ledger.record(
                    getattr(event, "author", None) or "verifier",
                    getattr(response, "response", None),
                )
        state = await runner.session_service.get_session(
            app_name=agent_sweep.VERIFY_APP,
            user_id=agent_sweep.USER,
            session_id=session.id,
        )
        return state.state if state else {}
    finally:
        try:
            await runner.session_service.delete_session(
                app_name=agent_sweep.VERIFY_APP,
                user_id=agent_sweep.USER,
                session_id=session.id,
            )
        except Exception:
            logger.exception("Failed to drop a sweep verification session")


def _scene_keys(scenes: list[dict]) -> list[str]:
    """Every scene this sweep read, by the browser's own name for it.

    EVERY SCENE SENT, not only the ones that raised a claim. A scene of pure
    dialogue asserts nothing about the world and comes back with no claims, and
    it was still read — marking only the productive ones would tell a writer
    their quiet scenes were skipped, which is the opposite of what happened.
    `budget_exhausted` is what says the VERIFICATION ran short; extraction
    covers the whole draft or the sweep fails.

    Deduplicated and order-preserving: a draft that repeats a scene verbatim
    sends one key twice, and the strip only ever asks whether a key is present.
    """
    return list(dict.fromkeys(str(scene.get("key") or "") for scene in scenes if scene.get("key")))


async def _run_sweep(uid: str, run_id: str, scenes: list[dict]) -> dict:
    """Every claim a draft makes, asked once, against one room.

    Transport-free for the reason `_run_check` and `_run_requisition` are.

    ONE RATE-LIMIT SLOT AND ONE BUDGET for a whole screenplay. Scene by scene,
    twenty-four scenes is twenty-four slots of an hourly window that admits
    five — about five hours — and twenty-four independent search budgets. That
    arithmetic, not the deduplication, is the case for this feature: measured
    over a real 24-scene draft the distinct set is 21% smaller than the raw
    one, which helps and is not the point.
    """
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    live = _runs.get(run_id)
    if live is not None and live.get("uid") == uid and live.get("status") == "running":
        raise HTTPException(
            409,
            "This room is still being built. Wait for the department to finish "
            "filing, then sweep the draft against it.",
        )

    if not _uid_limiter.check(f"sweep:{uid}"):
        raise HTTPException(
            429,
            f"Draft sweeps are capped at {config.max_rooms_per_ip_per_hour()} "
            "an hour per account, and this account has reached that. The "
            "window is a rolling hour. One sweep covers a whole draft, so this "
            "is a tighter ceiling than it looks.",
        )

    # Extraction, bounded. Every scene is one model call and none of them
    # spends a search, but opening eighty sockets at once is its own way to
    # fail — and a draft is read in order, so a bounded gate costs a writer
    # nothing they would notice.
    gate = asyncio.Semaphore(config.sweep_extract_concurrency())

    async def one(scene: dict) -> tuple[int, list[dict]]:
        async with gate:
            return int(scene.get("index") or 0), await _extract_claims(
                str(scene.get("text") or "")
            )

    timeout = config.sweep_timeout_seconds()
    try:
        per_scene = await asyncio.wait_for(
            asyncio.gather(*(one(scene) for scene in scenes)), timeout=timeout
        )
    except TimeoutError:
        logger.warning("Sweep on room %s exceeded its %ss ceiling", run_id, timeout)
        raise HTTPException(
            504,
            f"Reading the draft ran past its {timeout}-second limit and was "
            "stopped. Nothing was spent. Try a shorter stretch of the script.",
        ) from None

    per_scene = sorted(per_scene)
    raised = sum(len(found) for _, found in per_scene)
    # The years the draft states, read out of the scene text the server already
    # holds — pure Python, no second model call. Every claim then carries the
    # years it is asserted in, which is what the desk judges against. Before
    # this it had only the room's era, and a span is not a date.
    claims, where = sweep.gather(per_scene, sweep.scene_years(scenes))

    if not claims:
        # A real outcome, and it costs nothing to say so. A draft of pure
        # dialogue asserts little about the world, and reporting that is not
        # the same as failing to read it.
        return {
            "run_id": run_id,
            "scenes_read": len(scenes),
            "scene_keys": _scene_keys(scenes),
            "claims_raised": raised,
            "claims": [],
            "search_count": 0,
            "budget_exhausted": False,
        }

    # Walked once and held, because the chain is needed twice: the verifier
    # reads its files, and the ledger that hydrates the verdicts has to hold
    # every source it was shown. Fetching it twice would also mean the two
    # could disagree if a room changed between them.
    documents = await _chain_documents(uid, run_id, document)
    run_ledger = SourceLedger()
    try:
        state = await asyncio.wait_for(
            _verify_claims(
                claims, _chain_files(documents), run_ledger, _draft_years(scenes)
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.warning("Sweep verification on %s exceeded %ss", run_id, timeout)
        raise HTTPException(
            504,
            f"The check ran past its {timeout}-second limit and was stopped. "
            "Sweep a shorter stretch of the draft.",
        ) from None
    except Exception:
        logger.exception("Sweep verification on room %s failed", run_id)
        raise HTTPException(
            502,
            "The department hit an unexpected problem partway through the "
            "draft. The details are in the server log.",
        ) from None

    searches = int(state.get("search_count") or 0)
    ceiling = config.max_searches_per_sweep()
    result = annotate(
        state.get("verdicts"),
        [Claim.model_validate(claim) for claim in claims],
        # THE WHOLE CHAIN, not this room alone. The verifier was handed
        # every room's files and may cite a url it only saw in the parent;
        # hydrating against one room finds it in neither ledger and
        # downgrades a correct answer to unverifiable.
        ledger_from_chain(document for _, document in documents),
        run_ledger,
        searches >= ceiling,
        scene_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        search_count=searches,
    )
    payload = jsonable_encoder(result)
    profile = (document_to_room(document).get("story_profile") or {})
    swept = {
        "run_id": run_id,
        "room": {
            "title": profile.get("title") or "Untitled room",
            "era": profile.get("era") or "",
        },
        "sweep_id": uuid.uuid4().hex[:12],
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "scenes_read": len(scenes),
        "scene_keys": _scene_keys(scenes),
        # Both numbers, because the difference between them is the one thing a
        # reader cannot work out for themselves and the whole reason a sweep
        # costs less than the same scenes one at a time.
        "claims_raised": raised,
        "claims": sweep.attach(payload.get("claims") or [], where),
        "search_count": searches,
        "budget_exhausted": bool(payload.get("budget_exhausted")),
        "cover_note": payload.get("cover_note") or "",
        "scope_note": payload.get("scope_note") or "",
        "unsourced_count": payload.get("unsourced_count") or 0,
        # Recounted here rather than carried over from `payload`. The claims on
        # this document went through `sweep.attach` after the verifier ran, so
        # the count has to be taken from the list actually filed — a number
        # copied off the pre-attach payload would describe a different list and
        # be right only by luck. Found the first time this ran live: the field
        # existed on the check payload, was never added here, and the sweep
        # door reported None while the browser had the flags all along.
        "unmatched_citations": 0,
    }
    swept["unmatched_citations"] = count_unmatched(swept["claims"])

    # Filed, so a reload does not throw away a whole draft's answers and the
    # searches that bought them. Best-effort and named rather than hidden, the
    # posture `_run_check` takes for the same write: the answer was decided
    # above and the caller is holding it, so a Firestore hiccup costs
    # durability rather than the result they just paid for.
    try:
        await asyncio.to_thread(
            _store.save_sweep,
            uid,
            run_id,
            swept["sweep_id"],
            sweep_to_document(swept, swept["sweep_id"], swept["created_at"]),
        )
    except Exception:
        logger.exception("Failed to file sweep %s on room %s", swept["sweep_id"], run_id)

    return swept


@app.get("/api/rooms/{run_id}/sweeps")
async def list_sweeps(run_id: str, authorization: str | None = Header(None)) -> dict:
    # An unknown room and another caller's room both answer with an empty list
    # rather than a 404, for the reason list_scenes does: the path is rooted at
    # `users/{uid}`, so there is nothing to find in either case and no read
    # that could tell the two apart.
    uid = _require_uid(authorization)
    return {"sweeps": await asyncio.to_thread(_store.list_sweeps, uid, run_id)}


@app.get("/api/rooms/{run_id}/sweeps/{sweep_id}.csv")
async def get_sweep_csv(
    run_id: str, sweep_id: str, authorization: str | None = Header(None)
) -> Response:
    """One filed sweep as a spreadsheet.

    Registered ABOVE the `{sweep_id}` route it looks like, because Starlette
    matches in declaration order and `sweep_id` would otherwise swallow
    `abc.csv` and 404 on a sweep whose id has no dot in it.

    `text/csv` with an attachment disposition, never `text/html`: this is a
    file a browser downloads, and a content type it might render is a content
    type it might execute.
    """
    uid = _require_uid(authorization)
    document = await asyncio.to_thread(_store.get_sweep, uid, run_id, sweep_id)
    if document is None:
        raise HTTPException(404, "Unknown sweep")

    room = (document.get("room") or {}).get("title") or "sweep"
    # The id in the name, because the import refuses a file from another sweep
    # by id and a reader holding three same-named downloads cannot tell which
    # one it is asking for.
    filename = exports.csv_filename(
        room, document.get("created_at"), unique=sweep_id
    )
    return Response(
        content=exports.sweep_to_csv(document),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Belt and braces on a download whose cells are a writer's own text
            # and pages off the open web.
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/rooms/{run_id}/sweeps/{sweep_id}")
async def get_sweep(
    run_id: str, sweep_id: str, authorization: str | None = Header(None)
) -> dict:
    """One filed sweep, in the shape the surface that ran it renders."""
    uid = _require_uid(authorization)
    document = await asyncio.to_thread(_store.get_sweep, uid, run_id, sweep_id)
    if document is None:
        raise HTTPException(404, "Unknown sweep")
    return {"run_id": run_id, **document_to_sweep(document)}


class AnnotationRequest(BaseModel):
    csv: str
    # Two calls, and the first one changes nothing. The same arming
    # `delete_room` uses and for the same reason: this writes into a filed
    # record, and a writer should see what a file will do before it does it.
    apply: bool = False


async def _wrong_sweep(uid: str, run_id: str, origin: str) -> str:
    """The refusal, in the words the sweep picker uses.

    THE READER HAS NEVER SEEN A SWEEP ID. The picker draws each filed sweep as
    "24 scenes · 64 claims · 13 AUG 2026 13:35" and an id appears on no surface
    of this app, so the first version of this message — "that file was exported
    from sweep 26881297a20d, open the sweep the file came from" — sent a writer
    to look for a string that is not written anywhere they can look. True,
    specific, and impossible to act on, which is the exact failure the message
    was written to fix.

    So the sweep is looked up and described the way the button describes it. If
    it is not filed on this room at all, say THAT instead: it is a different
    answer, and "open the one that says 24 scenes" would be a lie about a sweep
    that is not on the screen.
    """
    try:
        sweeps = await asyncio.to_thread(_store.list_sweeps, uid, run_id)
    except Exception:  # pragma: no cover - a listing failure is not the point
        logger.exception("Could not list sweeps while refusing an import")
        sweeps = []

    for summary in sweeps or []:
        if (summary or {}).get("sweep_id") != origin:
            continue
        # Built from the same three fields the button is, in the same order, so
        # the sentence and the thing it points at can be read side by side.
        scenes = int(summary.get("scenes_read") or 0)
        claims = int(summary.get("claim_count") or 0)
        stamp = str(summary.get("created_at") or "")[:16].replace("T", " ")
        described = " · ".join(
            part
            for part in (
                f"{scenes} scene{'' if scenes == 1 else 's'}",
                f"{claims} claim{'' if claims == 1 else 's'}",
                stamp,
            )
            if part
        )
        return (
            "That file came from a different sweep of this room — the one "
            f"listed as {described}. Open that sweep and import the file "
            "there, or export this one and mark that up instead. Nothing was "
            "changed."
        )

    return (
        "That file was exported from a sweep that is not filed on this room, "
        "so there is nothing here to file its notes against. Export this "
        "sweep and mark that up instead. Nothing was changed."
    )


@app.post("/api/rooms/{run_id}/sweeps/{sweep_id}/annotations")
async def annotate_sweep(
    run_id: str,
    sweep_id: str,
    req: AnnotationRequest,
    uid: Annotated[str, Depends(_uid)],
) -> dict:
    """Bring a writer's own marks back from a spreadsheet.

    ANNOTATION, NEVER EVIDENCE. A verdict, a source and an excerpt are the
    department's, hydrated out of a ledger; the one thing that must stay
    impossible is a room reading as better-sourced than its research made it.
    A row that edited one has that column ignored and is named in the report.

    A shell over `_file_notes`, which the agent door calls too. The work moved
    down there the day this stopped being reachable from a desktop agent — the
    same reason every other pair on this file shares one function.
    """
    return await _file_notes(uid, run_id, sweep_id, req.csv, bool(req.apply))


async def _file_notes(
    uid: str, run_id: str, sweep_id: str, csv_text: str, apply: bool
) -> dict:
    """Read a marked-up sweep export and, if asked, file its notes. Shared.

    Transport-free so the browser's route and the agent door's `import_notes`
    cannot drift. The browser had this to itself for a week, and everything it
    learned in that week — the origin refusal, the changes preview, the
    complaint that names a column rather than crying wolf — is here rather than
    in the route, so an agent gets the same answers a writer does.
    """
    if len(csv_text) > config.max_annotation_chars():
        raise HTTPException(
            400,
            f"That file is {len(csv_text)} characters and the ceiling is "
            f"{config.max_annotation_chars()}. Import the sweep's own export.",
        )

    document = await asyncio.to_thread(_store.get_sweep, uid, run_id, sweep_id)
    if document is None:
        raise HTTPException(404, "Unknown sweep")

    # THE FILE SAYS WHICH SWEEP IT CAME FROM, so ask before doing anything
    # else. A file from another sweep still parses, still matches whatever
    # claims the two happen to share, and reports every difference between them
    # as the writer's doing — eight unmatched claims and six "you edited a
    # citation" complaints on the run that found this, none of which named the
    # one thing that was wrong. Refused rather than reported, because the
    # alternative is filing half a file's notes onto a sweep the writer was not
    # looking at.
    origin = exports.annotation_origin(csv_text)
    if origin and origin != sweep_id:
        raise HTTPException(400, await _wrong_sweep(uid, run_id, origin))

    annotations, complaints = exports.read_annotations(csv_text)
    # Both lists, in the order they are raised: what the FILE was wrong about
    # (unreadable rows, no claim named), then what it tried to change. The
    # second can only be decided against the stored sweep, which is why it
    # comes back from apply rather than from read.
    updated, unmatched, edits = exports.apply_annotations(document, annotations)
    complaints = complaints + edits
    matched = len(annotations) - len(unmatched)

    if apply and matched:
        try:
            await asyncio.to_thread(_store.save_sweep, uid, run_id, sweep_id, updated)
        except Exception:
            logger.exception("Failed to save annotations on sweep %s", sweep_id)
            raise HTTPException(
                502,
                "The notes were read but could not be filed. Nothing was "
                "changed. Try again.",
            ) from None

    return {
        "applied": bool(apply and matched),
        "matched": matched,
        # Named rather than counted. Silence here would let a writer annotate
        # twenty claims, import, find nineteen, and have no way to learn which
        # one went missing.
        "unmatched": unmatched,
        "complaints": complaints,
        "changes": _annotation_changes(document, updated),
        "claims": updated.get("claims") or [],
    }


def _annotation_changes(before: dict, after: dict) -> list[dict]:
    """Claim by claim, what this import would write. Pure.

    "25 claims in this sweep would take a note" is a count, and a count is not
    a preview. A writer arming a write into their own filed record can read
    that sentence and still not know whether the notes are going where they
    meant, whether a line they struck last week is about to be un-struck, or
    whether a note they typed a fortnight ago is about to be replaced by one
    from a stale copy of the file. Same shape as every other defect on this
    surface this week: true, and not the thing.

    So the diff is computed here, where BOTH documents are in hand, rather than
    in the browser. The alternative is the app re-deriving what the server
    already knows from a payload that carries only the after-state, which is
    how a second implementation of one fact starts.

    `was` fields are present only when they differ, so a reader scanning the
    list sees a replacement standing out from a first note rather than having
    to compare two strings on every row.
    """
    stored = {
        str((claim or {}).get("text") or "").strip(): claim or {}
        for claim in before.get("claims") or []
    }

    changes: list[dict] = []
    for claim in after.get("claims") or []:
        claim = claim or {}
        text = str(claim.get("text") or "").strip()
        note = claim.get("writer_note") or ""
        struck = bool(claim.get("dismissed"))
        old = stored.get(text) or {}
        was_note = old.get("writer_note") or ""
        was_struck = bool(old.get("dismissed"))

        if note == was_note and struck == was_struck:
            continue

        change: dict = {"claim": text, "writer_note": note, "dismissed": struck}
        # Only when they moved. A `was_note` echoing the new note on every row
        # would bury the handful that are genuinely overwriting something.
        if was_note and was_note != note:
            change["was_note"] = was_note
        if was_struck != struck:
            change["was_dismissed"] = was_struck
        changes.append(change)

    return changes


@app.delete("/api/rooms/{run_id}/sweeps/{sweep_id}")
async def delete_sweep(
    run_id: str, sweep_id: str, authorization: str | None = Header(None)
) -> dict:
    """Remove one filed sweep, and with it every scene fragment it quoted.

    A sweep's claims are exact quotations from across a whole draft, so this is
    not one scene's pages but a sample of all of them. The retention promise
    the check panel makes about a pasted scene has to cover them.
    """
    uid = _require_uid(authorization)
    removed = await asyncio.to_thread(_store.delete_sweep, uid, run_id, sweep_id)
    if not removed:
        raise HTTPException(404, "Unknown sweep")
    return {"deleted": True, "sweep_id": sweep_id}


class SceneRequest(BaseModel):
    scene: str
    # An opaque label the browser computes so a draft it splits tomorrow knows
    # which scenes it already checked. Optional, and empty from the agent door,
    # which has no draft to compare against. See star/store.py on why the
    # client owns it and this side only keeps it.
    scene_key: str = ""


@app.post("/api/rooms/{run_id}/scenes")
async def create_scene(
    run_id: str, req: SceneRequest, uid: Annotated[str, Depends(_uid)]
) -> dict:
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
    # The rate limiter this endpoint used to lack is not here either, and that
    # is now deliberate: it lives inside `_run_check`, keyed on the account, so
    # the browser and the agent door are limited by one object rather than by
    # two that have to be kept in step. See the comment against
    # `_uid_limiter.check` there for the ceiling and why it sits where it does.
    return jsonable_encoder(await _run_check(uid, run_id, scene, req.scene_key.strip()[:64]))


class SweepScene(BaseModel):
    index: int = 0
    heading: str = ""
    text: str
    # The same opaque client-computed label a single check carries, and stored
    # under the same rule: web/fountain.js owns what it means and this side
    # owns nothing but keeping it. It is what lets the draft strip say a scene
    # was already swept — without it, a sweep that read all 24 scenes leaves
    # every one of them looking untouched the moment the page reloads.
    key: str = ""


class SweepRequest(BaseModel):
    scenes: list[SweepScene]


@app.post("/api/rooms/{run_id}/sweep")
async def create_sweep(
    run_id: str, req: SweepRequest, uid: Annotated[str, Depends(_uid)]
) -> dict:
    """Every claim a whole draft makes, checked against this room in one pass."""

    # The BROWSER splits the draft (web/fountain.js) and sends the scenes. No
    # Fountain parser lives on this side, deliberately: a second one would be a
    # second answer to "where does a scene begin", and the writer would be
    # picking scenes out of one list while the department checked another.
    return await _sweep_draft(
        uid,
        run_id,
        [
            {"index": s.index, "heading": s.heading, "text": s.text, "key": s.key}
            for s in req.scenes
        ],
    )


@app.get("/api/rooms/{run_id}/defence")
async def get_defence(
    run_id: str, fact: str = "", authorization: str | None = Header(None)
) -> dict:
    """One filed fact with everything behind it, for the printable card.

    The same `star/defence.py` the MCP `defend_claim` tool calls, so the sheet
    a writer prints and the card an agent returns cannot disagree about what
    the room says — which is the one disagreement that matters, since both are
    read by someone who is already sceptical.

    404 for a room this account cannot see, and the same 404 for a fact that is
    not in it: `_store.get` is rooted at `users/{uid}`, so another caller's
    room is not found rather than refused, and a fact this room never filed is
    the same kind of absence.
    """
    uid = _require_uid(authorization)
    fact = (fact or "").strip()
    if not fact:
        raise HTTPException(400, "Name the fact to defend.")

    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        raise HTTPException(404, "Unknown run")

    result = document_to_room(document)
    located = defence.locate(result, fact)
    if located is None:
        raise HTTPException(
            404,
            "No finding in this room says that. The department will not build "
            "a card around the nearest match — that would put real sources "
            "behind a claim the room never made. Check the wording against the "
            "room and try again.",
        )
    category, finding = located
    return defence.card(result, category, finding, run_id)


class QuestionRequest(BaseModel):
    question: str
    category: str


@app.post("/api/rooms/{run_id}/questions")
async def create_question(
    run_id: str, req: QuestionRequest, uid: Annotated[str, Depends(_uid)]
) -> dict:
    """Send one question back to the field and file the answer into this room."""
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Ask the department a question.")
    if len(question) > config.max_question_chars():
        raise HTTPException(
            400,
            f"Questions are capped at {config.max_question_chars()} characters "
            "— ask the department one thing, not a treatment.",
        )
    # Named by the caller rather than inferred, and refused rather than
    # defaulted. A wrong drawer is not a cosmetic error: the drawer is how a
    # writer finds a fact again, and `get_room` with a `category` narrows on
    # it, so a finding filed under the wrong one is filed where nobody will
    # look. Guessing would need a model call to do badly what the caller
    # already knows.
    try:
        category = Category(req.category)
    except ValueError:
        raise HTTPException(
            400,
            f"`{req.category}` is not a drawer in this department. The four "
            f"are: {', '.join(c.value for c in Category)}.",
        ) from None
    # No limiter here, for the reason create_scene has none: it lives inside
    # `_run_requisition`, keyed on the account, so the browser and the agent
    # door are bounded by one object rather than two kept in step.
    return await _run_requisition(uid, run_id, question, category)


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


@app.delete("/api/rooms/{run_id}")
async def delete_room(run_id: str, authorization: str | None = Header(None)) -> dict:
    """Take a room out of sight, keeping it recoverable for the window.

    A flag on the document, not the document, and that is the opposite call
    from `delete_scene` below on purpose. A scene is a writer's script pages
    and the promise above the paste box is that the text stops being kept, so
    it goes for good the moment they say so. A room is research that cost real
    money and several minutes, its loss is the expensive mistake rather than
    its retention, and nothing in this app promises a room stops existing the
    instant it leaves the rail. It leaves the rail immediately either way;
    what the window buys is the morning after.

    Returns when it purges, because a delete that will not say when it becomes
    permanent is asking the reader to trust a number nobody stated.
    """
    uid = _require_uid(authorization)
    when = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    if not await asyncio.to_thread(_store.soft_delete_room, uid, run_id, when):
        raise HTTPException(404, "Unknown run")
    return {
        "run_id": run_id,
        "deleted_at": when,
        "retention_days": config.room_retention_days(),
    }


@app.post("/api/rooms/{run_id}/restore")
async def restore_room(run_id: str, authorization: str | None = Header(None)) -> dict:
    """Put a deleted room back, if the window has not closed on it.

    404 covers three cases the store reports apart — no such room, never
    deleted, past the window — and collapses them here on purpose. The first is
    genuinely unknown; the other two are indistinguishable from unknown to
    anyone who should not learn which rooms exist under an account they cannot
    read, and the web app is the only caller, where the reader just saw the
    room in a list this endpoint's own answer built.
    """
    uid = _require_uid(authorization)
    if not await asyncio.to_thread(_store.restore_room, uid, run_id):
        raise HTTPException(404, "Unknown run")
    return {"run_id": run_id, "restored": True}


def _chain_would_close(rooms: list[dict], run_id: str, parent_id: str) -> bool:
    """Would making `parent_id` the parent of `run_id` create a loop?

    Walks up from the proposed parent. If the walk reaches `run_id`, the link
    would close a ring and the rail's grouping would never terminate. Bounded
    by the number of rooms as well as by reaching the top, because a ring that
    already exists in the data — written by an older build, or by a race
    between two edits — must not hang the request that is trying to fix it.
    """
    parents = {room["run_id"]: (room.get("continues") or "") for room in rooms}
    seen: set[str] = set()
    current = parent_id
    while current:
        if current == run_id:
            return True
        if current in seen:
            return False
        seen.add(current)
        current = parents.get(current) or ""
    return False


@app.patch("/api/rooms/{run_id}")
async def update_room(
    run_id: str,
    uid: Annotated[str, Depends(_uid)],
    body: dict | None = None,
) -> dict:
    """Rename a room, or say which room it follows. Both, or either.

    One endpoint for two edits because they are one act: a writer looking at a
    room deciding what it is and what it belongs to. Two endpoints would mean
    two round trips for one save and two places for the ownership rule to live.

    Absent keys are left alone; `title: ""` and `continues: ""` are meaningful
    and do the documented thing (restore the derived title, clear the link).
    That distinction is why `body` is read as a plain dict rather than a model
    with defaults — a default cannot tell "not mentioned" from "set to empty",
    and both edits here need to.

    The body was declared OPTIONAL to make authorization the first gate,
    which worked for an absent body and not for an unparseable one: `[1,2,3]`
    still 422'd before this function ran. The gate is a dependency now, solved
    before any body param is validated, so the optional default is ordinary
    convenience again rather than a load-bearing workaround. See `_uid`.

    tests/test_server.py's route audit caught the first version of this and
    could not see the second: it sends one body that satisfies every route at
    once, so it proves auth is REQUIRED and never that it runs FIRST.
    tests/test_api_auth_posture.py asks the other question.
    """
    body = body or {}

    if "title" in body:
        title = str(body.get("title") or "")
        if len(title) > config.max_room_title_chars():
            raise HTTPException(
                400,
                f"Room names are capped at {config.max_room_title_chars()} "
                "characters. Shorten it and save again.",
            )

    if "continues" in body:
        parent_id = str(body.get("continues") or "").strip()
        # One implementation, shared with the agent door. A second copy of the
        # three refusals is how the two doors come to disagree about what a
        # legal chain is.
        await _link_room(uid, run_id, parent_id)

    updated = {"run_id": run_id}
    if "title" in body:
        named = await asyncio.to_thread(_store.set_title, uid, run_id, title)
        if named is None:
            raise HTTPException(404, "Unknown run")
        # The name the room now carries, which is not always the name that was
        # sent: an empty one restores what intake called it. The browser prints
        # what comes back rather than what it typed, or a writer who cleared
        # the field would watch the rail disagree with the room.
        updated["title"] = named
    if "continues" in body:
        updated["continues"] = parent_id
    return updated


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
    req: TokenRequest, claims: Annotated[dict, Depends(_claims)]
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
    # Limits the browser has to agree with, served rather than duplicated. A
    # cap typed into JS to match one defined in Python is the same defect
    # web/consent.js shipped when it advertised "four calls" on the day a fifth
    # tool landed: two sources of truth, and only one of them ever moves.
    limits = {"roomTitleChars": config.max_room_title_chars()}
    return Response(
        f"export const FIREBASE = {json.dumps(payload)};\n"
        f"export const GOOGLE = {json.dumps(google)};\n"
        f"export const LIMITS = {json.dumps(limits)};",
        media_type="application/javascript",
    )


# --- The agent door ---------------------------------------------------------
#
# Included BEFORE the StaticFiles mount below, and that ordering is not style.
# The mount matches every path under `/`, so Starlette finds it first for any
# route registered after it: `/mcp` would come back as a 404 from the static
# handler, with nothing in the log to say the router existed. GET and DELETE on
# /mcp are registered explicitly by the router for the same reason — without
# them the mount would answer, and the 405 the transport spec requires would
# arrive as a 404 instead.
#
# Five callables and no state. Three of them are the same function objects the
# handlers above call, so the agent door cannot drift from the browser door
# without the drift being visible as a second function. spec.md's Decision 4
# argues why the dependencies move rather than the run registry.


# The agent door's build. A functools.partial rather than a wrapper function,
# so what the router holds reports `.func is _start_build` — "one budget, one
# ceiling, one kill switch" is then a fact a test can assert about the object
# graph rather than a claim a comment makes. Binding the gate here is also
# what keeps the router from having to know that a limiter exists at all.
_mcp_start_build = functools.partial(_start_build, gate=_uid_gate)


async def _resolve_mcp_token(authorization: str | None):
    """Turn the agent door's Authorization header into a uid, or a refusal.

    `tokens.resolve` takes its store explicitly rather than holding module
    state, so something has to supply `_token_store`. A function reading the
    module global at call time rather than a partial binding the instance at
    import time, and the difference is not cosmetic: every other route in this
    file reaches Firestore through a name the whole test suite already patches,
    and a partial would hold the one TokenStore nothing could stand in for.

    It is the same store `/api/tokens` writes through, which is what makes a
    token issued in the browser resolve here to the account that issued it —
    one ledger, two doors.
    """
    return await tokens.resolve(authorization, _token_store)


async def _mcp_delete_room(uid: str, run_id: str) -> dict | None:
    """The agent door's delete, on the same store call the browser door uses.

    Returns the room document when it soft-deleted one and None when there was
    nothing there, so the tool can report what it removed rather than only that
    it removed something. Reads before writing for that reason alone — the
    store's own answer is a bool.
    """
    document = await asyncio.to_thread(_store.get, uid, run_id)
    if document is None:
        return None
    when = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    if not await asyncio.to_thread(_store.soft_delete_room, uid, run_id, when):
        return None
    return {**document, "deleted_at": document.get("deleted_at") or when}


async def _mcp_run_requisition(
    uid: str, run_id: str, question: str, category: str
) -> dict:
    """The agent door's requisition, on the same runner the browser door uses.

    The category arrives as a string off the wire and is turned into a Category
    here rather than inside `_run_requisition`, which takes the enum: the
    schema's own `enum` already refused anything else before this ran, so the
    conversion cannot fail and a second refusal below it would be dead code
    pretending to be a guard.
    """
    return await _run_requisition(uid, run_id, question, Category(category))


async def _mcp_read_sweeps(uid: str, run_id: str) -> list[dict]:
    """The sweeps filed on one room, off the event loop like `list_rooms`.

    No 404 for a room this account cannot see, and none for one that does not
    exist: the path is rooted at `users/{uid}`, so both answer with an empty
    list by construction — the same no-oracle posture the browser's own
    `/scenes` route arrives at.
    """
    return await asyncio.to_thread(_store.list_sweeps, uid, run_id)


async def _mcp_read_sweep(uid: str, run_id: str, sweep_id: str) -> dict:
    document = await asyncio.to_thread(_store.get_sweep, uid, run_id, sweep_id)
    if document is None:
        raise HTTPException(404, "Unknown sweep")
    return {"run_id": run_id, **document_to_sweep(document)}


app.include_router(
    build_mcp_router(
        start_build=_mcp_start_build,
        read_room=_read_room,
        list_rooms_for=_list_rooms_for,
        run_check=_run_check,
        delete_room=_mcp_delete_room,
        run_requisition=_mcp_run_requisition,
        # The file half, and every one of these is the SAME transport-free
        # function the browser's own route calls. That is the whole point of
        # extracting them: an agent importing a room and a writer importing one
        # cannot end up with different rules about what an imported room is.
        run_sweep=_sweep_draft,
        read_sweeps=_mcp_read_sweeps,
        read_sweep=_mcp_read_sweep,
        export_room=_export,
        import_rooms=_import_rooms,
        file_notes=_file_notes,
        write_bible=_write_bible,
        link_room=_link_room,
        resolve_token=_resolve_mcp_token,
    )
)

# --- the authorization server ------------------------------------------------
#
# Everything below is the OAuth 2.1 surface an MCP client discovers, and every
# route in it MUST be declared above `app.mount("/")` for the reason the MCP
# router already is: the StaticFiles mount answers `/` and therefore swallows
# every path declared after it. A `/.well-known/` route registered below the
# mount is a 404 that looks like a missing feature.
#
# The department is both roles here. It is the resource server, which it has
# been since the MCP door opened, and now also the authorization server, which
# `spec-oauth-as.md` explains it has to be: the spec requires a token to be
# validated as issued FOR this resource, and Google will not mint one carrying
# this resource's URI as its audience. So Google stays what identifies the
# human, and the issuing is ours.

_code_store = codes.CodeStore(max_keys=config.max_authorization_codes())
_client_store = ClientStore()


@app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
async def oauth_protected_resource() -> dict:
    """RFC 9728. The document a client reads to find out who issues tokens.

    A MUST for an MCP server, and the reason the 401 challenge stopped being a
    bare `Bearer`: without this, a client that begins by asking where the
    authorization server is has nothing to follow and stops there.
    """
    return oauth_metadata.protected_resource()


@app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
async def oauth_authorization_server() -> dict:
    """RFC 8414. What this authorization server can actually do.

    `code_challenge_methods_supported` carries the weight here: the OAuth 2.1
    and PKCE specs define no way for a client to probe for PKCE support, so a
    conformant client MUST refuse to proceed when that field is absent. An
    otherwise perfect document without it is a document nobody can use.
    """
    return oauth_metadata.authorization_server()


class DecideRequest(BaseModel):
    state_key: str
    decision: str


def _oauth_redirect(target: str, **params: str) -> str:
    """Append parameters to a redirect URI without disturbing what it carries.

    A registered redirect URI may already have a query string of its own, so
    parameters are merged rather than concatenated, and `state` is echoed back
    exactly as it arrived — it is the client's own value and the client is the
    only thing that can read it.
    """
    parts = urlsplit(target)
    merged = dict(parse_qsl(parts.query, keep_blank_values=True))
    merged.update({k: v for k, v in params.items() if v is not None})
    return urlunsplit(parts._replace(query=urlencode(merged)))


# Pending authorizations: validated request parameters, waiting for a human.
#
# Separate from `_code_store` on purpose. That one holds a grant somebody has
# already agreed to; this one holds a question nobody has answered yet, and the
# two have different lifetimes and different consequences if they leak. A
# pending entry buys an attacker a consent screen they could have requested
# themselves; a code buys them a token.
#
# In memory, bounded, and swept, for the reason star/guards.py documents about
# every other piece of module state in this process. Same accepted cost: a
# restart between the redirect and the press drops the question and the client
# starts over.
_pending_authorizations: dict[str, dict] = {}
_PENDING_TTL_SECONDS = 600


def _sweep_pending(now: float) -> None:
    stale = [k for k, v in _pending_authorizations.items() if now - v["at"] > _PENDING_TTL_SECONDS]
    for key in stale:
        _pending_authorizations.pop(key, None)


@app.get("/oauth/authorize", include_in_schema=False)
async def oauth_authorize(request: Request) -> Response:
    """The hinge: a client's request becomes a question put to a human.

    ORDER IS THE SECURITY PROPERTY HERE, and it is the one thing in this file
    worth reading twice. The client and its redirect URI are validated FIRST,
    and a failure at that step renders an error rather than redirecting. Every
    later failure may redirect, because by then the destination has been proved
    to belong to the client that registered it.

    Redirecting an unvalidated `redirect_uri` is how authorization codes are
    stolen: an attacker names a client that exists, points the redirect at
    themselves, and the server hands the code to whoever asked. That is why the
    two branches below are not symmetric, and why the asymmetry is deliberate
    rather than an oversight in error handling.

    No uid is bound here. The reader is identified when they answer, not when
    they arrive, so a link someone was tricked into opening cannot pre-bind a
    grant to whoever happens to be signed in.
    """
    q = request.query_params

    client = await clients.lookup(q.get("client_id"), _client_store)
    if isinstance(client, clients.Rejected):
        return _oauth_error_page("This client is not registered with the department.")
    if not clients.redirect_allowed(client, q.get("redirect_uri")):
        return _oauth_error_page(
            "That return address is not one this client registered. The "
            "department will not send an answer there."
        )

    redirect_uri = q.get("redirect_uri")
    state = q.get("state") or ""

    def _refuse(error: str, description: str) -> Response:
        return RedirectResponse(
            _oauth_redirect(redirect_uri, error=error, error_description=description, state=state),
            status_code=303,
        )

    if q.get("response_type") != "code":
        return _refuse("unsupported_response_type", "This server issues authorization codes.")
    if q.get("code_challenge_method") != "S256":
        return _refuse("invalid_request", "PKCE with S256 is required.")
    if not pkce.is_valid_challenge(q.get("code_challenge")):
        return _refuse("invalid_request", "That code_challenge is not a valid S256 challenge.")
    if not oauth_metadata.accepts_resource(q.get("resource")):
        return _refuse("invalid_target", "This server issues tokens for its own resource only.")

    granted = oauth_validate.requested_scope(q.get("scope"), client.scope)
    if granted is None:
        return _refuse("invalid_scope", "That scope is not one this client may be granted.")

    now = time.time()
    _sweep_pending(now)
    if len(_pending_authorizations) >= config.max_authorization_codes():
        return _refuse("temporarily_unavailable", "The department is busy. Try again.")

    state_key = secrets.token_urlsafe(24)
    _pending_authorizations[state_key] = {
        "at": now,
        "client_id": client.client_id,
        "client_name": client.client_name or "",
        "client_uri": getattr(client, "client_uri", "") or "",
        "redirect_uri": redirect_uri,
        "scope": granted,
        "code_challenge": q.get("code_challenge"),
        "state": state,
    }

    return RedirectResponse(
        "/consent.html?"
        + urlencode(
            {
                "client_name": client.client_name or client.client_id,
                "client_uri": getattr(client, "client_uri", "") or "",
                "redirect_host": urlsplit(redirect_uri).hostname or "",
                "scope": granted,
                "state_key": state_key,
            }
        ),
        status_code=303,
    )


@app.post("/oauth/authorize/decide", include_in_schema=False)
async def oauth_decide(
    req: DecideRequest, authorization: str | None = Header(None)
) -> dict:
    """The human answers, and only now is a uid attached to anything.

    `_require_uid` is what makes the answer somebody's. The `state_key` proves
    the question is real; the ID token proves who is answering it. Neither
    alone is enough, which is why this route asks for both.
    """
    uid = _require_uid(authorization)

    now = time.time()
    _sweep_pending(now)
    pending = _pending_authorizations.pop(req.state_key, None)
    if pending is None:
        raise HTTPException(
            400,
            "That request has expired or was already answered. Start the "
            "connection again from your client.",
        )

    if req.decision != "approve":
        return {
            "redirect_to": _oauth_redirect(
                pending["redirect_uri"],
                error="access_denied",
                error_description="The reader declined.",
                state=pending["state"],
            )
        }

    code = _code_store.issue(
        codes.Grant(
            uid=uid,
            client_id=pending["client_id"],
            redirect_uri=pending["redirect_uri"],
            scope=pending["scope"],
            code_challenge=pending["code_challenge"],
            resource=oauth_metadata.resource(),
        )
    )
    if code is None:
        raise HTTPException(503, "The department could not issue a code just now.")

    return {
        "redirect_to": _oauth_redirect(
            pending["redirect_uri"], code=code, state=pending["state"]
        )
    }


def _oauth_error_page(message: str) -> Response:
    """A dead end that says why, rather than a redirect that leaks a code.

    Reached only when the client or its redirect URI failed validation, which
    is exactly when there is no address the department is willing to send an
    answer to.
    """
    return Response(
        f"<!doctype html><meta charset=utf-8>"
        f"<title>STAR</title>"
        f"<body style='background:#232B27;color:#D2B98C;font:16px/1.6 system-ui;"
        f"padding:3rem;max-width:34rem'>"
        f"<h1 style='font-size:1.2rem'>The department cannot take this request</h1>"
        f"<p>{html.escape(message)}</p></body>",
        media_type="text/html",
        status_code=400,
    )


@app.post("/oauth/register", include_in_schema=False)
async def oauth_register(request: Request) -> Response:
    """RFC 7591 dynamic client registration.

    One of three registration paths the spec allows, and the one a client falls
    back to when it cannot host a Client ID Metadata Document. Both are
    supported because which one a given client reaches for is not worth
    guessing at, and building both cost less than measuring and being wrong.
    """
    try:
        document = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            {"error": "invalid_client_metadata",
             "error_description": "The registration body was not JSON."},
            status_code=400,
        )

    now = datetime.now(timezone.utc)  # noqa: UP017
    client = clients.register(document, now)
    if isinstance(client, clients.Rejected):
        return JSONResponse(
            {"error": client.error, "error_description": client.description},
            status_code=400,
        )

    await asyncio.to_thread(_client_store.save, client.client_id, clients.to_document(client))
    return JSONResponse(
        clients.registration_response(client, int(now.timestamp())), status_code=201
    )


@app.post("/oauth/token", include_in_schema=False)
async def oauth_token(request: Request) -> Response:
    """The token endpoint. Form-encoded, per OAuth 2.1.

    `Cache-Control: no-store` is required rather than polite: the body carries
    a bearer credential, and a proxy or a browser that caches it hands the next
    reader an access token.
    """
    form = await request.form()
    grant_type = form.get("grant_type")

    if grant_type == "authorization_code":
        issued = await oauth_tokens.exchange_code(
            code=form.get("code"),
            client_id=form.get("client_id"),
            redirect_uri=form.get("redirect_uri"),
            verifier=form.get("code_verifier"),
            resource=form.get("resource"),
            code_store=_code_store,
            store=_token_store,
        )
    elif grant_type == "refresh_token":
        issued = await oauth_tokens.refresh(
            refresh_token=form.get("refresh_token"),
            client_id=form.get("client_id"),
            store=_token_store,
        )
    else:
        return JSONResponse(
            {"error": "unsupported_grant_type",
             "error_description": "This server issues tokens for "
                                  "`authorization_code` and `refresh_token`."},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )

    if isinstance(issued, oauth_tokens.Denied):
        return JSONResponse(
            {"error": issued.error, "error_description": issued.description},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(issued.body(), headers={"Cache-Control": "no-store"})


# Pin the icon's content type before the static mount reads it.
#
# StaticFiles asks `mimetypes` what a suffix is, and `mimetypes` asks the host.
# On this Windows machine `.ico` came back `image/x-icon`; in the Linux
# container it came back `image/vnd.microsoft.icon`. Both are real registrations
# for the same format, which is exactly what makes it a trap: the MCP handshake
# DECLARES a mimeType for each icon, so the same service would tell a client one
# thing locally and another in production, and a client that keys on the value
# would be right to distrust whichever it saw second.
#
# Caught by a test that fetched every icon the handshake names and compared what
# came back against what was claimed, which is the only version of that check
# worth having.
mimetypes.add_type("image/vnd.microsoft.icon", ".ico")

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
