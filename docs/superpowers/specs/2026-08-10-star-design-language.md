# STAR design language — the measuring stick

**Date:** 2026-08-10
**Status:** stage 0 artifact of a vibe-glow campaign, pending approval
**Source of truth it promotes:** `docs/design/DIRECTION.md` (decided 2026-08-09)
**Evidence it was written against:** `docs/ui-evidence/`, round 1, 14 captures at
1440x900, one `default` theme round

This is not a new direction. THE MORGUE was decided on 2026-08-09 against four
research agents and an adversarial critic, with two alternatives rejected on the
record, and a campaign that invented identity hypotheses to argue against it
would be re-litigating a call made with better inputs than concept boards could
supply. What follows promotes that decision into something a review agent can
measure a surface against, and records what the running code actually does where
the direction never said.

Two kinds of statement live here and they are labelled, because conflating them
is how a measuring stick starts measuring its own guesses:

- **Decided** — carried from DIRECTION.md or implemented in `web/tokens.css`.
  A finding that contradicts one of these is wrong.
- **Observed** — what the CSS does today, with no decision behind it. A finding
  may propose changing these, and should.

## Identity statement

The newspaper clipping library behind the newsroom, where nothing gets filed
without a stamp saying who found it, where, and when. The metaphor was chosen on
one test: it describes the system rather than dressing it. A clipping file is
`LedgerEntry`, an unstamped clip is `Finding.unverified_urls`, four subject
drawers are `Category`, and the stamp is `found_by` plus the domain plus the
retrieval date. Nothing is stretched to fit.

The cabinet is the frame. The cards are the page.

## Type ramp — decided

Three families, all SIL OFL, all vendored under `web/vendor/fonts/`. No CDN
link, ever; the zero-third-party-request rule forbids it.

| Role | Family | Why this one |
| --- | --- | --- |
| Display / label | Archivo Narrow (400, 700 static) | Condensed American gothic in the ATF form-and-label tradition. The morgue's visible typography is labels: drawer plates, folder tabs, stamp slugs. Bold with wide tracking reads as a filing label, and a display serif would land in the cream-and-serif default. |
| Body | Newsreader (variable, wght 200-800, opsz 6-72) | The `opsz` axis is load-bearing, not decorative. The bible is a long read at one size and clip excerpts are captions at another, and one static face cannot serve both. `font-optical-sizing: auto` is left at its default so the browser applies it per computed size. |
| Utility | Sligoil (400) | Drawn for subtitling and film-adjacent paperwork, with apertures that survive at 11px. Carries URLs, dates, counts, stamp slugs. |

Scale, from `web/tokens.css`:

| Token | Size | Job |
| --- | --- | --- |
| `--label-sm` | 11px | Drawer plates, stamp slugs |
| `--label-md` | 13px | Folder tabs |
| `--text-sm` | 14px | Clip excerpts |
| `--text-md` | 17px | Findings |
| `--text-lg` | 22px | Room title |

`--track-label: 0.14em`. Labels are tracked wide; body text never is.

## Spacing scale — observed, and the one axis nothing ever decided

`web/tokens.css` defines a type scale and no spacing scale. The CSS uses at
least sixteen distinct values in `padding`, `gap`, and `margin`: 0.2, 0.35, 0.4,
0.45, 0.5, 0.6, 0.7, 0.75, 0.85, 0.9, 1, 1.1, 1.25, 1.5, 1.75, and 2rem, each
authored at its call site.

This is stated rather than fixed here, because inventing a ramp is a design
decision and stage 0 adopted an existing direction instead of making new ones.
It is the single largest open question this campaign can close, and a wave that
proposes a scale should argue it from the values already load-bearing in the
morgue's geometry, not from a generic 4/8pt grid imported from elsewhere.

## Shape language — observed

Corner radii in use: 2px (15 rules), 3px (17), 4px (6), plus `50%` on two round
elements, one `999px` pill, and two explicit `0`s. The working vocabulary is
"2 or 3px, decided per component."

The shape that actually carries the identity is not the radius, it is the
**hanging-folder geometry**: a cut tab rising above the card's top edge, a second
folder edge peeking out behind, and a card face layered over the tab's base.
`--tab-rise` in `web/drawer.css` is the one number the whole construction depends
on. That geometry is load-bearing identity; the radii are not.

## Iconography — observed

There is effectively no icon set. The app ships one mark, the `✶` asterisk in
the rail header, and otherwise carries meaning in typographic labels, stamps, and
the folder geometry. This is coherent with a direction whose visible typography
*is* labels, and a wave proposing an icon library would be adding a vocabulary
the morgue has so far done without. Any icon proposal argues its way in against
that record.

## Motion — decided

`--stamp-duration: 220ms`, declared in `:root` **before** the
`prefers-reduced-motion` override that sets it to `0ms`. Both rules target
`:root` at equal specificity, so source order decides the winner regardless of
the media condition. The brief's original order put the override first and
silently defeated the accessibility feature; the current order was inverted for
that reason and verified in a real browser with reduced motion emulated.

The signature is that **the stamp is an event, not a badge**. A finding lands
unstamped and the stamp presses down carrying the domain, the retrieval date, and
the researcher's code. A failed ledger check gets the second pad: `UNSOURCED` in
oxide, and the clip stays on screen. A hostile reader watches the department
catch its own people in the first thirty seconds, with no copy required.

## Palette tokens — decided

| Token | Hex | Job |
| --- | --- | --- |
| `--cabinet` | `#232B27` | Ground. Olive-drab mid-century steel furniture: dark, but cold and green-shifted so it reads as furniture rather than "dark mode." Deliberately not `#0f1115`. |
| `--drawer-shadow` | `#171D1A` | Insets, the treatment field, the rail. One step down, never to black. |
| `--manila` | `#D2B98C` | Folder stock. A component surface, never the page ground. |
| `--manila-edge` | `#B99F70` | Folder edge, tab shadow. |
| `--onionskin` | `#E9E2D2` | The expanded reading surface. A component inside an opened drawer. |
| `--aniline` | `#5C3D91` | **Filed.** Flat stamp ink. Surviving 1950s file cards are stamped violet because rubber-stamp ink was aniline violet. |
| `--oxide` | `#B3341F` | **Flagged.** `UNSOURCED`, and the anachronism verdict. |
| `--pencil` | `#7E8B7F` | Metadata, labels, and the unstamped state. |
| `--pencil-text` | `color-mix(--pencil 85%, --onionskin)` | `--pencil` when it must be read rather than drawn. One value serving both dark grounds so there is no second number to drift. |
| `--ink` | `#1B211D` | Text on manila. |

The irony is on the record and worth keeping there: the aversion research flags
violet as the loudest AI tell of 2026. Aniline here is the opposite of that, a
flat stamp-ink solid used only for a verified state. **The tell is the gradient,
not the hue.** If it ever appears as a gradient, the direction has failed.

## Component rules

- **Drawers.** Four, one per `Category`. A filing system a writer recognises,
  where "four agents running concurrently" is engineering self-regard. Five
  states: idle, searching, filed, flagged, failed.
- **Clips.** Added to a filed card, never replacing it. Each carries a stamp:
  domain, `RET <date>`, `FILED BY <code>`. A clip whose URL never appeared in
  the search results is stamped `UNSOURCED` and **stays on screen** rather than
  being quietly dropped.
- **Onionskin surfaces** stay inside an opened drawer. Promoting one to a page
  ground lands the direction in the cream-and-serif default by the side door.
- **Contrast is measured, not eyeballed.** Every CSS file carries a recorded
  table against a 4.5:1 floor for text and 3:1 for controls and visual
  boundaries, with the failing pairs named and marked `NEVER used`. A change to
  a colour pair restates the measured ratio or it is not shippable.

## Copy rules

Carried from DIRECTION.md, decided:

1. Every finding shows the scene it unlocks, from `ResearchQuestion.why`.
2. Every citation is click-through to the real excerpt. A citation that cannot
   be opened is worse than no citation.
3. Say what was actually checked. Never "verified" — the ledger proves a source
   was genuinely returned by a search, and says nothing about whether the fact
   matches it.
4. Show real uncertainty: `parse_rate`, `unverified_count`, the researchers' own
   notes.
5. State what happens to the treatment, in the intake, before the paste.
6. Never promise a duration. Show progress, not an ETA.
7. Distinguish source *type*, not just source count, where it can be inferred.
8. The register is institutional, not ingratiating. Any copy that flatters the
   user gets cut.

### Added 2026-08-10, from the builder, against round-1 evidence

9. **State a scope obligation once per surface, not once per element.** The
   obligations above are about honesty, not repetition, and the current
   implementation confuses the two. Round-1 evidence, counted from the rendered
   page rather than estimated:

   | Surface | Static explanatory prose, before the reader has done anything |
   | --- | --- |
   | Intake | 102 words across 3 paragraphs |
   | Account | 190 words across 5 paragraphs |
   | Check panel | 70 words across 2 paragraphs, before a scene is pasted |
   | Citation rail | 34 words reprinted under each of 9 marks |

   None of it collapses after first read, moves behind disclosure, or shrinks
   once the reader has used the thing. `web/scriptcheck.js:154` argues its
   `VERDICT_SCOPE` sentence "cannot be cut," and the obligation behind it is
   real — but honouring rule 3 does not require reprinting the same 34 words
   under every mark a reader clicks. Right rule, wrong cadence.

10. **The answer outranks the disclaimer in the visual hierarchy.** In
    `14-check-citation`, the one line a writer came for — "First model TPS-L2
    released in July 1979 in Japan" — renders third, at the same weight as its
    neighbours, between two explanatory paragraphs, with a full-length italic
    excerpt pushing it toward the fold. An interface that explains its own
    epistemology more loudly than it delivers the fact reads as a demo of
    carefulness rather than an instrument, which is the exact register the
    aversion research says a hostile audience distrusts.

Rules 9 and 10 extend DIRECTION.md rather than restating it. They exist because
round-1 evidence showed the failure and the builder named it; a wave arguing
against them argues against the evidence in `docs/ui-evidence/`, not against
taste.

## Invariants — verbatim

These outrank every finding. They are stored in `.vibe-glow/state.json` and
handed to each review agent unmodified.

1. Manila (`#D2B98C`) owns more than 40% of the room's pixel area in the filed
   state — a finding that shrinks cards to accent-sized chips is rejected however
   much cleaner it looks. The cards are the page, the cabinet is the frame.
2. Aniline (`#5C3D91`) is a flat stamp-ink solid, never a gradient, never a brand
   wash — the gradient is the AI tell of 2026, not the hue. Any proposal
   introducing a violet gradient or accent wash is rejected on sight.
3. Onionskin (`#E9E2D2`) stays a component inside an opened drawer, never a page
   ground — promoting it to a page background lands the direction in the
   cream-and-serif default by the side door.
4. The stamp stays typographic: no distress textures, no rotation past 2.5
   degrees — texture reads as a Photoshop filter, and decoration is what a
   skeptic dismisses.
5. Contrast is measured, not eyeballed — every CSS file carries a recorded table
   against a 4.5:1 floor for text and 3:1 for controls and visual boundaries. A
   finding that moves a colour pair must restate the measured ratio or it is not
   shippable.
6. Zero third-party requests at runtime — fonts and JS libraries are vendored
   under `web/vendor/`. No finding may introduce a CDN link or any hosted asset.
7. No build step — `web/` is hand-written CSS and ES modules served straight off
   a StaticFiles mount. No framework, no Tailwind, no bundler proposals.
8. The `prefers-reduced-motion` override must stay AFTER the default in
   `web/tokens.css` — both rules target `:root` at equal specificity, so source
   order decides. Reordering silently defeats the accessibility feature; it
   already shipped broken once.
9. Copy never says "verified", never promises a duration, never flatters the
   user — institutional register, evidence-first. DIRECTION.md's "What the UI is
   now obliged to do" outranks any copy finding.

## What round 1 saw that is not a design finding

Recorded here so a later wave does not argue typography against a broken page:

- **The bible truncates silently.** The Gdansk 1978 bible rendered section 1 of
  four and ended mid-sentence on "…withheld desirable inventory behind counters
  or". This is the defect `docs/judge-critique-2026-08-11.md` reported as
  shipping silently, reproduced live on 2026-08-10. `10-bible` is therefore
  evidence of a truncated document, not of the bible's reading layout.
- **A procedural claim went unextracted.** "The guards wave them past without a
  search" — the assertion that most directly contradicts the room's own research
  plan — produced no mark, while "fresh oranges without queueing" did. Backend
  recall, not design.
