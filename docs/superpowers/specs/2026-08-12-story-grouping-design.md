# Rooms belong to a story — design

**Date:** 2026-08-12
**Status:** authoritative for this feature. Supersedes `docs/spec.md` and
`docs/checklist.md` where they disagree; `checklist.md` is from an unrelated
earlier cycle and is **not** the plan for this work.
**Relationship to `docs/continuation-brief.md`:** that brief proposes the whole
continuation feature. This ships its **visible half** on the brief's schema.
The brief stays as written and remains the plan for the rest.

## The decision

Option 2 of three, chosen 2026-08-12 against the Sep 7 deadline.

Continuation has a visible half and an invisible half. Visible: rooms belong to
a story, they can be named, and the rail reads as a body of work instead of a
log. Invisible: the planner inherits scope so a later room is cheaper and
sharper. **This ships the visible half only, on the same data model the
invisible half will need**, so the rest drops in later with no migration and
nothing thrown away.

## Why this cut

Two independent readings landed on the same wound from opposite ends.

The builder's, from real use on 2026-08-12: a full story spans eras, the app
serves one treatment at a time, and the next step after a first room feels
fragmented even for a demo user.

The judge's, from `docs/judge-critique-round2-2026-08-11.md`, under *Still
standing*: *"Room hygiene. The account still lists three 'Untitled' rooms and
the errored husk; no retitle, no delete, no way to clean up over either door."*
Delete shipped. **Retitle never did** — there is no rename path in
`star/server.py`, `star/store.py` or the web app, and `star/store.py` still
hard-codes `"Untitled room"` as a permanent fate.

The invisible half is deliberately out of scope, and not for time. The
continuation brief records the risk that decides it: a planner shown prior
questions may **suppress** rather than narrow, failing quietly — the room comes
back looking fine and is thinner than it should be. Settling that honestly
needs paired builds and a measurement. Shipping it unmeasured into a submission
risks demonstrating a feature that makes research worse, with no way to know.

## What ships

1. A room can be **retitled**.
2. A room can name the room it **continues from**, at build time or afterwards.
3. The rail **groups** rooms that share a chain.
4. `delete_room` says how many rooms continue from the one being deleted.

Nothing else. No planner change, no inherited profile, no `ask_hallway`, no new
scope, no new collection.

## Decisions — build these, do not re-litigate

1. **`continues` is a single parent `run_id` on the room document.** One
   parent, not a set. A tree, not a graph. The hallway is the connected
   component and stays trivially walkable. Same field the full brief specifies,
   so the invisible half needs no migration.
2. **The hallway is derived, never authored.** No hallway document, no name, no
   membership list. This follows the rule the bible mark was rewritten under on
   2026-08-11: a mark is derived, never authored. A container would be a second
   source of truth for what the links already say.
3. **Retitle overwrites the stored `title`.** `story_profile.title` keeps the
   original, so nothing is lost and the derived title is still recoverable. No
   `title_set_by_writer` flag: a second field to explain the first is a second
   thing to keep true.
4. **A title is trimmed, capped, and never empty.** An empty retitle restores
   the derived title rather than storing `""`. Cap follows the existing
   `config.max_*` pattern with an env override.
5. **Retitle and re-parent are web-app only.** No new MCP tools. This matches
   `docs/delete-brief.md` decision 6 — restore is web-only because coming back
   from a delete is a person's decision — and naming a writer's own work is the
   same kind of act. The judge's "over either door" wording is noted and
   deliberately not followed here: an agent that can rename a writer's rooms is
   worse than an agent that cannot.
6. **`continues` is settable at build time and editable afterwards**, from the
   same control that retitles. Editable matters because ten rooms already
   exist; a build-time-only link would leave every one of them ungroupable.
7. **A room may not continue from itself or from any of its descendants.** The
   guard walks the chain and refuses by name, per the repo's refusal rule: say
   what failed and what to do next.
8. **A parent that no longer exists degrades honestly.** Rooms soft-delete and
   purge after `config.room_retention_days()`. A child whose parent is gone
   reads "continues from a room that is no longer filed" and still works. It
   does not break and does not silently drop the link without saying so.
9. **Deleting a parent does not delete its children.** Room delete already
   cascades to scenes; extending that to children would let one confirmation
   destroy work the caller never named. `delete_room`'s first call — the one
   that destroys nothing and reports what will be lost — states how many rooms
   continue from this one. The web app's two-press arming says the same.
10. **Grouping is presentation, computed from the links.** Rooms in a chain
    render together under the chain root's title, oldest first, because that is
    the story's own order. Ungrouped rooms keep the existing newest-first flat
    behaviour. Chains sort by their most recent room.

## Build

Order is by dependency. Commit each item separately.

**1. Store.** `title` becomes writable; `continues` on the room document.
`document_to_room` and `room_summary` both carry `continues` — the rail cannot
group without it, and reading every room whole to draw a list is the defect
`room_summary` exists to prevent. A `set_title` and a `set_continues` on
`RoomStore`, ownership by path construction the way `delete_scene` gets it, not
by an ownership check. Read `delete_scene`'s docstring before writing them; it
is the model for how a store method explains itself.

**2. Config.** `max_room_title_chars()`, following the existing `max_*` pattern
exactly.

**3. HTTP door.** `PATCH /api/rooms/{run_id}` accepting `title` and/or
`continues`. Returns what the web app needs to say what happened. The cycle
guard and the "parent must be filed under this uid" check live here.

**4. Web app.** An edit affordance on the room view for the title and the
continue-from link. Reuse what exists: the room view already has controls
(`docket-btn`) and the rail already renders groups (`renderDeleted` in
`web/shell.js` is the precedent for a grouped section). Do not invent a second
grouping mechanism.

**5. Rail grouping.** Chains render as groups. A single ungrouped room looks
exactly as it does today — a story of one room is not a group.

**6. MCP.** `delete_room`'s first call reports the count of rooms that continue
from this one. `get_room` and `list_rooms` carry `continues` in their payloads
so an agent can see the shape of a writer's workspace. **No new tool, no schema
change to `build_room`.**

## What "done" means

The repo's standing bar, from `docs/delete-brief.md`:

1. Items committed separately, declarative sentence-case subjects, no
   conventional-commit prefix, trailer
   `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
2. `.venv/Scripts/python.exe -m pytest -q` green and
   `.venv/Scripts/python.exe -m ruff check star tests scripts harness` clean —
   **checked by exit code, never by the tail of piped output.** A pipe hands
   the chain its last command's status, and that pushed a red `main` once.
3. Every behaviour change carries a test, and **every test is proven by
   reintroducing the bug it guards.** A first-pass green test is unverified.
4. No test asserts against the constant it is meant to pin.
5. Any count in reader-facing copy is derived or removed. `README.md` shipped
   "four tools and no fifth" for a day after a sixth landed; a count in prose
   is a second source of truth.
6. **A source assertion is not a live check.** Both halves of a cross-language
   contract passed while the wire between them was broken on 2026-08-12,
   because the Python test read `body["bible_coverage"]` and the JS test read
   `result.bible_coverage`. Anything that crosses that seam gets an assertion
   naming the other side's path, from whichever file already reads both.
7. Working copies are CRLF. Normalise line endings at read, or a pattern
   anchored to `\n` passes on one checkout and fails on another.
8. Nothing is deleted for real without a test proving what went with it.

## Explicitly out of scope

- Planner inheritance of era, entities or prior questions.
- Any change to `star/agents/planner.py` or `star/agents/synthesis.py`.
- Cross-room reads (`ask_hallway` or equivalent).
- Export, treatment-writing guidance, the demo video, the docs pass. Each is
  its own piece of work and none of them belong in this branch.
