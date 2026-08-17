# How often does a confirmed row cite a page that does not hold it up

Measured 2026-08-17 against filed sweep exports, no live runs. The question that
prompted it: one bad receipt in 200 is fine, one in 100 is liveable, one in 20
is not shippable on a tool whose product is the receipt.

**The answer is worse than one in twenty. It is about two in five — but only on
one class of row, and not the class the video uses.**

## The number

Unit of measurement is the finding a writer sees: one claim, in one scene, with
however many sources it cited. The same sentence checked against two scene years
is two findings, because it is two rows and can carry two verdicts.

Source: the whole-book sweep of *The Beat That Shook The Void*, `5b55e5c16c88`,
127 findings over 31 scenes. This is the post-era-fix run and the one whose rows
would appear on camera.

| Verdict | Findings | Receipt does not support the claim |
|---|---|---|
| confirmed | 73 | **29 (40%)**, plus 10 borderline |
| anachronism | 43 | 2 of the first 11 read, both weak rather than wrong |
| unverifiable | 11 | n/a — carries no citation by design |

Every confirmed finding had at least one citation. None were unsourced. The
failure is never a missing receipt; it is always a receipt for something else.

Judgement was mine, claim by claim, reading the excerpt against the note. The
strict test: does the cited page hold up *this* claim, in *this* year? A page
about the right city that never mentions the thing asserted counts as
unsupported. Ten findings sat close enough to the line to be listed separately
rather than counted either way.

## The asymmetry, which is the actual finding

**Anachronisms cite well. Confirmations cite badly.** That is not luck, and it is
not two defects.

An anachronism is an assertion that requires a date to make. To flag the Casbah
in 1958 the desk has to find a page saying the Casbah opened in August 1959 — so
a search runs, a dated page comes back, and the receipt is the page that decided
the verdict. The Casbah rows cite the Casbah's own Wikipedia entry with `Opened
29 August 1959` in the excerpt. `'Candid Camera'` cites the IMDb page saying the
UK version reached British television in 1960. `He was seventeen.` cites the
Beatles Bible page on Harrison's 1960 deportation for being under 18.

A confirmation of a bare noun requires nothing. **No page on the web says Hamburg
existed in 1958.** So there is no search that settles it, no page that decided
it, and the citation slot still has to be filled.

## Why the slot has to be filled

[`star/verdicts.py:275`](../star/verdicts.py#L275):

```python
if verdict in _NEEDS_A_SOURCE and not citations:
    verdict = Verdict.UNVERIFIABLE.value
```

A `confirmed` whose URLs do not resolve against the ledger is downgraded. The
intent is right and the comment above it says so: a stamp with nothing behind it
is the overclaim the ledger exists to prevent.

The consequence is the defect. To return `confirmed` at all, a URL from the
ledger must be named. The run's ledger held **35 distinct pages** for 127
findings. So a claim with no page behind it does not come back unverifiable — it
comes back confirmed, citing whichever of the 35 was nearest.

**The guard against unsourced confirmation manufactures mis-sourced
confirmation.** It converts an honest "could not settle this" into a
confident-looking row with a footnote pointing somewhere else.

## Both halves are mechanically visible

Neither of these needs a judgement call to see.

**One page carries 25 unrelated claims.** `The Beatles in Hamburg` on Wikipedia
is the cited source for `Dingle` (a Liverpool district), `Judea`, `Liverpudlian`,
`Export beer`, `Schließung`, `Störung`, and `two years and four hundred miles`.
Thirty-five pages carry 142 claim-source pairs between them.

**88% of confirmed claims are bare nouns.** Four words or fewer, no digits:
`Hamburg`, `Liverpool`, `Vespa`, `G-sharp`, `Reeperbahn`, `The Elbe.`. Against
70% for anachronisms.

And they are the same rows. Of the 30 confirmed findings citing a page reused
four or more times, **26 are bare-noun claims**.

## What follows

The bad receipts are concentrated in rows that should never have been rows. The
extractor is emitting scenery as claims, the verifier cannot decline them because
declining costs it the verdict, and the ledger is too small to give each one an
honest page.

Two levers, in order of how much they move:

1. **Stop extracting unfalsifiable nouns.** A claim no source could ever settle
   is not a claim. This removes the row rather than fixing its footnote, and by
   the count above it is where 26 of 30 bad receipts live.
2. **Make `unverifiable` the honest landing spot it was meant to be.** Right now
   the incentive runs the other way: naming a wrong page keeps the verdict,
   naming none loses it. A claim whose best available page does not address it
   should come back unsettled and say so.

Neither is an architecture change. Both are cheaper than they look because the
volume being removed is noise.

## For the shoot

**The demo rows are clean.** Verified individually, not assumed:

- `He was seventeen.` — Beatles Bible, Harrison deported November 1960 for being
  under 18. Holds.
- The Casbah cluster — Casbah Coffee Club Wikipedia, `Opened 29 August 1959`, and
  the Beatles Bible entry for the opening night. Holds.

Shot 9 is safe as planned. **Shot 5 is the exposure**: it opens a drawer on one
finding and its source. If that finding is a confirmation, it is a coin flip a
little worse than even. Pick an anachronism, or pick a confirmation off this
document's supported list, and check it on the day.

The video-plan warning already said an unchecked confirmation is a coin flip.
That was a guess and it was roughly right.
