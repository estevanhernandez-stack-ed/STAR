"""A story's rooms, read as one.

WHAT THIS IS AND WHAT IT REFUSES TO BE. A story spans eras: Liverpool in 1958
and Hamburg in 1960 are two worlds and want two rooms, each researched from its
own treatment. What a writer needs is not one enormous room — it is for a check
on a Hamburg scene to be able to use what the Liverpool room already found.

So rooms STACK AT READ TIME. Nothing is re-planned and no room is rebuilt.
`continues` already links one room to another; this walks that link and hands
the whole chain to whoever is answering a question.

WHY THIS IS THE SAFE HALF OF JOB 2B. The judge's version was to re-plan against
a revised treatment, and docs/continuation-brief.md records the risk: a planner
shown prior questions may SUPPRESS rather than narrow, and fail quietly — the
room comes back looking fine and thinner than it should be, with nothing on any
surface to say so. Stacking cannot fail that way. No planner is ever shown
anything, no research is skipped, and the only thing that changes is how much
evidence a reader has in front of them. A chain that is not working spends
searches it did not need to; a suppressed plan loses facts nobody knows are
missing.

EVERY ANSWER NAMES ITS ROOM. A chain that cannot say where a fact came from is
a bigger room with worse provenance, which is a trade this project does not
make.

Pure. No IO — the caller fetches; this decides what to fetch and in what order.
"""

# A story is a handful of rooms. This is not a limit anybody should meet: it is
# the bound that stops a corrupted `continues` — or a writer's own mistake —
# turning one check into an unbounded walk of a database.
MAX_DEPTH = 12


def order(run_id: str, rooms: dict[str, dict]) -> list[str]:
    """This room and every room it follows, NEAREST FIRST.

    `rooms` maps run_id to a stored document; anything the walk cannot find
    simply ends the chain, which is the honest outcome for a room that was
    deleted out from under a link.

    Nearest first, not root first, and the order is load-bearing — though not
    for the reason this said until 2026-08-17. There is no size ceiling and
    nothing truncates: `star/server.py`'s `_room_files` emits every cited
    finding in full. What ordering buys is attention, not survival. The room a
    writer is actually working in is read before a verifier has spent itself on
    four ancestors, which matters more the longer the chain gets.

    Cycle-safe by construction: a room already seen ends the walk. A writer can
    point two rooms at each other by hand, and a check that hung on it would be
    a check that never came back.
    """
    seen: list[str] = []
    current = str(run_id or "")
    while current and current not in seen and len(seen) < MAX_DEPTH:
        document = rooms.get(current)
        if document is None:
            break
        seen.append(current)
        current = str((document or {}).get("continues") or "").strip()
    return seen


def parents(document: dict) -> str:
    """The one room this document follows, or "" — read in one place so a
    caller never has to know how the link is spelled."""
    return str((document or {}).get("continues") or "").strip()


def label(document: dict) -> str:
    """A room's name for a reader, as a chain answer has to carry it.

    Title and era together, because a chain exists precisely when two rooms
    share a story and differ by period — and "Liverpool" alone does not say
    which of the two answered.
    """
    profile = (document or {}).get("story_profile") or {}
    title = str(profile.get("title") or document.get("title") or "Untitled room").strip()
    era = str(profile.get("era") or document.get("era") or "").strip()
    return f"{title} ({era})" if era else title
