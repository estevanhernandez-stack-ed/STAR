# F-002 — the note contract, and the one decision behind it

**Status:** blocked on one call. Everything below is measured; the recommendation
at the end is mine, and the question is one sentence.

**Register row:** `F-002` in
[`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md).

## What F-002 says, and why it cannot be built as written

The row proposes cutting `VERDICT_READING` from a paragraph to a slug beside the
stamp, so the answer outranks the gloss on it. On the Sony Walkman card that is
plainly right: the gloss is 2x the answer's height and says nothing a stamp does
not already say.

But **four of the nine claims in the filed Gdansk check carry no note at all** —
every one of them `confirmed`. On those four, that sentence is the only prose the
card has. Demote it with nothing to promote in its place and the card becomes a
stamp, a three-word slug, and a quotation.

So the row's own precondition — "`verdicts.py:91` requires a note only for
`unverifiable`" — is not a hole to close before building. It is the main case.

## What the pipeline actually intends

This is the part that was not in the register, and it changes the question.

`star/agents/script_check.py:196-199` instructs the verifier, in as many words:

> A note is required on every unverifiable line, and it must say what you looked
> for and did not find. An unverifiable line with an empty note is a line that
> fails to parse and is discarded. **On confirmed and anachronism the note is
> optional** — use it for the qualifier a writer needs, the year the thing
> actually arrives or the place it belongs.

That is not an oversight. **The note was designed as an optional qualifier, not
as the answer.** The pipeline's model of a card is: the verdict is the answer,
the sources are the evidence, and the note adds a qualifier when there is one to
add. The card's current layout assumes the opposite — that the note is the
answer — and that mismatch is the real defect F-002 is circling.

## What was measured

One filed check, nine claims. Small, and stated as such.

| verdict | claims | with a note | without |
|---|---|---|---|
| `confirmed` | 7 | 3 | **4** |
| `anachronism` | 2 | **2** | 0 |

**Every no-note claim carries 2 citations.** None is an empty card.

Both anachronisms got notes, which fits the prompt's own framing: an anachronism
needs the qualifier ("first model released July 1979"), a confirmation often does
not.

**How well the evidence stands in for a note, on those four:** only 1 of 4 has an
excerpt containing the claim's own words by a naive substring match. That test is
crude and understates the case — the sources are Polish and inflected, so `zloty`
against `tysiączłotówka` fails a match a reader would make instantly. Read by
hand, the four range from self-evident to requiring inference:

- `LENIN SHIPYARD` — the source names the gate directly. Self-evident.
- `spirit duplicator` — the source describes KOR bulletins printed on one. Close.
- `zloty` — the source describes a 1000-złoty note. Close.
- `SPOLEM STORE` — the source is about sugar ration cards. **The reader connects
  it themselves.**

## What wave 4 changed about this

Before wave 4, a no-note card fell back to ~2,900 characters of raw scraped
markdown, so "let the sources carry it" was not an option — there was nothing
readable to fall back to.

After wave 4 the same card falls back to a clean 250-character quotation. The
Lenin Shipyard card now reads:

> **CONFIRMED** · LENIN SHIPYARD
> "The Gate No. 2 of the Gdańsk Shipyard (Brama nr 2 Stoczni Gdańskiej) is one of
> the gates leading into Gdańsk Shipyard…"

That is a real answer. It was not available a day ago, and it is why this
decision is worth making now rather than when the row was filed.

## The options, with what each costs

**A — require a note for every verdict (`star/verdicts.py:91`).**
Rejected, and not close. It contradicts an explicit, reasoned instruction in the
verifier prompt, and the failure mode is bad: `_parse_line` returning `None`
means the claim comes back **`unverifiable`**. So a confirmed claim the model
simply did not annotate would be restamped as unsettled. That trades four quiet
cards for four false verdicts, and false verdicts are the one thing this app is
built not to produce.

**B — ask the prompt for a note more often.**
Cheap, no contract change, no parse risk. But it is a nudge, not a guarantee: the
card still needs a designed no-note state, so this cannot be the whole answer. It
is worth doing **as well**, never **instead**.

**C — build the card the pipeline actually describes.**
Accept that the verdict is the answer and the sources are the evidence. Demote
`VERDICT_READING` to a slug, let the quotation do the work it can now do, and
design the no-note card deliberately rather than papering it with a generic
sentence. Frontend only. Reversible. Touches no contract.

## Recommendation

**C, plus B as a follow-on.** The pipeline already decided this question and wrote
the decision into the prompt; the card is the thing that never honoured it. Wave 4
made the fallback good enough for that to be true rather than merely principled.

Two things wave 5 must not skip:

1. **The no-note card needs its own design, not an absence.** The `SPOLEM STORE`
   case is the honest test: a source about ration cards, a claim about a store,
   and nothing stating the link. A slug reading "as read from the sources below"
   is doing real work there and must survive the demotion.
2. **`REASON_LINE` still has no slot** in the proposed order, and on a
   budget-exhausted claim it is the whole answer. The row flags this and it is
   still true.

## The question

**Should a `confirmed` verdict owe the reader a sentence, or is the source
quotation the answer?**

My read: the source is the answer, the prompt already says so, and the card
should stop pretending otherwise. Say "C" and wave 5 is a frontend wave with no
contract risk. Say "A" and it becomes a backend wave that needs a live run
measured before a line is written.
