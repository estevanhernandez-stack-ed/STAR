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

Four files, downloaded after `star-00046`. Everything I changed is correct in
them. What I did not change moved on its own, and the movement is worth
reading.

## The columns, verified row by row

**Sweep file.** `scene, scenes, claim, claim_type, verdict, note, source_title,
source_url, source_excerpt, swept_at, sweep_id` — `scene` first, `scenes`
second.

- **80 rows**, up from 61. Exactly the inflation predicted, and the reason is
  visible: eleven claims appear in more than one scene.
- **Page order holds.** Scenes run 1, 2, 3, 5, 6, 7, 8, 9, 11, 13, 14, 15, 16,
  17, 18, 19, 20, 21, 22, 23, 24. Scenes 4, 10 and 12 are absent because they
  raised no claims — the TARDIS scenes, which assert nothing about 1958.
- **The split is right on every multi-scene claim.** `Kaiserkeller` carries
  `scenes = "13 17 19 20 21 23 24"` and appears as seven rows, one at each.
  `Top Ten` (8 9 13) → three rows. `Liverpool` (1 5 21) → three. `HAMBURG`
  (15 17 24) → three. `VESPA`, `G-sharp`, `RORY STORM AND THE HURRICANES` and
  `THE SENIORS` all land where their `scenes` cell says.

**Story file.** `continues` is present and correct: every Hamburg row carries
`01c41bcf266a`, every Liverpool row carries empty. Hamburg first, Liverpool
second — nearest first. **That file will import as two rooms, already linked.**

**Research file (Hamburg alone).** Same columns, and `continues` names
`01c41bcf266a` — a room that is not in the file. Importing it on its own will
file one room, unlinked, with the complaint saying so by name. Working as
designed; worth knowing before you see the message.

**One thing the story file proves that a fixture could not.**
`grokipedia.com/page/liverpool_city_police` is cited by BOTH rooms and appears
as two rows, not one. That is the no-deduplication rule doing its job: a source
carrying two rooms is a fact about the research.

## The accuracy moved in both directions

**Genuinely better than the 02:14 sweep:**

- **`Empire`** now cites `arthurlloyd.co.uk`'s Liverpool Empire Theatre page —
  the correct source, and the exact row that was the sharpest example of the
  defect last time.
- **`"Raunchy."`** → *Raunchy (instrumental)* on Wikipedia. Correct.
- **`Some Other Guy` → ANACHRONISM**, citing the Wikipedia entry showing a 1962
  release against a 1960 scene. **That is a new, correct catch with the right
  page under it** — and in the earlier sweep the same claim came back
  `confirmed` against the filler.
- `turning it up to eleven`, `Candid Camera`, `GERMAN POLICE MOTORCYCLE` and
  `drums` all cite pages that actually hold them up.

**Worse than the 02:14 sweep:**

- **`1959 Standard Vanguard Estate`** now cites a **Ford Thames Pickup**
  auction listing. The earlier sweep cited the Standard Vanguard Wikipedia
  entry, which was right. This one is a different vehicle from a different
  manufacturer.
- **`DALEK`**, the anachronism the whole demo turns on, cites **Penny Lane**.
  Last time it cited the minibus. Different nonsense, same nonsense.
- **A second filler emerged.** Alongside the Beatles-in-Hamburg minibus
  passage, the *Penny Lane* Wikipedia excerpt now carries eight rows:
  `Taj Mahal`, `DALEK`, `Do not pass Go`, `April. Judea.`, `A GOLDEN RECORD`,
  `Voyager`, `Out past the edge of the solar system`, `Carrying music`.

**The rate did not move.** 23 of 80 rows carry the minibus passage and 8 carry
Penny Lane: **31 of 80, 39%**. The earlier sweep was 23 of 61, 38%. Two
independent sweeps, the same fraction, different claims — which says this is
the pipeline's steady state and not a bad night.

## And the notes went away

Every `confirmed` row in this sweep has an **empty `note`**. The 02:14 sweep
wrote one on each — "Eyeglasses made of horn or tortoise shell were standard
personal items in the 1950s". Only the three anachronisms carry notes now, and
those three are excellent.

Not caused by anything shipped today: `sweep_rows` passes `note` through
untouched, and no code between the verifier and the file touches it. It is
model variance between two runs of the same prompt. It matters anyway — a
`confirmed` verdict with **no note and a wrong source** gives a reader nothing
at all to check.

## The diagnosis is now one sentence

`star/agents/script_check.py` tells the verifier: *"In the sources field list
only URLs you actually saw, either in `<room_files>` or in a parallel_search
result."*

**That binds the URL to SEEN, not to SUPPORTS.** The model is obeying the
instruction it was given. Every filler citation in both sweeps is a page the
verifier genuinely read on that run — it just is not the page that holds the
claim up. The rule the prompt never states is the one a receipt depends on:
*the URL you list must be the page that settles THIS claim, and if no page you
read settles it, the verdict is `unverifiable`.*

The neighbouring paragraph already makes exactly this argument for the verdict
("your certainty is not a source... a claim you are sure about with nothing
behind it is thrown out rather than stamped"). It was never extended to the
citation. A claim confirmed against a page that does not mention it is the same
failure the paragraph was written to stop, one field to the right.
