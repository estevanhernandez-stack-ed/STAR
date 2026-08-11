# Glow wave 5 — the answer outranks the gloss

**Branch:** `glow/wave-5-the-answer-outranks-the-gloss`
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md)
**Decision behind it:** [`f-002-the-note-contract.md`](f-002-the-note-contract.md)

One finding, `F-002`, the highest-ranked row left. It was blocked for two waves
on a question only the builder could answer, answered 2026-08-11:

> **The source quote is the answer.**

That is option C in the decision doc: frontend only, no contract change. It also
matches what `star/agents/script_check.py:196-199` already tells the verifier —
the note is an optional qualifier, never the answer.

## What the card becomes

Current order, and the defect: stamp, claim, `VERDICT_READING`, note,
`REASON_LINE`, `VERDICT_SCOPE`, then the citations. The one thing the reader came
for renders fourth at best and not at all on 4 of 9 real cards, while two
paragraphs of standing prose rank above the evidence.

Target order:

1. **`.rail-head`** — stamp, **slug**, claim type.
2. **`.rail-claim`** — the line, quoted back.
3. **note**, when there is one. Now genuinely a qualifier.
4. **`REASON_LINE`**, when there is one.
5. **"What answered it" + the citations** — the answer.
6. **`.rail-caveat`** — moved below the evidence it describes.

## Build

**1. `VERDICT_READING` becomes `VERDICT_SLUG`, rendered in the head.**

- `confirmed` → `as read from the sources below`
- `anachronism` → `out of period for the sources below`
- `unverifiable` → `not settled`

Rule 11's own test licenses this: strike every verb from "The department read
this line as supported by the sources below" and it says the same thing, so it
was a mark all along.

**The quantifier trap does not apply here, and the reason is a mechanism rather
than a hope.** `star/verdicts.py:275-277` downgrades any `confirmed` or
`anachronism` with no citations to `unverifiable`, so those two verdicts always
carry at least one source and "the sources below" asserts nothing unbacked. The
`unverifiable` slug makes no claim about sources at all, which is the case that
can legitimately have none. Cite this in the code — a later reader must not have
to re-derive it, and the amendment "a mark has no quantifier" exists precisely
because the intake once shipped this mistake.

**2. `.rail-caveat` moves below the citation list.**

Rule 10 is answer-over-disclaimer, and once the source quote IS the answer, 84px
of standing caveat above it is the violation restated. Both sentences survive the
move — **the second one cannot be cut.** `scriptcheck.js:154-157` argues it
carries rule 2's click-through beat, and rule 9's table records that an earlier
relocation was rejected for dropping exactly that clause. Reword only the
direction word: "Each source below" no longer points anywhere useful once the
paragraph sits underneath the list.

The stamp is still scoped, which is the constraint the file header names: the
slug beside it carries "the department's reading of the sources", so no card
renders a stamp with no scope on it.

**3. The no-citation card keeps the caveat where it is.** There is no list for it
to follow, and `VERDICT_SCOPE_NO_SOURCES` is written for that case. Do not move
what has nothing to move below.

## Out of scope

The four claims with no note are **not** a defect to fix here. That was the
decision: the source answers them. Do not invent a sentence to fill the gap, and
do not touch `star/verdicts.py` or the verifier prompt in this wave — raising the
note rate is a separate, promptside change with its own measurement.

## What "done" means

1. Committed in the repo's voice, tests in the repo's own framework, every test
   proven by reintroducing the bug it guards.
2. `python -m pytest -q` green, `ruff check star tests scripts harness` clean.
3. **Re-measure the same nine cards.** The finding was filed on proportions and
   closes on proportions: state the answer's share of the card before and after,
   and state plainly that "the answer" now means the quotation.
4. No new dependency, no build step, no CDN.
