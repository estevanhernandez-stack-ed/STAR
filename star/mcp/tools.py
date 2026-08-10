"""What the department tells an agent it can do, and where a call lands.

THE FOUR TOOLS ARE NOT HERE YET. This item built the transport, the auth, the
limiter, and the seam; the next one fills `TOOLS` with `list_rooms`,
`get_room`, `build_room`, and `check_scene` and writes the strings an agent
reads as the product. `TOOLS` being empty is a real state with a real answer —
`tools/list` returns an empty list and every `tools/call` comes back as an
unknown tool — rather than a stub that pretends.

`Calls` is the seam. star/server.py hands it four function objects, and three
of the four are the same objects its own HTTP handlers call, so "one
department, two doors" is a property of the wiring rather than a claim a
comment makes. spec.md's Decision 4 argues why the dependencies move to the
router instead of the run registry moving to a service module.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# What a client is told about the department at `initialize`, before it has
# read a single tool description. Deliberately about the shape of the work
# rather than about the tools: a build is slow and polled, a citation is only
# ever a source a search actually returned, and a checked scene is kept.
#
# The next item expands this alongside the four tool descriptions, and the
# copy rule that binds every other surface binds here too: never the bare word
# "verified" about a source, and never a duration promise.
INSTRUCTIONS = (
    "STAR is a research department for screenwriters. A room is a body of "
    "research built from a treatment: four categories of findings, each one "
    "carrying the sources behind it, plus a research bible.\n\n"
    "Building a room takes several minutes, so it returns an id to poll "
    "rather than holding the connection open. Every citation is hydrated "
    "server-side from what a live web search actually returned, and a claim "
    "whose source cannot be found in that ledger is stamped as unsourced "
    "rather than quietly dropped. A scene submitted for checking is stored "
    "with its room until it is deleted."
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


# The tool surface, in the exact shape `tools/list` puts on the wire — name,
# description, inputSchema, and nothing else. Empty until the next item. A
# tuple rather than a list so nothing can append to it at runtime and leave
# two callers disagreeing about what this server offers.
TOOLS: tuple[dict, ...] = ()

# Name to implementation, kept OUT of `TOOLS` rather than as a key inside each
# entry. `TOOLS` is serialised straight onto the wire, and a callable sitting
# in it would either fail to serialise or have to be stripped on the way out —
# a filter someone has to remember, which is the shape of mistake
# `star/tokens.py`'s to_metadata already refuses to make.
_RUNNERS: dict[str, Callable[[dict, "Calls", Any], Any]] = {}


def text_result(text: str, *, is_error: bool = False) -> dict:
    """One `CallToolResult`, which is how a tool reports both outcomes.

    A tool-level failure is `isError: true` with the reason in the content,
    never a JSON-RPC error object. The distinction is who the message is for:
    a JSON-RPC error says the client is broken and a model cannot act on it,
    while this reaches the calling model as text it can read and respond to.
    """
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


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
    a bug its model cannot fix.
    """
    runner = _RUNNERS.get(name)
    if runner is None:
        return text_result(
            f"There is no tool called {name!r}. Call tools/list for the ones "
            "this department offers.",
            is_error=True,
        )
    return await runner(arguments, calls, identity)
