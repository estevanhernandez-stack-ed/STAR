# Room delete — the brief

**Branch:** `feat/room-delete`
**Decided:** 2026-08-11. Option **B** (two-call handshake) carrying **C**'s
reversibility, with a real purge at the end so a workspace actually gets clean.

This file is authoritative and supersedes `docs/spec.md` for this feature. Where
it and a row in any register disagree, this file is right.

## The shape, in one paragraph

Deleting a room takes it out of the writer's sight immediately, keeps it
recoverable for a window, and then genuinely destroys it. Over MCP it takes two
calls: the first says what will be lost and hands back a one-time token, the
second spends that token. In the web app it takes two presses, the same arm-then-
confirm the check delete already ships. Restore lives in the web app only,
because coming back from a delete is a person's decision.

## Why this shape

The app already deletes exactly one thing, and `web/scriptcheck.js:708-714`
argues the pattern on the record: *"Two clicks, not one. The first arms and says
exactly what goes; the second does it… Nothing is hidden behind a browser dialog:
the warning is on the page, in the department's own voice."* The store's
`delete_scene` is a **hard** delete.

An agent has no eyes and no pause, so "press twice" is just "call twice" and
protects nothing. The two-call handshake is the translation that survives: the
first call puts *what is about to be destroyed* into the agent's context, in the
department's voice, which is what "the warning is on the page" means when the
reader is a model.

And this app's whole posture is that nothing is thrown away — unsourced URLs are
stamped rather than dropped, unparseable lines become field notes, a partial
build keeps what it filed. A hard irreversible delete reached first by an agent
is out of character. But an archive that never empties is not a delete, and the
builder's instruction is explicit that a workspace has to actually get clean. So:
reversible for a window, then real.

## Decisions already made — build these, do not re-litigate

1. **Soft delete is a `deleted_at` timestamp on the room document.** Not a move
   to another collection: a move is two writes that can half-fail and would
   strand the `scenes` subcollection, and `list_rooms` already streams and
   filters in Python.
2. **Retention is 30 days**, as `config.room_retention_days()` with an env
   override, following the existing `config.max_*` pattern exactly.
3. **Purge is lazy, on `list_rooms`.** Any room whose `deleted_at` is older than
   the window is hard-deleted — document *and* its `scenes` subcollection — when
   its owner next lists. Precedent: `_evict_old_runs` already evicts in-memory
   runs lazily rather than on a schedule, and Cloud Run runs `--min-instances=1`
   with no scheduler. A writer who never lists never purges; that is acceptable
   and must be **said in the code**, not hidden.
4. **A deleted room leaves `list_rooms` immediately.** That is what makes the
   workspace clean, and it is the half the builder asked for most plainly.
5. **`get_room` on a deleted room returns it** with `status: "deleted"`, the
   `deleted_at`, the day it purges, and how to restore. It does **not** 404: the
   information is retained during the window and pretending otherwise would be
   the app lying about what it still holds.
6. **Restore is web-app only.** No sixth MCP tool. This matches the sentence the
   app already ships about scenes — *"stays there until it is deleted from the
   web app"* — and keeps coming back from a delete a person's decision.
7. **`rooms:delete` is its own scope.** A reader granting read and write does not
   grant delete. The consent screen gets its own block for it.
8. **The web app gets room delete in the same change.** Shipping it on the agent
   door first would hand an agent a power the person does not have, which is the
   objection that blocked this feature in the first place.

## Build

**1. Store.** `soft_delete_room`, `restore_room`, `purge_expired_rooms`, and a
hard `purge_room` that removes the document and its scenes. `list_rooms` filters
`deleted_at` and calls the purge. `delete_scene`'s docstring is the model for how
these explain themselves — read it before writing them.

**2. Config.** `room_retention_days()`, default 30.

**3. HTTP door.** `DELETE /api/rooms/{run_id}` (soft), `POST
/api/rooms/{run_id}/restore`. Both return what the web app needs to say what
happened. Ownership is by path construction (`users/{uid}/rooms/...`), the way
`delete_scene` already gets it, not by an ownership check.

**4. Web app.** A room delete control, two-press armed, in the department's
voice, naming exactly what goes — findings, sources, searches spent, the checks
filed against it — and that it is recoverable for N days. Reuse the check
delete's arming pattern; do not invent a second one. A restore affordance for
rooms inside the window.

**5. MCP.** `delete_room` with `run_id` and optional `confirm`.
   - Without `confirm`: destroys nothing. Returns what will be lost, in counts,
     plus a one-time token and the fact that the room is recoverable for N days.
   - With `confirm`: spends the token, soft-deletes, says when it purges.
   - Tokens are per-uid, per-room, single-use, ~10 minutes, in memory. A restart
     loses pending confirms and the agent simply calls again; say so.
   - A wrong, stale or reused token is refused **by name**, with what to do next,
     per this file's first rule.

**6. Scope and consent.** `rooms:delete` in the scope table; a consent block that
says plainly what it grants — including that a delete is recoverable for N days
and permanent after. **The existing sentence "No call the department offers here
deletes a room, a check, or a scene" becomes false the moment this ships and must
be rewritten**, not left to drift.

## What "done" means

1. Items committed separately, declarative sentence-case subjects, no
   conventional-commit prefix, `Co-Authored-By: Claude Opus 5 (1M context)
   <noreply@anthropic.com>`.
2. `python -m pytest -q` green and `ruff check star tests scripts harness` clean
   — **checked by exit code, never by the tail of piped output.** A pipe hands
   the chain its last command's status, and that shipped a red `main` today.
3. Every behaviour change carries a test, and **every test is proven by
   reintroducing the bug it guards.** Four separate tests in the last campaign
   passed against broken code; assume a first-pass green test is unverified.
4. No test may assert against the constant it is meant to pin. A cap test that
   reads `_ASK_LIMIT` moves with it and guards nothing.
5. Any count stated in reader-facing copy must be derived, or removed. The
   consent screen said "four calls" in a language that cannot see the Python
   list, and shipped false the day a fifth tool landed.
6. Nothing is deleted for real without a test proving the scenes subcollection
   went with it.
