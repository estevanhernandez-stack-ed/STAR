# Continuation — the brief

**Status:** proposal. Nothing here is built, and the decisions below are marked
as either settled by evidence or **open — the builder's call**. This file
follows `docs/delete-brief.md`'s shape but has not yet earned its authority:
`delete-brief.md` was written after a decision, this one is written to inform
one.

**Deadline context:** hard deadline Sun 2026-09-07, 2:00 PM PT. 26 days at
writing. That is the constraint the sequencing at the end is written against.

## The shape, in one paragraph

A room can name the room it continues from. The second room inherits the first
one's era and entities, so its treatment can be a sentence rather than a page,
and its planner is shown what has already been answered and told to go narrower
rather than wider. The hallway — a story's whole body of research — is then
**derived** from the chain of those links, not modelled as a container. No new
collection, no new scope, no folder to maintain.

## The evidence this is written from

Room `dcdd9dad6a1f` (The Substitute Sync, 2026-08-12, 19 searches, 103 sources)
built against a real treatment for a real screenplay, and compared against
research its writer had already done by hand.

Two things came out of that comparison, and they point the same way.

**The wide room answers at the scale of its treatment.** The treatment named
cities, so findings came back at city scale: Copenhagen, the Netherlands, Hong
Kong, Adelaide. It did not describe the Princess Theatre, Festival Hall, or the
hotel where the climax is set, because nothing asked it to.

**The wide room produced the list of narrow rooms.** Without being asked, it
surfaced KB Hallen, Veilinghal Op Hoop Van Zegen, Centennial Hall, Adelaide Town
Hall, Kai Tak and the Royal Hotel. The buildings a writer needs next are already
in the first room's findings.

So this is not primarily a deduplication feature, which is how it was first
described in conversation. It is **scope inheritance**. The second room is not
"the first room minus what we know"; it is the first room's answers used as the
frame for a smaller question. That distinction decides the design: dedup argues
for diffing findings, inheritance argues for passing the profile forward and
letting the planner narrow.

## Decisions this brief proposes

1. **`continues` is a single parent `run_id` on the room document.** One parent,
   not a set. A tree, not a graph. The hallway is the connected component, and
   a single parent keeps that walk trivial and acyclic. A story that genuinely
   branches gets two children of the same parent, which is the same thing a
   writer means by it.
2. **The hallway is derived, never authored.** There is no hallway document, no
   name, no membership list. This follows the rule the bible mark was rewritten
   under on 2026-08-11: a mark is derived, never authored. A container would be
   a second source of truth for something the links already say.
3. **`build_room` takes an optional `continues`.** Schema-driven validation
   through `_arguments`, the way `shape` and `category` already work. The web
   app offers it as "continue from" on an existing room.
4. **Inheritance is of the story profile, not the findings.** The child run
   seeds intake with the parent's `era`, `genre` and `key_entities` so a
   one-sentence treatment produces a full profile. Findings are NOT copied: a
   child room owns only what it researched, or the provenance of every citation
   becomes a lie.
5. **The planner is shown the parent's questions and told to go narrower.** Not
   the parent's findings — the questions. They are short, they are already the
   right shape, and they are what "do not ask this again" is actually about.
6. **A parent that no longer exists degrades honestly.** Rooms soft-delete and
   purge after `config.room_retention_days()`. A child whose parent is gone says
   "continues from a room that is no longer filed" and works. It does not break,
   and it does not silently drop the inheritance without saying so.
7. **Deleting a parent does not delete its children.** A room's delete already
   cascades to its scenes; extending that to children would let one confirmation
   destroy a body of work the caller never named. `delete_room`'s first call
   must say how many rooms continue from this one.

## Open — the builder's call

- **Does a child inherit the parent's daily-cap treatment?** A narrow room
  should cost less. If it does not, a five-room hallway costs five full builds
  and the feature is a luxury rather than a saving. Worth measuring before
  promising.
- **Is `continues` offered over MCP at all in the first cut?** The web app is
  where a writer decides a story has a spine. An agent proposing a continuation
  is a different, larger idea.
- **Does the rail group by hallway, or stay flat with a marker?** Grouping is
  more useful and touches more of `web/shell.js` than anything else here.

## The risk that decides whether this is good

**The planner may under-research a new subject because a superficially similar
question was answered for a different one.** "What did the venue's stage look
like" answered for KB Hallen in Copenhagen must not suppress the same question
for Festival Hall in Melbourne. This is the whole feature failing quietly, in
the direction that is hardest to notice: the room comes back looking fine and is
thinner than it should be.

That needs a real test, not a hope. The honest one is a measurement, not an
assertion: build a child room with and without the parent's questions in the
planner prompt, and compare finding counts and source overlap per drawer. If
the inherited run files materially fewer findings in a drawer the parent also
covered, the prompt is suppressing rather than narrowing, and the feature is
wrong as designed.

## Build

**1. Store.** `continues` on the room document; `document_to_room` carries it.
`room_summary` carries it too, or the rail cannot group without reading every
room whole.

**2. Server.** `build_room` accepts `continues`, validates the parent is filed
under the same uid by path construction (the way `delete_scene` gets ownership,
not by an ownership check), and seeds the child's session state with the
parent's profile and questions.

**3. Planner.** One paragraph in the instruction: here is what a previous pass
already asked, go narrower, do not repeat. Built from state, with the `?`
suffix ADK needs so a run with no parent renders it empty rather than raising —
the same guard `star/agents/synthesis.py` documents at length.

**4. MCP.** `continues` on `build_room`'s schema if it ships to the door at all,
and `get_room` reports the link in its plain-language line rather than only in
the payload.

**5. Web app.** "Continue from" on the intake, defaulting to the room the writer
just came from. Rail grouping if it is in scope.

**6. Copy.** The consent screen and the tool descriptions both state what a
build costs. If a child build costs less, that has to be derived, not asserted.

## What "done" means

Same bar as `docs/delete-brief.md`, which is the repo's standing bar:

1. Items committed separately, declarative sentence-case subjects, no
   conventional-commit prefix, `Co-Authored-By` trailer.
2. `pytest -q` green and `ruff check star tests scripts harness` clean, both
   **checked by exit code**, never by the tail of piped output.
3. Every behaviour change carries a test, and **every test is proven by
   reintroducing the bug it guards.**
4. No test asserts against the constant it is meant to pin.
5. Any count in reader-facing copy is derived or removed.
6. The suppression risk above is settled by measurement against a real room
   before the feature is called done.

## Sequencing

The treatment guidance is separable and worth shipping first regardless of what
happens to this: it is copy, it takes hours, and it improves every build made
between now and the deadline. It is also the cheaper half of the same insight —
a treatment is only as good as the six fields intake extracts from it, and
nothing in the app says so.

This feature is a week if the rail grouping is in scope and closer to two days
if it is not. Against 26 days with export and the adoption items still open,
the honest question is whether a hallway beats a markdown export for a judge who
has already named reach and lifecycle as the remaining objections.
