# What is in `docs/`, and which of it is true today

Thirty-five files, two kinds. **Living documents** describe the app as it is now
and are corrected when it changes. **Dated records** are snapshots of a moment —
a review, a scope, a measurement — and are correct as written even where the app
has moved past them. Reading a dated record as current state is the one mistake
this index exists to prevent.

## Living — current as of `star-00065-v97`

| File | What it answers |
|---|---|
| `../README.md` | What STAR is, what it does, how to run it. The judged surface. |
| `RUNBOOK.md` | How to run, deploy, roll back, observe — and what bites. |
| `INFRASTRUCTURE.md` | The cloud project, billing, secrets, and why the scaling flags are load-bearing. |
| `smoke-2026-08-12.md` | The pre-demo walk. **Read its "Current as of" section first** — the steps are from the 12th, the deltas are current. |
| `spec.md`, `prd.md`, `scope.md` | The build's own specification. Largely current; predate the sweep and the year work. |
| `spec-oauth-as.md` | Why STAR issues its own tokens rather than accepting Google's. |
| `builder-profile.md` | Deadlines and working preferences. |

## Dated records — true when written, not corrected since

**Reviews and critiques.** `adversarial-review-2026-08-06.md`,
`judge-critique-2026-08-11.md` and its rounds 2 and 3. Findings from a moment;
many are fixed, some are not, and the documents do not say which.

**Scopes.** `scope-era-mismatch-2026-08-13.md` and
`scope-build-survival-2026-08-16.md`. Both carry their own outcome at the
bottom, including where the recommendation turned out to be wrong — which is the
useful half.

**Measurements.** `csv-review-2026-08-13.md`, `void-sweep-2026-08-14.md`,
`year-fix-verification-2026-08-13.md`. What a real run actually produced on a
given day.

**Agent briefs.** `agent-door-walk-2026-08-13.md`,
`agent-year-test-2026-08-13.md`. Prompts written to be handed to an agent, with
what came back appended.

**Build history.** `checklist.md`, `continuation-brief.md`, `delete-brief.md`,
`f-002-the-note-contract.md`, the `glow-*` briefs, `reflection.md`. The record of
how each piece got made.

**`HANDOFF.md` is stale and marked stale at the top.** It predates most of the
app. Kept because it records what the project believed about itself on day one.

## The rule

A dated filename means a snapshot. No date means it is maintained. If a
maintained document turns out to be wrong, **correct it** — the deploy of
2026-08-16 falsified a paragraph of `INFRASTRUCTURE.md` within the hour, and
shipping a fix without correcting what it falsified is how the next defect gets
made.
