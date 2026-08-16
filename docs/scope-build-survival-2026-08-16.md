# A build that does not survive a deploy — scope

> The second max-instances finding from `docs/RUNBOOK.md`. The daily cap half
> shipped as `e715d61`; this is the other one.

## The root is smaller than the symptom, again

"A deploy kills any build in flight" reads like nothing survives. Three things
already do, and they were built on purpose:

1. **The room document exists from the moment the build starts.** `_persist`
   runs at creation with status `running`, so Firestore holds the room before a
   single researcher has reported.
2. **`get_room` recovers a stranded run rather than spinning.** Stored as
   `running`, absent from `_runs` — the task did not survive a restart — and it
   is flipped to `interrupted` and says so once. `_store.mark_interrupted`
   even handles the room being deleted in the race.
3. **A check against an interrupted room is a supported case**, explicitly, and
   runs on fresh search alone. `check_scene` reads the live status rather than
   the stored one precisely so it refuses a build genuinely in flight and
   admits one that will never finish.

**So the failure is already visible, already named, and already has a
downstream story.** That is more than most of this week's defects started with.

## What is actually lost

**Every finding the build had already researched.**

`_persist` has five call sites: one at creation with `running`, and four
terminal — `complete`, `partial` twice, `error` twice. **Nothing writes between
them.** A build interrupted at ninety per cent files nothing, because the
document it wrote at creation is empty and the document that would carry
findings is only written at the end.

So the cost of a redeploy mid-build is:

- the searches already spent, gone
- a daily-cap slot spent, and now — correctly — **it stays spent**, because the
  cap persists as of `e715d61`
- a room the writer opens to find `interrupted` and nothing inside

The middle one is new. Before the cap persisted, a redeploy quietly refunded
the slot by resetting the counter. Fixing the cap made this finding sharper.

## Options

### A. Checkpoint findings as they land. *(recommended)*

Call `_persist(run, run_id, "running")` again each time a researcher category
files, rather than only at creation. An interrupted build then recovers with
whatever had actually been filed.

- **Cost:** one call in the right place inside `_execute`, plus one decision —
  whether a stranded run with findings recovers as `interrupted` or as
  `partial`. `partial` already means "stopped early, kept what was filed", the
  app already renders it, and `docs/HANDOFF.md` already describes it that way.
  It is likely the right answer and it is a judgement rather than a derivation.
- **Risk:** `_persist` uses `.set()`, which replaces the whole document. A
  mid-build write must carry everything the creation write did or it will erase
  fields. That is the one place this can go wrong quietly.
- **Validates without spending:** the suite already stubs researchers. A test
  can file two categories, drop the run out of `_runs`, and read the room back.

### B. Resume the run where it stopped.

Persist enough to continue the pipeline: which category was in flight, the ADK
session state, the ledger. This is the only option that makes a build genuinely
survive a deploy rather than degrade gracefully.

**Days, not hours**, and it touches the most load-bearing path in the app.
`_start_build` already has half the shape, which is exactly what makes it
tempting and exactly why it should wait for a week nobody has before Sep 7.

### C. Refund the cap slot when a run is marked interrupted.

Two lines, orthogonal to both. It does not save the work; it stops charging for
work that was destroyed. Worth doing **whichever of A or B happens**, and worth
doing even if neither does.

## Recommendation

**A now, C alongside it, B after the hackathon.**

A turns "lost everything" into "kept what was filed", which is a status this app
already has a word, a renderer and a docstring for. C is small and stops a
writer paying for a room the department threw away. B is the honest fix and it
is architecture.

## What A does not fix, stated plainly

A build interrupted **before its first category files** still recovers empty,
because there is nothing to checkpoint yet. The window is smaller, not closed.
And the searches spent inside the interrupted category are still gone — a
checkpoint is per category, not per search.

## Before building any of it

One thing needs verifying rather than assuming, and it is the risk named in A:
**what exactly `_persist` writes at creation versus at a terminal status.** If
the creation document is a subset, a mid-build `.set()` is safe; if the terminal
write adds fields the creation write omits, a checkpoint could erase on the way
past. That is a read of one function, and it decides whether A is one line or
three.
