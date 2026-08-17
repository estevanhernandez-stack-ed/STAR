# The council on the citation defect, checked

Eleven agents, four investigative lenses, a synthesis pass and two adversarial
refuters per candidate. Read alongside
[the rate measurement](scope-citation-rate-2026-08-17.md), which was taken
independently and first.

**Outcome: all three candidates drew two refutations and no defence. Nothing is
safe to ship before the 2026-08-22 shoot.** That is a real result, not a failure
of the exercise — two of the three refutations are that the fix has already been
tried in this repo and measured at zero or negative effect.

## The root cause, verified verbatim

The verdict and the citation are produced in one step but only the verdict is
constrained. The sole rule governing the sources field is a **SEEN** test, never
a **SUPPORTS** test.

[`star/agents/script_check.py:311-313`](../star/agents/script_check.py#L311-L313):

> In the sources field list only URLs you actually saw, either in `<room_files>`
> or in a parallel_search result you received — never a URL you did not see, and
> never a title or an excerpt of your own.

Nothing in it ties a URL to the claim above it. Reinforcing it,
[`star/tools/parallel_search.py:157`](../star/tools/parallel_search.py#L157)
ships an unqualified imperative inside the ADK tool declaration, which means it
is in every request: *"Cite these by URL in your findings."*

And nothing downstream can catch the result.
[`star/verdicts.py:275`](../star/verdicts.py#L275) downgrades only when **every**
URL fails to resolve. A wrong-but-genuinely-seen URL always resolves.

I checked all four strings against the files. All four are accurate.

The council's strongest measurement, which I reproduced: on rows where the cited
page never mentions the claim, the model's own note shares a **median 0.00** of
its content words with that page and 55% share none at all; where the page does
mention it, median 0.48 and 7% share none. **The note is written first, from
memory, and a URL is attached afterwards.**

## A second producer, under the same symptom

[`star/findings.py:139-140`](../star/findings.py#L139-L140):

```python
if len(excerpts) == 1:
    return excerpts[0]
```

A sole excerpt is returned unscored, so one stored passage prints under every
claim citing that URL. Measured in the exports: `Casbah_Coffee_Club` carries 20
claims on 1 distinct excerpt.

This matters for sequencing. A fix to the prompt cannot reach it, and a fix here
cannot reach the prompt. Two producers, one symptom.

## Where the council was wrong

Its own reconciliation pass caught two of its lenses contradicting each other and
resolved both correctly, including catching a lens that misattributed a quote
from `docs/f-002-the-note-contract.md` to disqualify an option that document
never discusses. That is the exercise working.

Two things it got wrong that survived to the final report:

**The headline example is fabricated.** The report's most emphasised finding —
called "the structural finding no lens reported" — rests on a row reading
`Long Tall Sally` cited to `Voyager_Golden_Record`, marked by the writer as
"Best catch in the sweep." **That row does not exist in any export.** What
exists is close to its inverse: `GOLDEN RECORD`, `Voyager`, and `Carrying music.`
are all *confirmed* and all cited to the catch-all Hamburg page.

**A refutation misattributes a commit.** It claims capping a model-facing
evidence list "was tried and measurement killed it in 54 minutes," citing
`6c5e582`. That commit is real but is titled *Bound the run so synthesis cannot
generate forever*, and `max_sources_per_category` is alive today at
[`star/config.py:360`](../star/config.py#L360), used in two places. Treat that
refutation as unproven.

**The conclusion those errors were supporting is nevertheless true**, which is
why it took measuring rather than arguing. A correct anachronism receipt *can* be
lexically zero-overlap, and the proof is the video's own centrepiece:

> `He was seventeen.` cited to *21 November 1960: George Harrison is deported
> from Germany*. Zero content words shared. The receipt is right — it proves
> Harrison was under 18 in late 1960 — and a naive gate would strike it.

Measured across the whole-book sweep: **38% of confirmed rows are zero-overlap,
against 14% of anachronisms.** Six anachronism rows are zero-overlap; five are
genuinely weak receipts and the sixth is the best row in the sweep. Any gate must
be confirmed-only, and even then it cannot be allowed to change a verdict.

## Why each candidate died

1. **Bind the sources field to SUPPORTS in the prompt.** Refuted, and the
   refutation checks out: [`script_check.py:314`](../star/agents/script_check.py#L314)
   *already* reads "Leave the sources field empty when a claim has no source."
   It has been there since the commit that created Pipeline B and has never been
   edited. The candidate's active ingredient is not the word *supports*, it is
   persuading the desk to leave the field empty — which is already instructed,
   one clause to the right of the string it wants to replace, and measured at
   zero effect.

2. **Compute the support score and flag it.** Refuted by the repo's own record:
   [`star/mcp/tools.py:1713`](../star/mcp/tools.py#L1713) says in capitals
   *"OVERLAP ALONE IS NOT BEARING, WHICH IS WHAT THIS FUNCTION USED TO ASSUME."*
   The same `_tokenize`, the same shared-token count, already shipped as a
   relevance gate, failed live, and was torn out in `210ce8d`.

3. **Rank and cap the room-files block.** Highest risk and the only candidate
   that can make *verdicts* worse rather than just receipts. Not five days before
   a shoot.

## The one free win

The diagnostic half of candidate 3 is true and worth taking on its own.
[`_chain_files`](../star/server.py#L1765-L1767) states that "the verifier reads
top down under a size ceiling and the room a writer is working in should never be
the part that gets cut." **There is no ceiling.** `_room_files` emits every cited
finding and its full excerpt with no cap, no slice and no knob. Two other places
assert the same false ceiling.

Correcting that prose changes no behaviour and costs nothing. It is the same
class of defect as the one that falsified `INFRASTRUCTURE.md` within an hour of
its own fix.

## A fourth direction the council did not consider

All three candidates target the citation step. The rate measurement points
somewhere upstream that none of the three refutations touch.

**88% of confirmed claims are bare nouns** — `Hamburg`, `Vespa`, `G-sharp`,
`The Elbe.` — and **26 of the 30 confirmed rows citing a heavily-reused page are
those nouns**. No page on the web says Hamburg existed in 1958. There is no
search that settles it and no receipt that could ever be right.

So do not fix the footnote. **Remove the row.** A claim no source could settle is
not a claim.

This is strictly better than flagging: the row disappears rather than becoming an
unverifiable, so it is the only direction that does *not* inflate the
unverifiable count the other candidates all raise. It shrinks the sweep and every
surviving row means something.

Stated plainly: this is mine, not the council's, and it has not been through the
adversarial pass. It changes extractor behaviour, so it needs one live sweep to
validate — the same cost as candidate 1, and the same answer on timing.

## Recommendation

**Do not ship a citation fix before the shoot.** Two of three candidates are
already-tried-and-failed, the third can degrade verdicts, and the fourth is
untested. Five days is not enough to validate any of them, and every one of them
needs a live sweep to prove out.

Before 2026-08-22, do only this:

- Correct the three false size-ceiling docstrings. No behaviour change.
- Pick shot 5's row off the verified-supported list, or use an anachronism.

After the shoot there are fourteen clear days to 2026-09-05. That is enough for
the extractor change plus one live sweep to measure it, with the fallback of
shipping nothing and disclosing the limitation — which is a defensible position
for a tool whose entire pitch is that it tells you what it could *not* settle.
