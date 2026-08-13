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
