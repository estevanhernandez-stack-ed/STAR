# Phase 3 design direction — decided 2026-08-09

The short version: **THE MORGUE**, and **findings lead, the bible follows**.

Four research agents ran independently on four different questions. This
records what they found, where they converged, what it changed, and what the
UI is now obliged to do. The full findings are in the sibling files; nothing
here restates them at length.

## What the research changed

### The convergence nobody coordinated

Three separate lines of inquiry landed on the same conclusion: **the unit of
value is one sourced clip, not the assembled document.**

- Practice research found that the two prestige shows most famous for period
  accuracy — *Mad Men* and *The Crown* — deliver **incremental, per-draft
  annotations tied to a scene**, not a static reference tome handed over once.
- The adversarial critic, working from the opposite end, said the organized
  document and the four-quadrant grid serve hackathon judges rather than
  writers: *"I don't care that four API calls ran concurrently — that's
  implementation detail cosplaying as feature."*
- Practice research again: trusted research is organized around **scene-level
  cues**, and each finding needs a visible line to the scene it unlocks.

**We already generate that line and bury it.** `ResearchQuestion.why` is
described in our own model as *"What scene-writing need this answers."* It is
rendered as grey italic inside the third tab, behind two clicks. The most
valuable connective tissue we produce is filed in the least visible place.

### What the critic got right, and what it got wrong

Right, and unaddressed anywhere in the product:

- **A treatment is unprotected IP.** We persist it to Firestore indefinitely
  with no retention policy stated anywhere in the intake copy. For a writer
  pasting an unproduced project into a website, this is a larger trust problem
  than any citation question. **The UI must say what happens to the treatment,
  in the intake, before the paste.**
- **"Verified" is an overclaim.** The ledger check proves a URL genuinely came
  back from a search. It does **not** prove the fact matches the source. A real
  URL attached to a wrong fact passes clean. Language must say precisely what
  was checked — proving rigour on the narrow case while implying breadth is the
  exact failure the aversion research warns about.
- **The duration promise is false on our own record.** `star/config.py`
  documents observed runs of 146s to over 420s for one fixed treatment, and a
  ceiling raised to 600s after a legitimate run tripped it. A UI implying
  "about four minutes" is lying with our own data.
- **The live URL must match the video.** Phase 3 has to be deployed before the
  demo is recorded, or a judge clicking through from the submission finds
  something that does not match what they watched.

Wrong on mechanism: it assumed Google sign-in. Ours is silent and anonymous.
The retention objection underneath it stands regardless.

### What the aversion research changed

- **Calibrated confidence beats blanket confidence.** ChatGPT signalled
  uncertainty 15 times across 200 responses while producing 134 wrong
  citations. We compute `parse_rate`, `unverified_count`, and the researchers'
  own uncertainty notes. **We have real uncertainty data to show, and almost
  nothing in this category does.** Showing it is the differentiator.
- **A citation is a trust signal independent of accuracy.** People trust an
  answer more for citing a known outlet even when it is wrong. So a citation
  that cannot be clicked through to the real excerpt is actively misleading —
  click-through is what makes it honest, not decoration on top of honesty.
- **Sycophancy is trusted and is the harm.** Warmth is the wrong lever for a
  hostile audience; a flat, evidence-first register reads safer. The
  "department" voice survives because it is *institutional*, not ingratiating —
  but any copy that flatters the user gets cut.
- **Purple and indigo gradients are the loudest AI tell of 2026**, read before
  a single citation. Note the irony below.

### What the practice research changed

- **Say "grounded."** Three unrelated interviews reached for that word
  unprompted. Not "accurate," not "verisimilitude."
- **Source *type* beats source count.** Trust runs on primary-versus-secondary
  distance. "11 sources" tells a writer nothing; whether those are museum
  archives or somebody's blog tells them everything.
- **Do not say "lookbook."** It is taken, and means images and mood — a
  production designer's artifact, not cited prose.

## The direction: THE MORGUE

The newspaper clipping library behind the newsroom, where nothing gets filed
without a stamp saying who found it, where, and when.

It was chosen on one test: **the metaphor describes the system rather than
dressing it.**

| The metaphor | The code that already is that |
| --- | --- |
| A clipping file | `LedgerEntry(url, title, excerpts, found_by)` |
| A clip dropped in the drawer unstamped | `Finding.unverified_urls` |
| Four subject drawers | `Category` — setting, objects_props, logistics, forces_conflicts |
| The stamp: who found it, where, when | `found_by`, the domain, the retrieval date |

Nothing is stretched to fit. That also answers the critic's sharpest point:
four drawers are a **filing system**, which a writer recognises, where "four
agents running concurrently" is engineering self-regard.

### Palette

| Hex | Name | Job |
| --- | --- | --- |
| `#232B27` | Cabinet Green | Ground. Olive-drab mid-century steel furniture — dark but cold and green-shifted, so it reads as *furniture*, not "dark mode." Deliberately not `#0f1115`. |
| `#171D1A` | Drawer Shadow | Insets, the treatment field, the rail. One step down, never to black. |
| `#D2B98C` | Manila | Folder stock. A component surface, never the page. |
| `#5C3D91` | Aniline | **Filed and verified.** Rubber-stamp ink was aniline violet, which is why surviving 1950s file cards are stamped violet rather than black. |
| `#B3341F` | Oxide Red | **Flagged.** The `UNSOURCED` stamp, and later the anachronism verdict. Red because that is what the second pad was. |
| `#7E8B7F` | Pencil | Metadata, labels, and the **unverifiable** state — a clip nobody got around to stamping. |

**The irony worth naming:** the aversion research flags violet as the loudest
AI tell of 2026. Aniline here is the opposite of that — a flat stamp-ink solid
used only for a verified state, never a gradient, never a brand wash. The tell
is the gradient, not the hue. If it ever appears as a gradient, the direction
has failed.

### Type

All three are SIL OFL and self-hostable. **No Google Fonts CDN link** — the
zero-third-party-request rule from Phase 2 forbids it.

- **Display — Archivo Narrow.** A condensed American gothic in the ATF
  form-and-label tradition. The morgue's visible typography is *labels*: drawer
  plates, folder tabs, stamp slugs. Bold with wide tracking is a filing label.
  Not a display serif, which keeps this clear of the cream-and-serif default.
- **Body — Newsreader.** A news text face with a real `opsz` axis. Load-bearing:
  the bible is a long read at one size and clipping excerpts are captions at
  another, and one static face cannot serve both.
- **Utility — Sligoil.** A monospace drawn for subtitling and film-adjacent
  paperwork, with apertures that survive at 11px. Carries URLs, dates, counts,
  stamp slugs. Fallback if hinting disappoints: Sometype Mono or DM Mono.

### The signature: the stamp is an event, not a badge

A finding lands unstamped. The stamp presses down — domain, retrieval date,
and the researcher's code from `found_by`. A failed ledger check gets the
second pad: `UNSOURCED` in oxide red, angled, and **the clip stays on screen.**

A hostile screenwriter watches the department catch its own people in the first
thirty seconds, with no copy required. That is the whole trust argument
delivered as motion rather than as a claim.

### Two rules that make or break it

1. **Manila must own more than 40% of the room's pixel area in the filed
   state.** `#232B27` is not `#0f1115`, but it is dark — if the cards shrink to
   accent-sized chips the page becomes near-black-with-a-warm-accent, which is
   precisely the default being avoided. The cards are the page; the cabinet is
   the frame.
2. **The stamp stays typographic.** No distress textures, no rotation past
   2.5 degrees. The moment it looks like a Photoshop filter it reads as
   decoration, and decoration is what a skeptic dismisses.

One more, from the expanded reading view: its onionskin surface (`#E9E2D2`) is
cream-adjacent and must remain a component inside an opened drawer. If it ever
becomes a page ground, the direction lands in the cream-and-serif default by
the side door.

## What the UI is now obliged to do

Beyond the visual direction, the research obliges specific behaviour:

1. **Every finding shows the scene it unlocks**, from `ResearchQuestion.why`.
2. **Every citation is click-through to the real excerpt.** A citation that
   cannot be opened is worse than no citation.
3. **Say what was actually checked.** Not "verified" — the ledger proves the
   source was genuinely returned by a search, and says nothing about whether
   the fact matches it.
4. **Show real uncertainty.** `parse_rate`, `unverified_count`, and the
   researchers' own "verify before writing" notes.
5. **State what happens to the treatment, in the intake, before the paste.**
6. **Never promise a duration.** Show progress, not an ETA.
7. **Distinguish source type**, not just source count, where it can be inferred.

## Rejected, with reasons

- **THE BENCH** — light table, near-black as film and ink. The boldest move
  against the AI defaults, and genuinely nobody looks like it. Rejected because
  an unsourced clip is a *missing negative*, and absence is far harder to
  dramatise than a red stamp — it loses the trust moment the product is built
  around.
- **THE ROD** — card catalogue, brass rod, archival square-bracket convention
  for "the archivist supplied this." Quietly exact. Rejected as the closest of
  the three to period pastiche: warm walnut risks reading nostalgic where this
  product needs to read rigorous.
- **Cutting the bible entirely** — the purest reading of the research, and
  rejected because it removes the one surface that reads well cold. A judge
  skimming a submission may never build a room.
