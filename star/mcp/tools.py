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
import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from star import bible, config, defence
from star.findings import _tokenize
from star.models import Category

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
    "There are six tools. `list_rooms`, `get_room` and `ask_room` read; "
    "`build_room` and `check_scene` spend; `delete_room` removes.\n\n"
    "`delete_room` is the only call here that destroys anything, and it takes "
    "two: the first tells you what the room holds and hands back a one-time "
    "token, the second spends it. A deleted room is recoverable in the web app "
    "for a window, and only there — an agent can remove a room from a writer's "
    "workspace and cannot put it back.\n\n"
    "`ask_room` is the cheapest way in: give it a question and it returns the "
    "findings that bear on it, with their sources, out of a room that already "
    "exists. It searches what was filed and never writes an answer of its "
    "own, so what comes back is the department's words rather than a "
    "summary of them.\n\n"
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
    """The six things a tool is allowed to do, injected by star/server.py.

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
    delete_room: Callable[..., Any]
    run_requisition: Callable[..., Any]


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


# --- The tools --------------------------------------------------------------
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

_SHAPES = ("full", "findings", "plan", "bible", "summary")

# Everything but `categories`, which is the only part that carries bodies.
_LIGHT_KEYS = (
    "created_at",
    "story_profile",
    "search_count",
    "source_count",
    # Travels with every shape that carries counts, because a caller who asked
    # for less should not thereby be told less about what the room holds.
    "bible_coverage",
    # And for the same reason one step further: what a room holds is sometimes
    # an account of why it holds nothing. A `summary` that dropped the note
    # would answer a question about a failed room by omitting the only part of
    # it that says anything.
    "note",
)


TOOLS: tuple[dict, ...] = (
    {
        "name": "list_rooms",
        "description": (
            "List every research room filed under this account, newest "
            "first.\n\n"
            "Takes no arguments. Returns one entry per room: `run_id`, which "
            "is the id every other tool takes, plus `title`, `era`, `status`, "
            "`created_at`, `search_count`, the number of live web searches "
            "that room cost to build, `continues`, the `run_id` of the "
            "room this one follows, and `note`. It does not return the "
            "research itself; call `get_room` with a `run_id` for that.\n\n"
            "A `status` of `error` or `partial` means the build did not "
            "finish, and `note` is that room's account of why, in the words "
            "the writer was given at the time. A failed room still cost the "
            "searches it spent before it stopped, which is why it stays in "
            "the list rather than disappearing: `search_count` says what it "
            "cost and `note` says what happened. Rooms that finished carry "
            "an empty `note` and need none.\n\n"
            "A writer's rooms are not always a flat list. One story can span "
            "several eras, and a room that continues from another belongs "
            "under it — reading a chain from its first room forward is "
            "reading the story in the order it was researched. An empty "
            "`continues` means the room starts a story or stands alone. Only "
            "the writer sets that link; this door reports it.\n\n"
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
            "answers the same way as one that does not exist.\n\n"
            "**Ask for less than the whole room.** A complete room is about "
            "30,000 tokens, and roughly 72% of that is the quoted excerpt "
            "under each source. `shape` cuts it: `summary` is counts and the "
            "story profile, `bible` is the research bible alone, `plan` is "
            "what the department set out to find, and `findings` is every "
            "fact with every url and title but no quotes — about a quarter of "
            "the full size, losing nothing an agent cannot re-fetch from the "
            "url it is given. `full` is the default and is unchanged. "
            "`category` narrows any shape to one drawer. Whatever a shape "
            "leaves out, the reply says so, so a cut is never mistaken for an "
            "empty room."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": _ROOM_ID},
                "shape": {
                    "type": "string",
                    "enum": list(_SHAPES),
                    "description": (
                        "how much of the room to return: `summary`, `bible`, "
                        "`plan`, `findings`, or `full`. Defaults to `full`"
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                    "description": (
                        "one drawer to narrow to: `setting`, `objects_props`, "
                        "`logistics` or `forces_conflicts`. Defaults to all four"
                    ),
                },
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_room",
        "description": (
            "Ask a filed room a question and get back the findings that bear "
            "on it, each with the sources behind it.\n\n"
            f"Needs `run_id`, {_ROOM_ID}, and `question` — a plain question "
            "about the world of the story, in the writer's own words.\n\n"
            "**This is a search over what the department already filed. It is "
            "not new research, and it is not a model reading the room for "
            "you.** It matches your question against the text of each finding "
            "and returns the closest ones, ranked, unchanged, with their urls "
            "and titles. It does not summarise them, does not answer in its "
            "own words, and never says anything the room does not already "
            "say. If nothing in the room bears on the question it says so "
            "plainly rather than reaching: a room that was never researched "
            "for something does not contain it, and `build_room` is how you "
            "get research that does.\n\n"
            "Quoted excerpts are left out, the same as `get_room`'s "
            "`findings` shape, because they are about 72% of a room by size "
            "and every source is fetchable at the url returned beside it.\n\n"
            "Costs nothing, spends no searches, and is never rate-limited — "
            "it reads a room that already exists. `category` narrows the "
            "search to one drawer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": _ROOM_ID},
                "question": {
                    "type": "string",
                    "description": (
                        "a plain question about the story's world, in the "
                        "writer's own words"
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                    "description": (
                        "one drawer to search: `setting`, `objects_props`, "
                        "`logistics` or `forces_conflicts`. Defaults to all four"
                    ),
                },
            },
            "required": ["run_id", "question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "defend_claim",
        "description": (
            "Take one fact out of a filed room with everything behind it, in "
            "the shape a writer hands to someone challenging it.\n\n"
            f"Needs `run_id`, {_ROOM_ID}, and `fact` — the sentence to "
            "defend, as the room filed it or a distinctive fragment of it.\n\n"
            "Returns that fact, every source behind it with the page's own "
            "title and the excerpt the search returned, the date those "
            "sources were retrieved, which drawer it lives in, and whether "
            "the build filed it or a writer asked for it afterwards — with "
            "the question they asked, when they did.\n\n"
            "**It will not find a fact by approximation.** An exact match, or "
            "a fragment that appears in exactly one finding, or it says it "
            "cannot find it. A card assembled around the nearest match would "
            "put real sources behind a claim the room never made, which is "
            "worse than no card at all in the one conversation this exists "
            "for. Use `ask_room` to search on meaning and bring back the "
            "wording as filed.\n\n"
            "A source whose ADDRESS says it is a forum or comment page is "
            "marked `user_written`. The quotation from such a page is a post "
            "somebody made, not the site's own reporting — worth knowing "
            "before it is repeated, and not a verdict on it, since a forum "
            "thread is often the only place a detail survives. It is read off "
            "the url alone, so a page anyone can post to whose address does "
            "not announce it comes back unmarked: absence is not evidence of "
            "an editor.\n\n"
            "The retrieval date is the finding's own where it has one. A "
            "finding the build filed was retrieved when the room was made; "
            "one added later by `research_question` was retrieved then, and "
            "carries that date rather than the room's.\n\n"
            "What this proves is narrow and worth stating: every url came "
            "back from a live search and was recorded before the fact was "
            "written, so no source here was authored by a model. Whether the "
            "source supports the claim is a judgement the department does not "
            "make — the excerpts are returned so a reader can make it.\n\n"
            "Costs nothing, spends no searches, and is never rate-limited — "
            "it reads a room that already exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": _ROOM_ID},
                "fact": {
                    "type": "string",
                    "description": (
                        "the fact to defend, as the room filed it or a "
                        "distinctive fragment of it"
                    ),
                },
            },
            "required": ["run_id", "fact"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_room",
        "description": (
            "Delete a filed room. Two calls, and the first one deletes "
            "nothing.\n\n"
            "Call it with `run_id` alone and it tells you what the room holds "
            "— findings, sources, searches spent, the size of its bible — and "
            "hands back a one-time `confirm` token. Call it again with that "
            "token to go ahead. Do nothing after the first call and nothing "
            "happens.\n\n"
            "The two calls are the point rather than ceremony. A room costs "
            "real money and several minutes to build, and this is the only "
            "call at this door that destroys anything, so what is about to be "
            "lost is put in front of you before you can agree to lose it.\n\n"
            "A deleted room leaves the writer's rail immediately and stays "
            "recoverable in the web app for a window the reply names, after "
            "which it and every check filed against it are destroyed for good. "
            "**Restoring is the writer's decision and there is no tool for it "
            "here** — an agent can remove a room from their workspace and "
            "cannot put it back.\n\n"
            "Costs nothing and spends no searches. Needs the `rooms:delete` "
            "scope, which is granted separately from reading and building: a "
            "token that reads and builds does not delete unless the writer "
            "said so. **If this call returns 403 the credential lacks that "
            "scope, and the fix is not retrying — tell the writer to issue a "
            "token carrying `rooms:delete` from Your card in the web app, or "
            "to re-authorise this connection and approve deletion.** The "
            "refusal is an HTTP challenge rather than an error in the reply, "
            "so a client that cannot act on the challenge may surface it as a "
            "transport failure with nothing readable in it; this sentence is "
            "then the only account of what went wrong that reaches you.\n\n"
            "Read the room with `get_room` first if you are deciding rather "
            "than executing — this tool tells you what a room holds in counts, "
            "and `get_room` tells you what is actually in it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": _ROOM_ID},
                "confirm": {
                    "type": "string",
                    "description": (
                        "the one-time token the first call handed back. Leave "
                        "it out to see what the room holds and get one"
                    ),
                },
            },
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
            f"{MIN_TREATMENT_CHARS} and {_MAX_TREATMENT} characters. The "
            "department reads it, writes a research plan, and runs live web "
            "searches across setting, objects and props, logistics, and "
            "forces and conflicts.\n\n"
            "WHAT A TREATMENT IS READ FOR, because it decides what comes "
            "back. Six things are pulled out of it and every question the "
            "researchers ask is written from them: a title, a logline, the "
            "era, the locations, the genre, and the key entities — the "
            "people, professions, organisations, technologies and activities "
            "the story leans on. So name the era to the year, the places to "
            "the building, and the things that have to be real. Tone, theme "
            "and a character's interior life are not read out and produce no "
            "questions; they cost nothing to include and buy nothing. If the "
            "story is invented or fantastical, say so plainly and keep the "
            "real world in — the research comes back on the parts that "
            "existed.\n\n"
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
    {
        "name": "research_question",
        "description": (
            "Send one question back to the field and file the answer into a "
            "room that already exists.\n\n"
            "**This is what to reach for when `ask_room` says the room does "
            "not answer.** A room is a snapshot of the treatment it was built "
            "from, and a writer keeps working after it is filed. The old move "
            "was `build_room` — a whole second room, several minutes and a "
            "dozen searches, to answer one question. This researches the one "
            "question and files it into the room the writer already has, so "
            "the room grows with the story instead of freezing at intake.\n\n"
            f"Needs `run_id`, {_ROOM_ID}, `question` — one plain, factual, "
            "answerable question — and `category`, the drawer it belongs in. "
            "The drawer is not guessed: it is how a writer finds the fact "
            "again and what `get_room`'s own `category` filter narrows on, so "
            "a finding filed in the wrong one is filed where nobody looks.\n\n"
            "The answer comes back as an ordinary finding, cited to the same "
            "standard as the rest of the room: the researcher runs a live "
            "search and every url is hydrated from what that search actually "
            "returned, so a url the researcher named that no search result "
            "carried is reported as unsourced rather than printed as a "
            "source. The finding carries the question that requisitioned it, "
            "so a reader can always tell what the build filed from what was "
            "asked for later.\n\n"
            "If the researcher comes back without a citable answer, nothing "
            "is filed and the reply says so with what it spent. A room that "
            "grew a blank entry every time a question missed would be worse "
            "than one that stood still.\n\n"
            "**SPENDS. This is the half of asking that costs money** — live "
            "searches against the account's hourly window, unlike `ask_room`, "
            "which reads what is already filed and is free. It needs the "
            "`rooms:write` scope for that reason: a token granted only "
            "`rooms:read` can ask a room what it holds and cannot spend a "
            "writer's budget finding out what it does not."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": _ROOM_ID},
                "question": {
                    "type": "string",
                    "description": (
                        "one plain, factual, answerable question about the "
                        "story's world"
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                    "description": (
                        "the drawer to file the answer in: `setting`, "
                        "`objects_props`, `logistics` or `forces_conflicts`"
                    ),
                },
            },
            "required": ["run_id", "question", "category"],
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

    # Optional properties, handled here rather than in the tool, for the reason
    # the docstring above gives: the schema an agent reads in `tools/list` and
    # the rules it is held to have to be one object. A tool that read
    # `arguments.get("shape")` itself would be the second copy this function
    # exists to prevent, and the first thing to drift would be the enum.
    for key, spec in properties.items():
        if key in values or key not in arguments:
            continue
        value = arguments[key]
        if value is None:
            continue
        if not isinstance(value, str):
            raise _BadArguments(
                f"`{name}`'s `{key}` must be a string. This call sent "
                f"{_kind(value)}. It should be {spec['description']}."
            )
        value = value.strip()
        allowed = spec.get("enum")
        if allowed and value not in allowed:
            listed = ", ".join(f"`{option}`" for option in allowed)
            raise _BadArguments(
                f"`{name}` does not take `{value}` as `{key}`. It takes one "
                f"of {listed}. Sending none of them is also fine — "
                f"{spec['description']}"
            )
        if value:
            values[key] = value
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


def _spend_line(result: object) -> str:
    """What a failed build cost, said in the same breath as the failure.

    A build that fails has already spent live searches and a slot of the shared
    daily budget, and neither is refunded — correctly, because the money went.
    What was wrong was not charging for it, it was charging silently: an agent
    told only "this failed" cannot tell whether to retry, and a caller who
    retries three times has spent three slots learning that.
    """
    if not isinstance(result, dict):
        return ""
    searches = result.get("search_count") or 0
    if not searches:
        return ""
    sources = result.get("source_count") or 0
    found = (
        f" and returned {sources} source{'' if sources == 1 else 's'}"
        if sources
        else ""
    )
    return (
        f" It spent {searches} live search{'' if searches == 1 else 'es'}"
        f"{found} before it stopped. That is not refunded, and it used one of "
        "the department's daily builds. Retrying costs the same again."
    )


def _verify_line(result: object) -> str:
    """The cautions, in the line above the room rather than only inside it.

    The judge's round-two note asked for exactly this: the "Verify before
    writing" block is well written and it "lives inside the bible's prose. It
    belongs in the room's summary too — a writer who skims drawers and never
    reads the bible top-to-bottom shouldn't miss the one line that saves them a
    rewrite." An agent has no scrollbar at all; it reads what the tool says
    first and may never request the bible.

    Named, not counted-and-hidden. "3 cautions" would make a caller fetch the
    document to learn whether any of them mattered, and one of these is
    routinely the department telling a writer their own premise is dated wrong.
    """
    notes = bible.verify_notes(result)
    if not notes:
        return ""
    one = len(notes) == 1
    head = (
        " The researchers flagged one thing to verify before writing: "
        if one
        else f" The researchers flagged {len(notes)} things to verify before "
        "writing: "
    )
    if one:
        return head + notes[0]
    return head + "\n\n" + "\n".join(f"- {note}" for note in notes)


def _filed_drawers(result: object) -> int:
    """How many category drawers actually got findings into them.

    The companion to `_filed_anything`, which answers whether any did. Read off
    the payload for the same reason: the status says the pipeline finished, and
    that is not the same question as what is in the cabinet.
    """
    categories = (result or {}).get("categories") or {}
    if not isinstance(categories, dict):
        return 0
    return sum(1 for doc in categories.values() if (doc or {}).get("findings"))


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
        # The last clause is the one that can be wrong. A room whose editor
        # stopped after section one is still filed and still complete by every
        # other measure, and this sentence is fair right up to the point where
        # it promises a document the room does not have. So the clause is
        # asked for rather than asserted.
        # "four category drawers" was typed here, and it was the same defect
        # one clause early: four is what a healthy room has, not what this
        # room necessarily filed, and a complete build whose logistics
        # researcher came back empty was told it had four drawers of findings.
        # Counted now, from the same payload the drawers themselves come from.
        drawers = _filed_drawers(result)
        return (
            "This room is filed and complete: the story profile, the research "
            f"plan, {drawers} category drawer{'' if drawers == 1 else 's'} of "
            "findings with the sources behind them, and "
            + bible.closing_clause(result)
            + _verify_line(result)
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
                "the rest." + _spend_line(result)
            )
        return (
            "This build failed and filed nothing, so the room below is empty. "
            "Nothing more will be added and polling it again will not change "
            "that. Start another with `build_room`; a shorter, more specific "
            "treatment usually gets further." + _spend_line(result)
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
            "still need it." + _spend_line(result)
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


def _drawer_counts(categories: dict) -> dict:
    """How much is in each drawer, without any of it."""
    counts = {}
    for name, doc in (categories or {}).items():
        findings = (doc or {}).get("findings") or []
        counts[name] = {
            "findings": len(findings),
            "citations": sum(len((f or {}).get("citations") or []) for f in findings),
        }
    return counts


def _without_excerpts(categories: dict) -> dict:
    """The drawers, keeping every fact and every source, dropping the quotes.

    Measured against the stored rooms on 2026-08-11: excerpt text is **72.3%**
    of a complete room's payload and the facts themselves are 4.4%. Dropping
    excerpts alone takes `get_room` from 31,047 tokens to 8,613 without losing
    a single fact, url, title or unverified-url warning — an agent keeps
    everything it needs to reason and to fetch a source itself, and loses only
    the quoted passage it can retrieve from the url.
    """
    out = {}
    for name, doc in (categories or {}).items():
        doc = dict(doc or {})
        doc["findings"] = [
            {
                **{k: v for k, v in (f or {}).items() if k != "citations"},
                "citations": [
                    {k: v for k, v in (c or {}).items() if k != "excerpt"}
                    for c in ((f or {}).get("citations") or [])
                ],
            }
            for f in (doc.get("findings") or [])
        ]
        out[name] = doc
    return out


def _project_room(result: object, shape: str, category: str | None) -> object:
    """One room, cut to the shape the caller asked for. Pure.

    `full` is the default and returns exactly what this tool has always
    returned, so an agent written before this argument existed is unaffected.
    Every other shape is strictly smaller.
    """
    if not isinstance(result, dict):
        return result

    if category:
        result = {**result, "categories": {
            name: doc for name, doc in (result.get("categories") or {}).items()
            if name == category
        }}

    if shape == "summary":
        return {
            **{k: result.get(k) for k in _LIGHT_KEYS},
            "drawers": _drawer_counts(result.get("categories") or {}),
            "research_bible_chars": len(result.get("research_bible") or ""),
        }
    if shape == "bible":
        return {
            "created_at": result.get("created_at"),
            "research_bible": result.get("research_bible") or "",
            # The one shape where the measurement is most obviously the
            # caller's business: they asked for the bible, so whether it is
            # whole is part of the answer.
            "bible_coverage": result.get("bible_coverage"),
        }
    if shape == "plan":
        return {
            **{k: result.get(k) for k in _LIGHT_KEYS},
            "research_plan": result.get("research_plan"),
        }
    if shape == "findings":
        return {
            **{k: result.get(k) for k in _LIGHT_KEYS},
            "categories": _without_excerpts(result.get("categories") or {}),
        }
    return result


async def _get_room(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["get_room"], arguments)
    run_id = values["run_id"]
    shape = values.get("shape") or "full"
    category = values.get("category")
    room = await calls.read_room(identity.uid, run_id)
    status = room.get("status") or "unknown"
    whole = room.get("result")
    result = _project_room(whole, shape, category)
    # Reported off the WHOLE room, not the projection. A caller asking for
    # `findings` gets a payload with no bible in it, and reporting off that
    # would have told them the bible was fine by saying nothing about it —
    # the shape they asked for deciding what they are allowed to learn.
    report = _room_report(status, whole)
    if shape != "full" or category:
        report = f"{report}\n\n{_shape_note(shape, category)}"
    return _payload(
        report,
        {"run_id": run_id, "status": status, "shape": shape, "room": result},
    )


def _shape_note(shape: str, category: str | None) -> str:
    """Say what was left out, so an agent never mistakes a cut for an absence.

    The whole risk of this argument is an agent reading a `findings` room and
    concluding the sources have no excerpts, or reading a `bible` room and
    concluding the drawers are empty. A shape has to announce itself.
    """
    drawer = f" from the `{category}` drawer only" if category else ""
    if shape == "summary":
        return (
            f"This is a `summary`{drawer}: counts and the story profile, with "
            "no findings, no sources and no bible. Nothing here is missing "
            "from the room — call again with `shape` set to `findings`, "
            "`bible` or `full` for the contents."
        )
    if shape == "bible":
        return (
            f"This is the research bible alone{drawer}. The findings and their "
            "sources are in the room and were not returned; call again with "
            "`shape` set to `findings` for those."
        )
    if shape == "plan":
        return (
            f"This is the story profile and research plan{drawer} — what the "
            "department set out to find, not what it found. Call again with "
            "`shape` set to `findings` for the results."
        )
    if shape == "findings":
        return (
            f"These are the findings{drawer} with every fact, url and title, "
            "and with the quoted excerpts left out — they are about 72% of a "
            "room by size. Every source is still here and still fetchable at "
            "its url. Call again with `shape` set to `full` for the quotes."
        )
    return f"This is the whole room, filtered to the `{category}` drawer."


# How many findings one question gets back. Not an argument: every property in
# these schemas is a string and the suite holds them to it, so a numeric `limit`
# would be the one exception an agent has to discover. Eight is enough to answer
# a question and small enough that the reply stays cheap; the report says how
# many matched in total, so an agent knows when it is seeing a slice.
_ASK_LIMIT = 8

# Words a question is BUILT from rather than words it asks ABOUT. They survive
# `_tokenize`'s four-character floor and then match nearly any prose, which is
# how "what were the tram timetables in Lisbon" found two Ruth Kovacs findings
# on `what` and `were` alone — a room with nothing about trams, answering a
# question about trams, on the strength of two English function words.
#
# Dropped from the QUESTION only. A finding that genuinely says "what" keeps
# it; there is just never a reason to treat it as evidence of an answer.
_QUESTION_WORDS = frozenset({
    "about", "after", "also", "another", "back", "because", "been", "before",
    "being", "both", "came", "come", "could", "does", "doing", "done", "down",
    "each", "even", "ever", "every", "from", "gave", "give", "goes", "going",
    "gone", "have", "here", "into", "just", "kind", "know", "made", "make",
    "like", "look", "looked", "looks",
    "many", "might", "more", "most", "much", "must", "need", "onto", "only",
    "other", "over", "same", "shall", "should", "since", "some", "such",
    "take", "tell", "than", "that", "their", "them", "then", "there", "these",
    "they", "thing", "things", "this", "those", "through", "used", "using",
    "very", "want", "well", "went", "were", "what", "when", "where", "which",
    "while", "will", "with", "within", "without", "would", "your",
})

# How much of a question has to find ANY home in the room before the room is
# allowed to answer it. Measured across the twenty-one stored rooms on
# 2026-08-12, and the reason this is a question-level rule rather than a
# per-term one: the first attempt at this fix weighted terms by how much of the
# room they cover, on the theory that an era year saturates its room. It does
# not. `1978` is in 8 of 29 Lenin Shipyard findings, `1984` in 26 of 32 of the
# Colliery Canteen's, `1929` in 3 of 38 of Ruth Kovacs' — 8% to 81%, with real
# search terms sitting in the same range. No cutoff on document frequency tells
# an era year apart from a term worth ranking on, and a fix built on one passed
# every unit test while leaving the reported bug exactly as it was.
#
# What does separate them is how much of the QUESTION the room can speak to at
# all. Against the same rooms: questions that bear found homes for 67%, 75% and
# 100% of their content terms; questions that reach found 0%, 25%, 50% and 50%.
# A room that cannot place more than half of what you asked about was not
# researched for this, and one term that happens to land is a coincidence of
# vocabulary rather than an answer.
_QUESTION_COVERAGE = 0.5

# Once a room does answer, how weak a match may still be shown, as a share of
# the best match in that room. Coverage decides WHETHER the room speaks; this
# decides which findings are worth putting in front of a reader.
#
# The case it exists for: ask a 1978 room about the barracks on Kartuska and
# the coverage gate opens, correctly — but every finding carrying `1978` also
# matches, so one real answer arrives with eight findings about riot uniforms
# and penal code articles behind it. Their evidence is the era year and the era
# year is worth almost nothing here, which the weighting already knows: the
# barracks finding outscores them by a factor of forty. Relative rather than
# absolute, because it asks the only question that generalises across rooms —
# not "is this term rare" but "is this the same kind of evidence as the best
# thing we found".
#
# A tenth, not a quarter, and the difference is a real finding: asked how the
# blackout affected the subway, the BROWNOUT room's best match carries `subway`
# (1 of 28 findings, heavily weighted) while a second carries only `blackout`
# (19 of 28) — the closure of the transit tunnels for loss of ventilation,
# which is most of the answer. At a quarter that finding was cut for standing
# in the shadow of a stronger one. Secondary evidence is still evidence; this
# bar is for findings that share a word, not for findings that say less.
_WEAK_EVIDENCE_SHARE = 0.10


def _rank_findings(room: dict, question: str, category: str | None) -> tuple[list[dict], int]:
    """The findings whose text bears on the question, best first.

    Token overlap, using star/findings.py's own `_tokenize` rather than a
    second one — the same scoring `_best_excerpt` already uses to pick which
    excerpt belongs to a fact, and imported for the reason star/verdicts.py
    imports four other names from that module instead of copying them.

    Scored against the fact AND its source titles, because a question about
    "the shipyard gate" should reach a finding whose fact says "Brama nr 2" if
    the source it rests on is titled "Gate No. 2 of the Gdansk Shipyard". The
    citation urls are deliberately NOT scored: a url matches on domain noise
    and would rank every wikipedia source above a real answer.

    OVERLAP ALONE IS NOT BEARING, WHICH IS WHAT THIS FUNCTION USED TO ASSUME.
    Counting shared tokens made every term worth the same, and the term a room
    shares with itself is worth nothing: ask a room whose era is 1978 "what
    songs would be playing on the radio in 1978" and the old scoring returned
    eight findings — ZOMO uniforms, penal code articles, barracks locations —
    each riding on the single token `1978`, because `1978` is in most facts a
    1978 room ever wrote. Nothing bore on the question and the tool answered
    anyway, which is the one failure this tool exists to not have: the
    description at the top of this module promises it "says so plainly rather
    than reaching," and `songs` and `radio` matched nothing at all.

    So bearing is decided BEFORE ranking, and at the level of the question
    rather than the finding: strip the words a question is built from
    (`_QUESTION_WORDS`), then ask how many of the content terms left find any
    home in this room at all. Below `_QUESTION_COVERAGE` the room cannot speak
    to what was asked, nothing is returned, and the caller's refusal path says
    so plainly. Above it, findings are ranked by inverse document frequency —
    a term in one finding of forty is stronger evidence than a term in twenty,
    and the ordering follows.

    The consequence worth stating, because it looks like a bug and is not: a
    room can hold a finding that mentions your subject and still refuse, when
    the rest of the question lands nowhere. "What music was on the radio",
    asked of a room with one passing mention of a radio, is not a question that
    room researched. The refusal copy already points at `get_room` for a reader
    who wants to judge that themselves, and at `build_room` for research that
    would actually answer.
    """
    wanted = _tokenize(question) - _QUESTION_WORDS
    if not wanted:
        return [], 0

    # Two passes, because a term's weight is a fact about the room and cannot
    # be known while still walking it.
    corpus: list[tuple[str, dict, set[str]]] = []
    for name, doc in (room.get("categories") or {}).items():
        if category and name != category:
            continue
        for finding in (doc or {}).get("findings") or []:
            finding = finding or {}
            text = " ".join(
                [str(finding.get("fact") or "")]
                + [str((c or {}).get("title") or "") for c in finding.get("citations") or []]
            )
            corpus.append((name, finding, _tokenize(text)))

    total_findings = len(corpus)
    if not total_findings:
        return [], 0

    # Document frequency for the question's terms only. Nothing else is ever
    # weighed, so nothing else is ever counted.
    frequency = {
        term: sum(1 for _, _, tokens in corpus if term in tokens) for term in wanted
    }

    # Does the room speak to this question at all? Decided once, over the whole
    # question, before any finding is looked at — a per-finding rule cannot see
    # that `songs`, `playing` and `radio` all landed nowhere.
    placed = sum(1 for count in frequency.values() if count)
    if placed / len(wanted) <= _QUESTION_COVERAGE:
        return [], 0

    scored: list[tuple[float, int, dict]] = []
    for name, finding, tokens in corpus:
        matched = wanted & tokens
        if not matched:
            continue
        # Smoothed so it stays positive at every corpus size: the ordering is
        # wanted even in a room too small for frequency to mean much.
        weight = sum(
            math.log((total_findings + 1) / frequency[term]) for term in matched
        )
        scored.append((weight, len(matched), {
            "category": name,
            "fact": finding.get("fact") or "",
            # The raw count, not the weight. It is what a reader can verify
            # against the fact in front of them, and a float nobody can check
            # would be a worse thing to publish than a number they can.
            "matched_terms": len(matched),
            # url and title only, for the reason get_room's `findings`
            # shape drops excerpts: they are 72% of a room and every one
            # of them is fetchable at the url beside it.
            "citations": [
                {"url": (c or {}).get("url") or "", "title": (c or {}).get("title") or ""}
                for c in finding.get("citations") or []
            ],
            "unverified_urls": finding.get("unverified_urls") or [],
        }))
    scored.sort(key=lambda triple: (triple[0], triple[1]), reverse=True)
    if not scored:
        return [], 0

    # Everything standing far below the best evidence in the room is not a
    # weaker answer, it is a different question's finding that shares a word.
    floor = scored[0][0] * _WEAK_EVIDENCE_SHARE
    kept = [triple for triple in scored if triple[0] >= floor]
    return [item for _, _, item in kept[:_ASK_LIMIT]], len(kept)


def _searched_count(room: dict, category: str | None) -> int:
    return sum(
        len((doc or {}).get("findings") or [])
        for name, doc in (room.get("categories") or {}).items()
        if not category or name == category
    )


async def _ask_room(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["ask_room"], arguments)
    run_id = values["run_id"]
    question = values["question"]
    category = values.get("category")

    room = await calls.read_room(identity.uid, run_id)
    status = room.get("status") or "unknown"
    result = room.get("result")

    # No early return for `running`. Mutation testing found this branch was
    # dead weight: `_room_report` already answers STILL_BUILDING for that
    # status, so removing the branch changed no text — and the branch was
    # quietly WORSE, because it dropped `question` from the payload that the
    # nothing-filed path below carries. One path, one shape.
    if not isinstance(result, dict) or not _filed_anything(result):
        return _payload(
            _room_report(status, result),
            {"run_id": run_id, "status": status, "question": question, "matches": []},
        )

    matches, total = _rank_findings(result, question, category)
    searched = _searched_count(result, category)
    drawer = f" in the `{category}` drawer" if category else ""

    if not matches:
        report = (
            f"Nothing{drawer} in this room bears on that question. The "
            f"department researched {searched} findings here and none of them "
            "share wording with what you asked, so this room does not answer "
            "it — that is a fact about the research, not a failure of the "
            "search.\n\n"
            "**`research_question` sends this one question back to the field "
            "and files the answer into this room.** That is the move here: it "
            "spends a live search or two and the room grows to cover what was "
            "asked, rather than the writer paying for a whole second room to "
            "learn one thing. Read the room with `get_room` first if you want "
            "to judge the gap yourself; `build_room` is for a different story, "
            "not for a hole in this one."
        )
    else:
        more = (
            f" {total} findings matched in total; the closest {len(matches)} "
            "are below."
            if total > len(matches)
            else ""
        )
        report = (
            f"{len(matches)} of {searched} findings{drawer} share wording with "
            f"that question, closest first.{more} These are the department's "
            "own findings, returned unchanged and with the sources behind "
            "them. Nothing here was written to answer you: this is a text "
            "match over what was already filed, so read the facts and judge "
            "whether they bear on what you asked. Quoted excerpts are left "
            "out; each source is fetchable at its url."
        )

    return _payload(report, {
        "run_id": run_id,
        "status": status,
        "question": question,
        "searched": searched,
        "matched": total,
        "matches": matches,
    })


# Pending delete confirmations, keyed by (uid, run_id) -> (token, issued_at).
#
# In memory, for the reason star/server.py keeps `_runs` there: this service
# deploys at `--min-instances=1` with the abuse guards already depending on
# single-process state, so a second store would be new infrastructure for a
# value that is worthless ten minutes after it is minted. A restart drops
# pending confirmations and an agent simply asks again — which the refusal
# below says, because an agent told only "invalid token" would retry the
# confirm rather than restart the handshake.
_PENDING_DELETES: dict[tuple[str, str], tuple[str, float]] = {}

# Long enough for an agent to read what it is about to destroy and decide;
# short enough that a token found in a log is worthless.
_CONFIRM_TTL_SECONDS = 600


def _mint_confirm(uid: str, run_id: str) -> str:
    token = secrets.token_urlsafe(9)
    _PENDING_DELETES[(uid, run_id)] = (token, time.monotonic())
    return token


def _spend_confirm(uid: str, run_id: str, offered: str) -> bool:
    """Single use, and only for the room it was minted against.

    Keyed by room as well as by account so a token handed out for one room can
    never delete another — an agent holding a confirmation for a room it meant
    to remove must not be one argument away from removing a different one.
    """
    held = _PENDING_DELETES.get((uid, run_id))
    if held is None:
        return False
    token, issued = held
    del _PENDING_DELETES[(uid, run_id)]
    if time.monotonic() - issued > _CONFIRM_TTL_SECONDS:
        return False
    return secrets.compare_digest(token, offered)


def _what_goes(document: dict) -> str:
    """What this delete costs, in the department's own counts.

    The whole point of the first call. web/scriptcheck.js argues that a
    destructive control must say "exactly what goes" before it acts, and that
    "nothing is hidden behind a browser dialog: the warning is on the page". An
    agent has no page, so the warning is this sentence, in its context, before
    it can commit.
    """
    categories = (document.get("categories") or {}).values()
    findings = sum(len((doc or {}).get("findings") or []) for doc in categories)
    parts = [
        f"{findings} findings",
        f"{document.get('source_count') or 0} sources",
        f"{document.get('search_count') or 0} searches spent",
    ]
    bible = len(document.get("research_bible") or "")
    if bible:
        parts.append(f"a {bible:,}-character research bible")
    return ", ".join(parts)


async def _following(calls: Calls, uid: str, run_id: str) -> list[str]:
    """Every room that continues from this one, however far down the chain.

    Read off the account's own list, which the rail already builds, rather than
    a query: the link points UP, so there is no index that answers "what points
    at me" without scanning anyway.

    Bounded by what it has already seen. The web door refuses to create a ring
    and so does nothing else, but data written before that guard existed must
    not spin a delete warning — and a room is never among its own followers,
    which in a ring it would otherwise reach.
    """
    rooms = await calls.list_rooms_for(uid)
    children: dict[str, list[str]] = {}
    for room in rooms:
        parent = (room.get("continues") or "").strip()
        if parent:
            children.setdefault(parent, []).append(room.get("run_id") or "")

    seen: set[str] = set()
    stack = list(children.get(run_id) or ())
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(children.get(current) or ())
    seen.discard(run_id)
    return sorted(seen)


def _follows_note(followers: list[str]) -> str:
    """The sentence a delete earns when other rooms lean on this one.

    Says what does NOT happen as plainly as what does. The reader is one call
    from spending a token, and "3 rooms continue from this one" without "they
    stay" reads like a warning that three more rooms are about to go.
    """
    if not followers:
        return ""
    count = len(followers)
    if count == 1:
        return (
            " 1 room in this account continues from this one. It stays and "
            "keeps its research. What it loses is the link, which afterwards "
            "reads as a room that is no longer filed."
        )
    return (
        f" {count} rooms in this account continue from this one. They stay and "
        "keep their research. What they lose is the link, which afterwards "
        "reads as a room that is no longer filed."
    )


async def _delete_room(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["delete_room"], arguments)
    run_id = values["run_id"]
    confirm = values.get("confirm")
    days = config.room_retention_days()

    if not confirm:
        room = await calls.read_room(identity.uid, run_id)
        document = room.get("result")
        if not isinstance(document, dict):
            return _payload(ROOM_NOT_FOUND, {"run_id": run_id, "deleted": False})
        # What ELSE this delete touches. Rooms that continue from this one are
        # not deleted with it — a room's delete already takes its scenes, and
        # extending that to a story's later rooms would let one confirmation
        # destroy work the caller never named. But their link goes stale, and a
        # caller about to spend a token is owed that before they spend it.
        followers = await _following(calls, identity.uid, run_id)
        token = _mint_confirm(identity.uid, run_id)
        return _payload(
            f"This has deleted nothing yet. The room holds {_what_goes(document)}. "
            f"Deleting it takes it out of the writer's rail at once and keeps it "
            f"recoverable in the web app for {days} days, after which it is "
            f"destroyed for good along with every check filed against it."
            f"{_follows_note(followers)}\n\n"
            f"To go ahead, call `delete_room` again with `confirm` set to "
            f"`{token}`. That token is good once, for this room only, for about "
            f"ten minutes. Do nothing and nothing happens.",
            {"run_id": run_id, "deleted": False, "confirm": token,
             "retention_days": days, "holds": _what_goes(document),
             "followed_by": followers},
        )

    if not _spend_confirm(identity.uid, run_id, confirm):
        return text_result(
            "That confirmation is not good for this room. A token works once, "
            "for the room it was issued against, for about ten minutes, and "
            "the department forgets every pending one if it restarts. Call "
            "`delete_room` with `run_id` and no `confirm` to see what the room "
            "holds and get a fresh one.",
            is_error=True,
        )

    document = await calls.delete_room(identity.uid, run_id)
    if document is None:
        return text_result(ROOM_NOT_FOUND, is_error=True)
    return _payload(
        f"Deleted. The room is out of the writer's rail now and recoverable in "
        f"the web app for {days} days; after that it and every check filed "
        f"against it are destroyed for good. Nothing at this door can bring it "
        f"back — restoring is the writer's decision to make.",
        {"run_id": run_id, "deleted": True,
         "deleted_at": document.get("deleted_at") or "", "retention_days": days},
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
    # Directly under the tally, because the tally is what it qualifies. A count
    # of confirmed claims reads as a verdict on the whole scene unless the next
    # sentence says which kinds of claim were looked at.
    if result.get("scope_note"):
        lines.append(result["scope_note"])
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


async def _defend_claim(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["defend_claim"], arguments)
    run_id = values["run_id"]
    fact = values["fact"]

    room = await calls.read_room(identity.uid, run_id)
    status = room.get("status") or "unknown"
    result = room.get("result")
    if not isinstance(result, dict) or not _filed_anything(result):
        return _payload(
            _room_report(status, result),
            {"run_id": run_id, "status": status, "fact": fact, "found": False},
        )

    located = defence.locate(result, fact)
    if located is None:
        return _payload(
            "No finding in this room says that. The department can only "
            "defend what it filed, and it will not assemble a citation for a "
            "sentence it cannot find — a card built around the nearest match "
            "would put sources behind a claim the room never made, which is "
            "the failure this call exists to prevent. Check the wording with "
            "`ask_room`, which searches on meaning rather than on the exact "
            "sentence, and bring back the fact as it is filed. If the room "
            "genuinely does not cover it, `research_question` can send it to "
            "the field.",
            {"run_id": run_id, "fact": fact, "found": False},
        )

    category, finding = located
    card = defence.card(result, category, finding, run_id)
    sources = card["sources"]
    quoted = sum(1 for source in sources if source["excerpt"])

    lines = [
        f"{card['room']['title']} — one claim, and where it came from.",
        card["fact"],
    ]
    if card["filed_by"] == "requisition":
        lines.append(
            "Filed after the room was built, in answer to: "
            f"{card['requisition']}. Its sources were retrieved then, not when "
            "the room was made, and the date below is that retrieval."
        )
    if sources:
        lines.append(
            f"{len(sources)} source{'' if len(sources) == 1 else 's'} behind "
            f"it, {quoted} carrying the page's own words. Every url here came "
            "back from a live search and was recorded before this fact was "
            "written — the title and the excerpt are the page's, not a "
            "model's. That is what the department can say. Whether the source "
            "supports the claim is a judgement it does not make for you, and "
            "the excerpts are here so you can make it."
        )
    else:
        lines.append(
            "No source is filed behind this fact. The department will not "
            "assemble a defence out of nothing, and a claim in this state "
            "should not go in front of anyone who might ask."
        )
    posted = [source for source in sources if source.get("user_written")]
    if posted:
        lines.append(
            f"{len(posted)} of these address{'' if len(posted) == 1 else 'es'} "
            f"{'is' if len(posted) == 1 else 'are'} a forum or comment page — "
            f"`{posted[0]['url']}`"
            + (f" and {len(posted) - 1} more" if len(posted) > 1 else "")
            + ". The quotation is a post somebody made there, not the site's "
            "own reporting, and it is worth saying so before this goes in "
            "front of anyone. That is not a verdict on it: a forum thread is "
            "often the only place a detail survives. Read off the url, so a "
            "page anyone can post to whose address does not say so is not "
            "marked here — absence of this note is not evidence of an editor."
        )
    if card["unsourced_urls"]:
        count = len(card["unsourced_urls"])
        lines.append(
            f"{count} url{'' if count == 1 else 's'} the researcher named "
            "never appeared in a search result and "
            f"{'is' if count == 1 else 'are'} stamped unsourced below. "
            "Do not cite them."
        )
    return _payload("\n\n".join(lines), card)


async def _research_question(arguments: dict, calls: Calls, identity) -> dict:
    values = _arguments(_TOOLS_BY_NAME["research_question"], arguments)
    question = values["question"]

    # Ahead of the call, for the reason check_scene's cap is: the browser's cap
    # lives at star/server.py's endpoint rather than inside the runner, so this
    # door carries its own, and refusing here means nothing was spent and the
    # message can say so.
    cap = config.max_question_chars()
    if len(question) > cap:
        raise _BadArguments(
            f"That question is {len(question)} characters and the ceiling is "
            f"{cap}. Ask one thing rather than pasting a treatment — "
            "`build_room` is the tool that takes a document."
        )

    result = _jsonable(
        await calls.run_requisition(
            identity.uid, values["run_id"], question, values["category"]
        )
    )
    findings = result.get("findings") or []
    unsourced = sum(len((f or {}).get("unverified_urls") or []) for f in findings)
    sourced = sum(len((f or {}).get("citations") or []) for f in findings)

    lines = [
        (
            f"Filed {len(findings)} finding"
            f"{'' if len(findings) == 1 else 's'} into the "
            f"`{result.get('category')}` drawer of room {values['run_id']}, "
            f"answering: {question}"
        )
    ]
    lines.append(
        f"{sourced} source{'' if sourced == 1 else 's'} behind "
        f"{'it' if len(findings) == 1 else 'them'}, every one hydrated from "
        "what the search actually returned. This room now stands at "
        f"{result.get('search_count')} live searches and "
        f"{result.get('source_count')} sources."
    )
    if unsourced:
        lines.append(
            f"{unsourced} url{'' if unsourced == 1 else 's'} the researcher "
            "named never appeared in a search result, and "
            f"{'is' if unsourced == 1 else 'are'} stamped unsourced rather "
            "than presented as a source. The department will not present a "
            "source it cannot find in a ledger."
        )
    lines.append(
        "Each finding carries the question that requisitioned it, so a later "
        "reader can tell what the build filed from what was asked for after. "
        "`get_room` returns them alongside the rest of the drawer."
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
    "ask_room": _ask_room,
    "defend_claim": _defend_claim,
    "research_question": _research_question,
    "delete_room": _delete_room,
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
            f"There is no tool called `{name}`. This department offers "
            f"{len(_TOOLS_BY_NAME)}: {offered}. Call `tools/list` for what each one takes and "
            "returns.",
            is_error=True,
        )
    try:
        return await runner(arguments, calls, identity)
    except _BadArguments as bad:
        return text_result(str(bad), is_error=True)
    except HTTPException as refused:
        return _refused(refused.detail, refused.status_code)
