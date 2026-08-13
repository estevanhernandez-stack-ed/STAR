# The three CSVs, read — 2026-08-13

> Against `star-00046-zjs`. The two research files are clean. The sweep file
> has a defect worth a decision before the video, and it is a defect the export
> made visible rather than one the export caused.

## Which file imports

**Only the sweep file.** `doctor-who-liverpool-and-hamburg-special-sweep-2026-08-13.csv`.

The import path files a writer's marks against a *sweep* — it matches rows on
the `claim` column and writes `writer_note` and `dismissed` onto claims in a
filed sweep. A research export has no claims in it, so there is nothing for it
to match and no room-level import to match against. The two research files are
for reading, sorting and sending; they do not come back.

The file you already downloaded still imports. It predates the page-order
change and has no `scene` column, and the import never needed one. Re-download
if you want the new shape.

### How to import it

1. Open the room → **Check the script**.
2. Under **Draft sweeps filed on this room**, press the sweep. The import panel
   only appears once a sweep is open, and it files into *that* sweep.
3. In the spreadsheet, add a **`writer_note`** column and type into it. Add
   **`dismissed`** and put `yes` on any row you want struck. Those two columns
   are the only ones that come back; every other edit is ignored and named.
4. Save as CSV.
5. Below the results: **"Marked the export up in a spreadsheet? Bring it back."**
   Choose the file → **Read the file**.
6. That first press **changes nothing**. It tells you how many claims would
   take a note, names any claim the file mentions that the sweep does not hold,
   and names any column you edited that the department writes. The button
   re-labels itself to **File these notes** — that re-label is the arming.
7. Press it again to file.

A claim that appears in three scenes is now three rows. Type the note on any
one of them; it lands on the claim once. Notes typed on two rows of the same
claim are joined, not overwritten.

**Changed since you last read this:** the "you edited the department's columns"
complaint used to fire on *every* annotated row, because an unmodified export
carries a verdict and a source on every row and the check could only see that
they were present. It now fires only when a value comes back that the sweep
never wrote. A url that moved rows because you sorted the file is not a change.

## The sweep file: 23 of 61 rows cite a page that does not support them

Every one of these rows carries the same source, and it is the same excerpt
each time — a passage about a minibus being craned onto a ferry at Harwich:

> The group were to be paid about … Williams drove the group and their
> equipment in his Austin J4 minibus which was loaded by crane onto a ferry at
> Harwich on 16 August 1960 …

It is attached to `horn-rimmed glasses`, `technicolor`, `Jaffa Cake`,
`Taj Mahal`, `Empire`, `Raunchy`, `G-sharp`, `Ta`, `1960`, `Top Ten`, `Macca`,
`head on a stick`, `DALEK`, `Do not pass Go`, `April. Judea.`, `One After 909`,
`Some Other Guy`, `vinyl records`, `GOLDEN RECORD`, `Voyager`, `Out past the
edge of the solar system.`, `Carrying music.` and `Allons-y`.

**The sharpest example is `Empire`.** The verdict reads *confirmed — "The
Liverpool Empire Theatre opened on Lime Street in 1925"*, and the receipt under
it is the minibus passage. The Liverpool room holds **three properly sourced
findings about the Liverpool Empire Theatre** — arthurlloyd.co.uk, the Moss
Empires history, and liverpooltheatres.com — and they are in the research CSV
you sent me. The sweep had the right sources in its files and cited the wrong
one.

`Top Ten` is the same shape: the Hamburg room holds the Top Ten Club at
Reeperbahn 136, and the sweep cited the minibus.

**This is not a plumbing bug.** The pipeline faithfully hydrated the URL the
verifier named; it can cite correctly, and does — `turning it up to eleven`
comes back anachronism against the Spinal Tap page, `DALEK`'s neighbours in the
same sweep cite properly. The defect is upstream: for a claim it is confirming
from general knowledge rather than from the room, the verifier names *a* page
from its files instead of declining. That produces a receipt that is wrong
rather than absent, which is worse than either.

**Why it matters more than it looks:** the whole argument of this product is
that a verdict is only as good as the page under it. A judge who opens this
file and reads *Taj Mahal — confirmed — [minibus excerpt]* has found the one
thing that undoes the pitch.

### The related one: right subject, wrong era

`86 to Penny Lane` comes back confirmed against
`transportxtra.com/.../24-hour-bus-routes-for-liverpool` — an article about
24-hour routes launched in the 2020s. Route 86 existing today says nothing
about 1958. Same class: a page that mentions the words, not a page that
supports the claim.

### And the extraction noise underneath it

`G-sharp`, `Ta`, `head on a stick`, `Do not pass Go`, `Allons-y`,
`vinyl records`, `Out past the edge of the solar system.` and `Carrying music.`
are not claims about the world a research room can answer. The claim extractor
raised them, and the verifier — having nothing real to cite — reached for the
nearest page. Tightening what gets raised would shrink the filler set
substantially on its own.

### What I did not do

I did not touch the verifier or the extractor. Both are prompt changes, both
cost a live sweep to validate, and neither is what you asked for tonight. The
call is yours:

- **Tighten the verifier** so a claim with no supporting page in its files
  comes back `unverifiable` rather than confirmed against the nearest one.
  Highest value, and it makes the sweep *look* worse — more unverifiables —
  while being more honest. That is the right trade for a product whose pitch is
  receipts.
- **Tighten the extractor** so `G-sharp` and `Allons-y` never become claims.
  Cheaper, lower risk, and it removes most of the filler set as a side effect.
- **Both**, in that order.

## The two research files: clean

`doctor-who-special-liverpool-research-2026-08-13.csv` (one room) and
`doctor-who-liverpool-and-hamburg-special-story-2026-08-13.csv` (the chain).

- Every excerpt matches the fact it sits under. Spot-checked across all five
  drawers in both rooms; found nothing like the sweep's filler.
- `retrieved_at` is the room's own build stamp on every row, `requisition` is
  empty on every row. Correct: nothing in either room was commissioned after
  the build.
- The chain file carries both rooms, nearest first — `1fd837bdd99e` (Doctor
  Who: Liverpool and Hamburg Special) then `01c41bcf266a` (Doctor Who Special:
  Liverpool) — which is the order a check reads them in.
- Filtering the chain file to `01c41bcf266a` gives back the single-room file.
  Checked drawer by drawer against the file you sent; the suite asserts the
  same property on fixtures.
- Nothing in either file would execute as a formula.

One thing worth knowing rather than fixing: the two rooms overlap. The Hamburg
Special was researched as Liverpool **and** Hamburg from the start, so the
chain file has two rooms answering some of the same ground. The `room` column
tells them apart, which is the reason the chain export was safe to offer.

## What changed in the sweep file since you downloaded it

Re-download to get it. Nothing needs re-sweeping — this reads the claims
already stored.

- A **`scene`** column, first. One row per scene: a claim the draft makes in
  seven scenes is seven rows. Filter on it and you have that page's whole
  picture.
- **Rows in page order**, scene 1 through 24, instead of claim order.
- `scenes` stays alongside carrying the claim's full spread, so "where else
  does the draft say this" still has an answer.
- Claims the sweep could not place keep their row with an empty `scene` and
  sort to the end.

Row count goes up — the file you sent has 61 rows and the same sweep will
export around 80, because eleven claims appear in more than one scene.


---

# The second round, after the split — sweep `26881297a20d`, 13:35

Nine files in the download folder, two generations of each. The suffixed copies
are the new shape; the unsuffixed ones predate today's exports and carry
neither `scene` nor `continues`. Everything below is measured off the files
themselves, not read off the screen.

**Correcting the first round.** That review said 23 of 61 rows carried the
filler source. The real figure for the 11:41 sweep was higher, and I had
counted distinct claims where I reported rows. Numbers below are derived by
script and are the ones to trust.

## The columns, verified by count

`doctor-who-liverpool-and-hamburg-special-sweep-2026-08-13 (1).csv`, sweep
`26881297a20d`.

- Header: `scene, scenes, claim, claim_type, verdict, note, source_title,
  source_url, source_excerpt, swept_at, sweep_id`. **`scene` first.**
- **80 rows from 64 distinct claims.** The 11:41 sweep was 64 rows from 64
  claims, one apiece.
- **Scene order 1, 2, 3, 5, 6, 7, 8, 9, 11, 13, 14 … 24 — strictly ascending,
  and not one blank.** Scenes 4, 10 and 12 raised no claims.
- **Eight multi-scene claims, and every one splits exactly as its `scenes` cell
  says. Zero mismatches across all 64.** `Kaiserkeller` (7 scenes) → 7 rows.
  `Top Ten`, `Liverpool`, `HAMBURG` → 3 each.

**Room files.** `continues` is present on the suffixed copies only. The story
file carries `1fd837bdd99e → continues=01c41bcf266a` and `01c41bcf266a →
continues=""`. That file imports as two rooms, already linked. The
`research (1)` file is the Hamburg room alone and names a parent that is not in
it, so it arrives unlinked with the complaint saying so. `requisition` is empty
on all 132 rows and `retrieved_at` is each room's own stamp — 02:14:17 and
11:51:03. All correct.

## Three counts that say more than the citations do

**Zero claims cite more than one source. 0 of 64.** The format asks for
`<url>, <url>` and got exactly one URL, sixty-four times.

**Zero `unverifiable` verdicts. 77 confirmed, 3 anachronism, 0 declined.**

**Zero notes on confirmed rows. 0 of 77.** All three anachronisms carry one,
and all three are good: *"The Daleks first appeared in Doctor Who in December
1963"*, *"The phrase originated in the 1984 film This Is Spinal Tap"*,
*"Richie Barrett's single 'Some Other Guy' was first released in 1962"*.

Read together those are one finding, not three. **A desk that never declines
always needs a URL**, and a claim it cannot source still has to be given one —
so it reaches for a page it read. It writes no note on a confirmation because
there is nothing to say about a page that does not mention the claim. And it
lists one source rather than two because it is naming the nearest page rather
than assembling support.

## What the filler actually looks like

**`en.wikipedia.org/wiki/Penny_Lane` — 8 rows, 8 claims, one excerpt, and it
supports none of them:** `Taj Mahal`, `DALEK`, `Voyager`, `A GOLDEN RECORD`,
`April. Judea.`, `Do not pass Go`, `Out past the edge of the solar system`,
`Carrying music`. **`DALEK` is among them** — the anachronism the demo turns
on has a correct note and a nonsense receipt.

**`en.wikipedia.org/wiki/The_Beatles_in_Hamburg` — 33 rows, 27 claims, three
different excerpts.** This one is not simply wrong. It genuinely answers
`Indra`, `Top Ten`, `Rory Storm`, `The Hurricanes`, `PETE BEST`, `Hamburg.
1960.` and the band members' ages. It is also where `horn-rimmed glasses`,
`Union Jack`, `blitzed`, `mate`, `The Elbe.`, `Seventeen. He was seventeen.`
and `Liverpool in 1958` were sent. **The page is doing real work and standing
in as the catch-all at the same time**, which is why counting rows against it
overstates the defect and ignoring it understates it. The honest figure is the
Penny Lane eight, which are unambiguous, plus a judgement call on roughly seven
of the Hamburg twenty-seven.

## Where it improved, on its own

- **`Empire`** — the sharpest example in the first review — now cites
  `arthurlloyd.co.uk`'s Liverpool Empire Theatre page.
- **`Some Other Guy` came back ANACHRONISM against its 1962 release.** In the
  11:41 sweep the same claim was `confirmed` against the Hamburg page. **A new,
  correct catch with the right page under it.**
- `"Raunchy."` cites *Raunchy (instrumental)*. `turning it up to eleven` cites a
  history of the Spinal Tap line.

## The fix is one sentence, and it is a sentence already in the file

`star/agents/script_check.py` tells the verifier: *"In the sources field list
only URLs you actually saw, either in `<room_files>` or in a parallel_search
result."*

**That binds the citation to SEEN, not to SUPPORTS.** Every filler URL in both
sweeps is a page the verifier really did read on that run. It is obeying.

The paragraph immediately above it already makes the argument for the verdict:
*"Your certainty is not a source… a claim you are sure about with nothing
behind it is thrown out rather than stamped."* It was never extended one field
to the right, to the citation — and the 0-of-64 unverifiable count says the
verdict half is not holding either.
