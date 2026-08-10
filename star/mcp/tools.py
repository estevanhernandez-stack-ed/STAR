"""What the department tells an agent it can do, and where a call lands.

An agent cannot see a screen, so on this surface the strings ARE the product.
The four descriptions below and every refusal they can produce are the whole
interface, and `scope.md` puts the standard plainly: a persona that cannot
tell why a call failed is a test that produced nothing. Three rules follow,
and they are why this file is mostly prose.

  · Every refusal names what failed, why, and what to do next. A bare status
    code fails. A bare "invalid request" fails. "Room not found" on its own
    fails, because it does not say how to get an id that works.
  · Every description names what a call COSTS before it is made: money, rate
    limit, and time. That is what a person reads off a screen and an agent
    has no way to find out.
  · `build_room` returns before its work is done, so its description says what
    to do while waiting. Leave that out and an agent either hammers the poll
    or holds a connection open for nothing.

Two copy rules bind here as on every other surface. Never the bare word
"verified" about a source: what the department can say is which ledger a
citation came out of, and it says that. And never a promise about how long
something takes — "several minutes" and "poll about every 15 seconds" are
honest, a number of seconds is not (obligation 6).

`Calls` is the seam. star/server.py hands it four function objects, and three
of the four are the same objects its own HTTP handlers call, so "one
department, two doors" is a property of the wiring rather than a claim a
comment makes. spec.md's Decision 4 argues why the dependencies move to the
router instead of the run registry moving to a service module.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from star import config

# How often an agent should poll `get_room`. Named in the tool descriptions,
# in INSTRUCTIONS, and in the still-building answer itself, because an agent
# left to guess picks either "immediately, forever" or "once, in five
# minutes". Fifteen seconds against a build that runs 146s to 420s+ is roughly
# twenty polls: cheap for a read that costs one Firestore call, and fine
# enough that the terminal status is never more than a few seconds stale.
POLL_SECONDS = 15

# The treatment floor, and the one number in this file that is written down in
# two places. star/server.py:693 is the authority — `_start_build` raises on
# it and this module refuses ahead of it only so the message can name the
# floor and say what a treatment needs to contain. tests/test_mcp_protocol.py
# pins the two together by driving the real `_start_build` at this exact
# length, so a drift fails a test rather than shipping a refusal that names a
# number the server does not enforce.
MIN_TREATMENT_CHARS = 40

# Read once, at import, and put into the descriptions an agent reads at
# `tools/list`. star/server.py already reads config at import time for
# `_ip_limiter`'s ceiling, so this is the file's existing posture rather than
# a new one. Every *refusal* below re-reads config at call time, which is the
# half that has to be live: a description naming a stale cap is a cosmetic
# wrong, a refusal naming one is a lie about what just happened.
_MAX_TREATMENT = config.max_treatment_chars()
_MAX_SCENE = config.max_scene_chars()
_MAX_SEARCHES_PER_BUILD = config.max_searches_per_build()
_MAX_SEARCHES_PER_CHECK = config.max_searches_per_check()


# What a client is told about the department at `initialize`, before it has
# read a single tool description. Deliberately about the shape of the work
# rather than about the tools: a build is slow and polled, a citation is only
# ever a source a search actually returned, and a checked scene is kept.
#
# It carries the three facts spec.md names — minutes-and-a-run_id, citations
# hydrated from what search returned, a scene stored with its room — plus the
# one an agent cannot infer from any single description: which calls spend
# money and which are free.
INSTRUCTIONS = (
    "STAR is a research department for screenwriters, and this connection is "
    "one writer's account. The rooms you can read here are the same rooms "
    "they see in the web app, filed under the same identity.\n\n"
    "A room is a body of research built from a treatment. The department "
    "reads the treatment, writes a research plan, runs live web searches "
    "across four categories (setting, objects and props, logistics, forces "
    "and conflicts), and files what comes back as findings, each one carrying "
    "the sources behind it, plus a research bible.\n\n"
    "There are four tools and no fifth. `list_rooms` and `get_room` read; "
    "`build_room` and `check_scene` spend.\n\n"
    "Building a room takes several minutes, so `build_room` hands back a "
    "`run_id` straight away instead of holding the connection open. Poll "
    f"`get_room` with that id about every {POLL_SECONDS} seconds until the "
    "status is no longer `running`. A room still being built answers "
    "`running`; that is an answer, not an error, and nothing blocks.\n\n"
    "Two things about what comes back are worth knowing before you read one. "
    "Every citation is hydrated on the server from what a live web search "
    "actually returned, so a source printed under a finding is one the "
    "department saw; a cited URL that appears in no search result is stamped "
    "unsourced and left in view rather than quietly dropped. And a scene sent "
    "to `check_scene` is stored with its room until someone deletes it from "
    "the web app.\n\n"
    "Reading costs nothing and is never rate-limited. A build and a check "
    "both spend real money on live web searches, and both count against "
    "limits: an hourly ceiling on this account, and a daily budget the whole "
    "department shares. A refusal always says which one turned you away."
)


@dataclass(frozen=True)
class Calls:
    """The four things a tool is allowed to do, injected by star/server.py.

    Frozen because the router holds one of these for the life of the process
    and nothing should be able to swap a callable out from under an in-flight
    request. Typed loosely on purpose: these are the server's own functions,
    their real signatures live at their definitions, and restating them here
    would be a second place to keep in step.
    """

    start_build: Callable[..., Any]
    read_room: Callable[..., Any]
    list_rooms_for: Callable[..., Any]
    run_check: Callable[..., Any]


# --- The strings a refusal is made of ---------------------------------------
#
# Constants and small builders rather than literals at the raise site, for the
# reason star/tokens.py's three Refusals are constants: "these eleven messages
# are all different from each other" is a property a test asserts directly,
# and it cannot assert it against strings buried in four functions.
#
# spec.md's error table has eleven rows. Three of them belong to
# star/tokens.py (no token, unrecognised token, revoked token) and are refused
# by the router before a tool is ever reached. Two are the server's own
# sentences and pass through untouched (the per-account hourly ceiling, the
# shared daily budget). Two are answers rather than errors and live below as
# room reports (still building, interrupted). The remaining four are here.

ROOM_NOT_FOUND = (
    "No room with that id is filed under this account. Call `list_rooms` for "
    "the ids you can read, or `build_room` to start a new room. A room filed "
    "under somebody else's account answers exactly this way, so this does not "
    "tell you whether the id exists at all."
)

# The half of a refusal that only a caller with no screen needs. A browser
# carries both of these in pixels: the rail keeps listing rooms while a build
# is being refused, and a live timeline shows when a room is ready. An agent
# gets one sentence and nothing else.
#
# Appended on the strength of what the sentence already says rather than on
# which refusal it is, and that is the deliberate shape. The tool layer cannot
# tell the hourly ceiling from the shared daily budget without reaching into
# star/server.py, and it does not need to: the question that decides the
# append is "was the caller told?", which the sentence itself answers. If the
# server's wording drifts, the worst case is one extra true sentence.
READS_ARE_FREE = (
    "Reading is not affected: `list_rooms` and `get_room` cost nothing and "
    "are never limited."
)

WAIT_FOR_THE_ROOM = (
    f"Poll `get_room` with the same `run_id` about every {POLL_SECONDS} "
    "seconds, and check the scene once the status is no longer `running`."
)


def treatment_too_short(sent: int) -> str:
    """A treatment the department cannot plan from, and what would fix it."""
    return (
        f"That treatment is {sent} characters and the department needs at "
        f"least {MIN_TREATMENT_CHARS} to plan any research from it. Send a "
        "few sentences of prose that say three things: when the story is set, "
        "where it happens, and what the characters actually do. Those three "
        "are what the research plan is built out of, and a one-line premise "
        "gives the planner nothing to ask a question about."
    )


def treatment_too_long(sent: int, cap: int) -> str:
    return (
        f"That treatment is {sent} characters and treatments are capped at "
        f"{cap}. Send the department a treatment, not the script: the era, "
        "the places, the people, and what happens. Trim it and call "
        "`build_room` again. Nothing was spent, and no room was started."
    )


def scene_too_long(sent: int, cap: int) -> str:
    return (
        f"That scene is {sent} characters and scenes are capped at {cap}. "
        "Check one scene at a time rather than a whole act, then call "
        "`check_scene` again with the shorter text. Nothing was spent, and "
        "nothing was stored."
    )


STILL_BUILDING = (
    "This room is still being built. The department is researching and has "
    "filed nothing yet, so there is nothing to read here. Call `get_room` "
    f"with the same `run_id` again in about {POLL_SECONDS} seconds. The "
    "status changes to `complete`, `partial`, `error`, or `interrupted` when "
    "the build stops, and only then is there a room to read. This is an "
    "answer, not an error, and no call blocks waiting for it."
)


# --- The four tools ---------------------------------------------------------
#
# Descriptions are written for a reader with no screen: what it does, what it
# needs, what it returns, what it costs. Each is longer than a tool
# description usually is, which is the point — this text is the only
# documentation this surface has, and the alternative to spending tokens here
# is spending an agent's calls on discovering the same facts by failing.
#
# Each argument's `description` is a noun phrase on purpose. It is printed in
# `tools/list`, and it is also dropped into the sentence an agent gets back
# when it omits that argument or sends the wrong type — so the description an
# agent reads and the refusal it is handed cannot disagree with each other.

_ROOM_ID = (
    "the id of a room filed under this account, as returned by `list_rooms` "
    "or by `build_room`"
)

TOOLS: tuple[dict, ...] = (
    {
        "name": "list_rooms",
        "description": (
            "List every research room filed under this account, newest "
            "first.\n\n"
            "Takes no arguments. Returns one entry per room: `run_id`, which "
            "is the id every other tool takes, plus `title`, `era`, `status`, "
            "`created_at`, and `search_count`, the number of live web "
            "searches that room cost to build. It does not return the "
            "research itself; call `get_room` with a `run_id` for that.\n\n"
            "Costs nothing, spends no searches, and is never rate-limited. "
            "Start here when you do not already hold a room id. An account "
            "with no rooms yet is a normal answer and not an error."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_room",
        "description": (
            "Read one filed room, and poll a build that is still running. "
            "This tool is both: there is no separate status tool, and "
            "`build_room`'s reply is polled here.\n\n"
            f"Needs `run_id`, {_ROOM_ID}.\n\n"
            "Returns a `status` and the room. The status is one of:\n"
            "- `running`: the build is still going and nothing is filed yet. "
            f"Call this again in about {POLL_SECONDS} seconds. It is not an "
            "error and it does not block.\n"
            "- `complete`: the build finished. The room carries the story "
            "profile, the research plan, four category drawers of findings "
            "with the sources behind them, and the research bible.\n"
            "- `partial`: the build stopped early and the department kept "
            "what the researchers had already filed. The bible may be missing "
            "or short. Nothing more will be added.\n"
            "- `error`: the build failed. Whatever it filed before failing is "
            "returned, and often that is nothing.\n"
            "- `interrupted`: the department restarted while the build was "
            "running, so it stopped where it was and will never finish. What "
            "it filed before the restart is readable and will not change.\n\n"
            "Costs nothing, spends no searches, and is never rate-limited, so "
            "polling it is free. A room filed under a different account "
            "answers the same way as one that does not exist."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": _ROOM_ID}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "build_room",
        "description": (
            "Start a new research room from a treatment, and come straight "
            "back with the `run_id` that names it.\n\n"
            "Needs `treatment`: prose describing the story, between "
            f"{MIN_TREATMENT_CHARS} and {_MAX_TREATMENT} characters. Say when "
            "it is set, where it happens, and what the characters do. The "
            "department reads it, writes a research plan, and runs live web "
            "searches across setting, objects and props, logistics, and "
            "forces and conflicts.\n\n"
            "Returns a `run_id` and no research: nothing is filed at the "
            "moment this comes back. The build takes several "
            "minutes and this call does not wait for it: poll `get_room` with "
            f"that `run_id` about every {POLL_SECONDS} seconds until the "
            "status is no longer `running`. There is no notification and no "
            "stream to subscribe to.\n\n"
            "What it costs: real money, in live web searches, up to "
            f"{_MAX_SEARCHES_PER_BUILD} of them for one room, plus several "
            "model calls. It counts against this account's hourly build "
            "ceiling and against the daily budget the whole department "
            "shares, and either of those can refuse it before anything is "
            "spent. Reading rooms costs nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "treatment": {
                    "type": "string",
                    "description": (
                        "a prose treatment of the story, between "
                        f"{MIN_TREATMENT_CHARS} and {_MAX_TREATMENT} "
                        "characters, saying when and where it is set and what "
                        "the characters do"
                    ),
                }
            },
            "required": ["treatment"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_scene",
        "description": (
            "Check a scene's claims about the real world against a room that "
            "has already been built.\n\n"
            f"Needs `run_id`, {_ROOM_ID}, and `scene`, the scene text, up to "
            f"{_MAX_SCENE} characters. The room has to have finished "
            "building; a room still in progress is refused rather than "
            "checked against nothing.\n\n"
            "The department pulls out every claim the scene makes about the "
            "world rather than about the story (\"she drives a '61 Impala\" "
            "is a claim, \"she is afraid\" is not), answers each one from the "
            "room's own filed sources first, and spends a live web search "
            "only for what those sources do not answer. Each claim comes back "
            "with the exact text it was taken from, a verdict of `confirmed`, "
            "`anachronism`, or `unverifiable`, the sources behind that "
            "verdict with their excerpts, and whether the room's files or a "
            "fresh search produced each source. A claim whose cited URL is in "
            "neither is returned stamped unsourced rather than dropped, and a "
            "scene that asserts nothing about the world comes back with no "
            "claims, which is a result.\n\n"
            "The scene text is stored with the room and stays there until it "
            "is deleted. Deleting it is done from the room's script-check "
            "panel in the web app; there is no tool here that removes it.\n\n"
            "What it costs: unlike `build_room` this answers in the same "
            "call, so it holds the connection while it runs, which is under a "
            "wall-clock ceiling and can time out on a long scene. It spends "
            f"up to {_MAX_SEARCHES_PER_CHECK} live web searches and counts "
            "against this account's hourly check ceiling, which is separate "
            "from the build ceiling."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": _ROOM_ID},
                "scene": {
                    "type": "string",
                    "description": (
                        "the scene text to check, as it is written, up to "
                        f"{_MAX_SCENE} characters"
                    ),
                },
            },
            "required": ["run_id", "scene"],
            "additionalProperties": False,
        },
    },
)

_TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def text_result(text: str, *, is_error: bool = False) -> dict:
    """One `CallToolResult`, which is how a tool reports both outcomes.

    A tool-level failure is `isError: true` with the reason in the content,
    never a JSON-RPC error object. The distinction is who the message is for:
    a JSON-RPC error says the client is broken and a model cannot act on it,
    while this reaches the calling model as text it can read and respond to.
    """
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _payload(text: str, value: object) -> dict:
    """A plain-language line, then the JSON the line is about.

    The order is the whole point. A model reading this top-down knows what it
    is looking at and what to do next before it reaches the data, and a model
    that only parses the JSON loses nothing.

    Not indented. `spec.md > Open issues` #5 already flags room payloads as
    possibly too large for this door — bibles have run 11,000 to 17,000
    characters — and pretty-printing would add roughly a fifth to a number
    item 12 is supposed to measure honestly.
    """
    return text_result(f"{text}\n\n{json.dumps(value, ensure_ascii=False)}")


def _jsonable(value: object) -> object:
    """A tool's return value as JSON, whether or not it is a Pydantic model.

    Duck-typed rather than importing ScriptCheckResult, because `Calls` is
    typed loosely on purpose: a test that injects a callable returning a plain
    dict is exercising this dispatcher, and it should not have to construct a
    model to do it.
    """
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else value


# --- Arguments --------------------------------------------------------------


class _BadArguments(Exception):
    """A call this tool will not attempt, and the sentence explaining why.

    Raised rather than returned so a runner reads as the happy path, and
    caught once in `call` alongside HTTPException — the two ways a tool
    declines are then translated in one place instead of four.
    """


def _kind(value: object) -> str:
    """What arrived, in words, for a message that has to name it."""
    if isinstance(value, bool):
        return "a true/false value"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, dict):
        return "a JSON object"
    if isinstance(value, list):
        return "an array"
    return "a null"


def _accepted(properties: dict) -> str:
    names = [f"`{name}`" for name in properties]
    if not names:
        return "no arguments at all"
    if len(names) == 1:
        return f"one argument, {names[0]}"
    return "arguments " + ", ".join(names[:-1]) + f" and {names[-1]}"


def _arguments(tool: dict, arguments: dict) -> dict:
    """Check one call's arguments against the schema the agent was shown.

    Driven off `inputSchema` rather than written out per tool, so the shape an
    agent reads in `tools/list` and the shape it is held to are the same
    object. A hand-written check is a second copy, and a second copy is how a
    tool ends up refusing an argument its own description asked for.

    Unknown keys are refused rather than ignored, which is the deliberate
    call. Ignoring them is friendlier to a client that sends noise and much
    worse for the case that actually happens: an agent sends `roomId`, the
    tool silently sees no `run_id`, and the refusal it gets back talks about a
    missing argument it is certain it supplied. Naming the key it sent and the
    keys this tool takes is the difference between one wasted call and a loop.
    """
    name = tool["name"]
    properties = tool["inputSchema"].get("properties") or {}
    required = tool["inputSchema"].get("required") or []

    for key in arguments:
        if key not in properties:
            raise _BadArguments(
                f"`{name}` does not take an argument called `{key}`. It takes "
                f"{_accepted(properties)}. Call `tools/list` to see what each "
                "one is for."
            )

    values = {}
    for key in required:
        description = properties[key]["description"]
        value = arguments.get(key)
        if value is None:
            raise _BadArguments(
                f"`{name}` needs `{key}`: {description}. This call did not "
                f"send it. Call `tools/list` for the full argument list."
            )
        if not isinstance(value, str):
            raise _BadArguments(
                f"`{name}`'s `{key}` must be a string. This call sent "
                f"{_kind(value)}. It should be {description}."
            )
        if not value.strip():
            raise _BadArguments(
                f"`{name}`'s `{key}` arrived empty. Send {description}."
            )
        values[key] = value.strip()
    return values


# --- Reading a room ---------------------------------------------------------


def _filed_anything(result: object) -> bool:
    """Did this room actually get research into a drawer?

    Read off the payload rather than off the status, because the two are not
    the same question and this file has to answer honestly on a surface with
    no screen to soften it. A build persists its document the moment it
    starts, so an `interrupted` or `error` room usually carries the shape of a
    room with nothing in it — and telling an agent "what it filed is below"
    when nothing is below sends it to read an empty payload.
    """
    categories = (result or {}).get("categories") or {}
    if not isinstance(categories, dict):
        return False
    return any((doc or {}).get("findings") for doc in categories.values())


def _room_report(status: str, result: object) -> str:
    """The line that goes above a room, chosen by what actually came back.

    `interrupted` is reported as itself here and in the payload below it, and
    never folded into a failure. A run that died with its process is a real,
    distinct outcome: nothing is coming, the findings it did file are still
    good, and an agent told "error" instead would reasonably retry the same
    read waiting for it to resolve.
    """
    filed = _filed_anything(result)
    if status == "running":
        return STILL_BUILDING
    if status == "complete":
        return (
            "This room is filed and complete: the story profile, the research "
            "plan, four category drawers of findings with the sources behind "
            "them, and the research bible."
        )
    if status == "partial":
        return (
            "This build stopped before it finished, and the department kept "
            "what the researchers had already filed. The findings below are "
            "real and carry their sources; the research bible may be missing "
            "or short. Nothing more will be added to this room, so there is "
            "no reason to poll it again."
        )
    if status == "error":
        if filed:
            return (
                "This build failed partway through. What the researchers had "
                "filed before it failed is below and carries its sources. "
                "Nothing more will be added, so there is no reason to poll "
                "this room again. Start another with `build_room` if you need "
                "the rest."
            )
        return (
            "This build failed and filed nothing, so the room below is empty. "
            "Nothing more will be added and polling it again will not change "
            "that. Start another with `build_room`; a shorter, more specific "
            "treatment usually gets further."
        )
    if status == "interrupted":
        kept = (
            "What it filed before the restart is below and will not change."
            if filed
            else "It had filed nothing by then, so the room below is empty."
        )
        return (
            "This build was interrupted: the department restarted while it "
            "was running, so it stopped where it was and will never finish. "
            f"{kept} Polling it again will not change that. It is reported as "
            "`interrupted` rather than as an error because the research did "
            "not fail, it was cut off. Start another with `build_room` if you "
            "still need it."
        )
    # A status this file has no sentence for. Say that, rather than picking
    # the nearest one — a wrong description of an unfamiliar state is worse
    # than an honest "I do not know what this is" with the payload attached.
    return (
        f"This room came back with the status `{status}`, which this tool has "
        "no description for. The payload is below exactly as the department "
        "filed it."
    )


# --- The four runners -------------------------------------------------------


async def _list_rooms(arguments: dict, calls: Calls, identity) -> dict:
    _arguments(_TOOLS_BY_NAME["list_rooms"], arguments)
    rooms = await calls.list_rooms_for(identity.uid)
    if not rooms:
        # An empty account is the first thing a fresh agent sees, and an empty
        # JSON array tells it nothing about whether it is looking at the wrong
        # account, a broken call, or a writer who has not started yet.
        return text_result(
            "No rooms are filed under this account yet. That is not an error: "
            "the account is real and the token works, there is just nothing "
            "in it. Call `build_room` with a treatment to start the first "
            "one."
        )
    count = len(rooms)
    return _payload(
        f"{count} room{'' if count == 1 else 's'} filed under this account, "
        "newest first. Use a `run_id` from this list with `get_room` to read "
        "one, or with `check_scene` to check a scene against it.",
        {"rooms": rooms},
    )


async def _get_room(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["get_room"], arguments)
    run_id = values["run_id"]
    room = await calls.read_room(identity.uid, run_id)
    status = room.get("status") or "unknown"
    result = room.get("result")
    return _payload(
        _room_report(status, result),
        {"run_id": run_id, "status": status, "room": result},
    )


async def _build_room(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["build_room"], arguments)
    treatment = values["treatment"]

    # Refused here, ahead of `_start_build`, only so the message can name the
    # floor and the cap and say what a treatment needs to contain. The server
    # still enforces both — it is the authority and this is not a substitute
    # for it — but its sentences are the browser's, written for a reader who
    # has a character counter under the box and cannot see this one.
    if len(treatment) < MIN_TREATMENT_CHARS:
        raise _BadArguments(treatment_too_short(len(treatment)))
    cap = config.max_treatment_chars()
    if len(treatment) > cap:
        raise _BadArguments(treatment_too_long(len(treatment), cap))

    started = await calls.start_build(identity.uid, treatment)
    run_id = started.get("run_id")
    # `stream_key` is deliberately not returned. It is the capability that
    # guards a run's SSE stream, and this door has no stream to guard: GET
    # /mcp is a 405 by design. Handing an agent a secret it cannot use, for a
    # channel it cannot open, is exposure bought for nothing.
    return _payload(
        "The build has started and this account's daily and hourly budgets "
        "have been charged for it. Nothing is filed yet: the department is "
        f"planning and searching, which takes several minutes. Call "
        f"`get_room` with this `run_id` about every {POLL_SECONDS} seconds "
        "until the status is no longer `running`.",
        {"run_id": run_id, "status": "running"},
    )


_VERDICTS = ("confirmed", "anachronism", "unverifiable")


def _provenance(claims: list[dict]) -> str:
    """Which of the two answered, in the prose rather than only in the JSON.

    `citation_sources` already carries this per citation, and on the browser's
    side of the department a rail shows it next to every source. An agent gets
    a paragraph, and the payload design here is explicit that a model reading
    top-down should know what it is looking at before it reaches the data — so
    a fact that lives only in the data is a fact half the readers of this
    surface will not have.

    Added because a persona run found the case that makes it matter. A scene
    from a different story checked against a room that knows nothing about it
    comes back four-for-four `confirmed`, because the verifier falls through to
    a fresh search and answers correctly about the world. Nothing was wrong and
    the answer was worthless: the room is what supplies the era, so with the
    room contributing nothing, a phone released in 1998 is `confirmed` in a
    scene that never said what year it was. The tally alone reads as a clean
    pass, and only the per-citation `source` fields said otherwise.

    `_cover_note` does not cover this. It fires when the room filed no sources
    at all, and its own docstring hands the per-claim question here. A room
    full of sources that answer none of this scene is the case neither of them
    was watching.

    Counted over citations rather than over claims because a single claim can
    be answered by both, and a count that can exceed its own total is a
    sentence a reader has to distrust.
    """
    room = sum(
        1
        for claim in claims
        for source in claim.get("citation_sources") or []
        if source == "room"
    )
    search = sum(
        1
        for claim in claims
        for source in claim.get("citation_sources") or []
        if source == "search"
    )
    total = room + search
    if not total:
        # Every verdict came back with nothing behind it. The per-claim notes
        # already say what was looked for and not found, and a sentence about
        # the split between two ledgers that both answered nothing would be
        # arithmetic about an empty set.
        return ""
    if not room:
        return (
            f"None of the {total} sources behind these verdicts came out of "
            "this room's own files. Every one of them is from a search this "
            "check ran just now, so the room contributed nothing. That happens "
            "when a scene covers ground the room does not hold, including "
            "when the scene belongs to a different story than the room was "
            "built for, and it means these claims were judged against the "
            "world at large rather than against this room's era and setting."
        )
    if not search:
        return (
            f"All {total} sources behind these verdicts came out of this "
            "room's own files. This check bought nothing it did not already "
            "have."
        )
    return (
        f"Of the {total} sources behind these verdicts, {room} came out of "
        f"this room's own files and {search} from a search this check ran "
        "just now."
    )


async def _check_scene(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["check_scene"], arguments)
    scene = values["scene"]

    # The cap lives at the endpoint on the browser side
    # (star/server.py's create_scene), not inside `_run_check`, so this door
    # has to carry its own. Ahead of the call for the same reason as the
    # treatment checks: nothing is spent and nothing is stored, and the
    # message can say so.
    cap = config.max_scene_chars()
    if len(scene) > cap:
        raise _BadArguments(scene_too_long(len(scene), cap))

    result = _jsonable(await calls.run_check(identity.uid, values["run_id"], scene))
    claims = result.get("claims") or []
    counted = {
        verdict: sum(1 for claim in claims if claim.get("verdict") == verdict)
        for verdict in _VERDICTS
    }
    tally = ", ".join(f"{counted[verdict]} {verdict}" for verdict in _VERDICTS)

    lines = [
        (
            f"Checked {len(claims)} claim{'' if len(claims) == 1 else 's'} "
            f"from this scene against room {values['run_id']}: {tally}."
        )
    ]
    if result.get("cover_note"):
        lines.append(result["cover_note"])
    provenance = _provenance(claims)
    if provenance:
        lines.append(provenance)
    unsourced = result.get("unsourced_count") or 0
    if unsourced:
        lines.append(
            f"{unsourced} cited URL{'' if unsourced == 1 else 's'} turned up "
            "in neither the room's own files nor this check's searches. The "
            "claims that named them are stamped unsourced and are still "
            "below; the department will not present a source it cannot find "
            "in a ledger."
        )
    # Only when there is something to describe. A scene that asserts nothing
    # about the world is a legitimate result, and a paragraph explaining what
    # each claim carries, printed over zero claims, reads as a payload the
    # reader failed to receive.
    if claims:
        lines.append(
            "Each claim below carries the exact scene text it came from, the "
            "sources behind its verdict with their excerpts, and, per source, "
            "whether the room's own files or a fresh search produced it."
        )
    lines.append(
        f"This check spent {result.get('search_count') or 0} live web "
        "searches. The scene text is now stored with this room, and can be "
        "deleted from the room's script-check panel in the web app."
    )
    return _payload("\n\n".join(lines), result)


# Name to implementation, kept OUT of `TOOLS` rather than as a key inside each
# entry. `TOOLS` is serialised straight onto the wire, and a callable sitting
# in it would either fail to serialise or have to be stripped on the way out —
# a filter someone has to remember, which is the shape of mistake
# `star/tokens.py`'s to_metadata already refuses to make.
_RUNNERS: dict[str, Callable[[dict, "Calls", Any], Any]] = {
    "list_rooms": _list_rooms,
    "get_room": _get_room,
    "build_room": _build_room,
    "check_scene": _check_scene,
}


def _refused(detail: object, status: int) -> dict:
    """One of the server's own refusals, as something a model can act on.

    Replaced in one case, extended in two, and passed through otherwise.

    Replaced: `_read_room` and `_run_check` both raise 404 "Unknown run",
    which is the browser's answer. On screen it lands next to a rail listing
    every room the reader owns, so it needs to say nothing about how to get a
    working id. Here there is no rail, and a two-word refusal with no next
    step is exactly what `prd.md` fails a surface for.

    Extended: see READS_ARE_FREE and WAIT_FOR_THE_ROOM above. Both add the
    part a screen would have carried, and neither rewrites what the server
    said.

    Passed through otherwise, and that is the default on purpose. The hourly
    ceiling already names its ceiling, its window, and what is still free;
    re-wording it here would put the same fact in two files and let them drift.
    """
    text = str(detail)
    if status == 404:
        return text_result(ROOM_NOT_FOUND, is_error=True)
    if status == 429 and "reading" not in text.lower():
        text = f"{text} {READS_ARE_FREE}"
    elif status == 409 and "get_room" not in text:
        text = f"{text} {WAIT_FOR_THE_ROOM}"
    return text_result(text, is_error=True)


async def call(name: str, arguments: dict, calls: Calls, identity) -> dict:
    """Dispatch one `tools/call` onto the injected callables.

    `identity` is the resolved `TokenIdentity`, and every tool needs it: a
    room, a build, and a check are all scoped to one uid, and the uid is the
    only thing that makes the agent door and the browser door read the same
    ledger. It is passed per call rather than held on `Calls` because `Calls`
    is built once for the process and this is a fact about one request.

    Unknown names come back as a tool result rather than as `-32601`, and that
    is the deliberate half of the split above: a model that asked for a tool
    this server does not have made a recoverable mistake and can be told what
    to do about it, where a client that sent an unknown JSON-RPC *method* has
    a bug its model cannot fix. The same argument covers both excepts below —
    a refused argument and a refused call are things a model can read and
    answer, so neither is allowed to leave here as a protocol error.

    Nothing else is caught. An unexpected exception is not a refusal, it is a
    defect, and star/mcp/router.py logs it and answers with an internal error
    carrying none of this project's vocabulary.
    """
    runner = _RUNNERS.get(name)
    if runner is None:
        offered = ", ".join(f"`{tool}`" for tool in _TOOLS_BY_NAME)
        return text_result(
            f"There is no tool called `{name}`. This department offers four: "
            f"{offered}. Call `tools/list` for what each one takes and "
            "returns.",
            is_error=True,
        )
    try:
        return await runner(arguments, calls, identity)
    except _BadArguments as bad:
        return text_result(str(bad), is_error=True)
    except HTTPException as refused:
        return _refused(refused.detail, refused.status_code)
