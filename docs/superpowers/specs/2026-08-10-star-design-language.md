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

`web/tokens.css` defines a type scale and no spacing scale. Counted across
`padding`, `margin`, `gap`, `row-gap`, and `column-gap` in all seven
stylesheets: **34 distinct rem values across 368 declarations**, each authored
at its call site.

(An earlier draft of this section said sixteen. That was a partial count taken
from `padding`/`gap`/`margin` alone and is corrected here rather than left
standing — a measuring stick carrying a wrong number measures wrong.)

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

Rules 9 and 10 are written outside the numbered list above because a heading
between list items restarts the numbering in most renderers, and these two are
referenced by number throughout this campaign.

**Rule 9 — state a scope obligation once per surface, not once per element.**
The obligations above are about honesty, not repetition, and an implementation
that confuses the two is reprinting rather than informing.

**This rule survived stage 1 with no confirmed violation, and the evidence
table it originally carried was wrong.** It is kept because the rule is sound,
and corrected here because the campaign measures against this file.

What the table claimed, and what the audit established:

| Claimed | Established |
| --- | --- |
| Citation rail: 36 words "reprinted under each of 9 marks" | The rail holds **one card at a time** — `scriptcheck.js:487` is `railBody.replaceChildren(buildRailCard(claim))`. The sentence renders once on screen, re-rendered per selection. Not a cadence violation. |
| Intake: 101 words "before the reader has done anything" | 101 is correct, but only 61 precede the field. The 40-word provenance paragraph renders in the right-hand index column beside the Build button, outside the reading path to the textarea. |
| Account card: 194 words across 6 strings, at `account.js:125-145` | The count is exact. The range is wrong: the six strings span `:72` through `:145`; `:125-145` holds two of them. |
| Check panel: 69 words across 2 paragraphs | Correct, and compliant — two *different* obligations stated once each is what this rule prescribes. |

The rule's normative content is the cadence clause, not a word budget. Volume
on a surface is not a violation; the same obligation reprinted per element is.
Findings citing this rule must show the repetition, not the total.

`web/scriptcheck.js:154-157` argues its `VERDICT_SCOPE` sentence "cannot be
cut," and that defence held: the relocation proposed against it turned out to
drop the click-through clause the comment names, which is rule 2's beat.

**Rule 10 — the answer outranks the disclaimer in the visual hierarchy.** In
`13-check-annotated`, the one line a writer came for — "First model TPS-L2
released in July 1979 in Japan" — renders **fourth** in `buildRailCard`'s order:
stamp, claim, the department's reading (`VERDICT_READING`), then the fact. The
fact and the explanation above it are both `el("p", "rail-line", …)`, byte-
identical treatment, so nothing in the type ranks the answer over the gloss on
it. An interface that explains its own epistemology more loudly than it delivers
the fact reads as a demo of carefulness rather than an instrument, which is the
exact register the aversion research says a hostile audience distrusts.

This rule was confirmed in stage 1 at severity 4 / visibility 4. One hole to
carry into any fix: `star/verdicts.py:91` requires a note only for
`unverifiable`, so a `confirmed` or `anachronism` card can render with no fact
line at all — a reordering that assumes the note is present has no case for
that card.

(The earlier draft said "third" and cited `14-check-citation` for the fold. Both
were wrong: the position is fourth, and in `14` the whole card sits below the
fold because the capture was taken with the stage scrolled, which is a capture
artifact and separately a real scroll defect, not intra-card ordering.)

**Rule 11 — a note earns its sentence, or it becomes a mark.**

THE MORGUE's native vocabulary is not prose. It is the plate, the tab, the slug
and the stamp: terse, structural, verbless, and the thing a hostile reader
trusts most on the page. `teatrnn.pl / RET 10 AUG 2026 / FILED BY OBJ` carries
more than any paragraph about provenance could, and DIRECTION.md says why — the
stamp is "the whole trust argument delivered as motion rather than as a claim."

The app writes prose in places where it already owns a better vocabulary. The
four drawer remits are the clearest case: "Light, sound, weather, dress, money,
food — the texture of a place in its period" is a sentence doing a plate's job.

**A note may be a sentence when it does something a mark cannot:**

- states a consequence the reader must weigh before acting — retention,
  revocation, spend, irreversibility;
- carries an obligation DIRECTION.md requires *in words* (rules 3, 5, 6);
- corrects something the reader would otherwise get wrong.

**A note must not be a sentence when it is:**

- an enumeration of what a thing contains — that is a plate;
- a restatement of what the adjacent control already says;
- a label wearing a verb.

**The test, so this is checkable rather than felt:** strike every verb. If the
note still says the same thing, it was a mark all along.

### A mark is derived, never authored

Added 2026-08-11, after this rule licensed a proposal that three independent
reviews then killed. **The flaw was in the rule, not only in the proposal.**

Rule 11 quotes `teatrnn.pl / RET 10 AUG 2026 / FILED BY OBJ` as proof that a
mark outperforms a paragraph, and cites DIRECTION.md's "delivered as motion
rather than as a claim" as its authority. Read carelessly — and it was — that
licenses replacing a sentence with a *picture* of a mark. It borrowed the moving
stamp's authority to license a still one.

The stamp's authority is not its typography. It is that every field is derived
from something that happened. `buildFiledHead` does `[code, date].filter(Boolean)`
and prints `LOG` alone rather than fill a slot it cannot support.
`web/drawer.js:340-348` refuses to default `retrieved` from `date`, because that
would be "a fabricated provenance claim on the exact element whose whole job is
provenance." `web/clip.js:201-208` invents no domain. Three files, one
discipline.

**So: a note may become a mark only where the mark's values come from data. A
hand-authored mark is a badge, and DIRECTION.md's signature section is titled
"the stamp is an event, not a badge."** A mark with no mechanism behind it is
the only kind of mark this app must never render — it is a trust signal with
nothing under it, which the aversion research names as the harm, and it is
uncatchable afterwards because no verb test and no grep reads a picture.

Two further traps this rule now names, both found the hard way:

- **A mark has no quantifier.** `web/shell.css:640-656` records that the intake's
  provenance sentence once read "the source it came from" and was killed at
  critical severity, because `star/findings.py` keeps a Finding whose every
  cited URL failed the ledger check with `citations: []`. The fix was the
  quantifier — "the sources that came back for it", which allows zero. A
  rendered mark asserts the universal again, in a form no wording review
  catches. Where a sentence carries a quantifier, a hedge, or a "where there was
  one", it is not convertible.
- **A mark cannot state a failure behaviour.** "A cited link that never came back
  from a search is stamped, not dropped" survives the verb test and is the half a
  hostile reader cares about. No mark says it, and demonstrating it would mean
  fabricating a failure.

### Why rules 9 and 11 are two rules

Rule 9 catches a thing said too often. Rule 11 catches a thing said in the wrong
form. Stage 1 proved they are not the same failure: rule 9 survived 67
adversarial reviews with **no confirmed violation** — every finding citing it
was correctly refuted, because the app really does state each obligation once
per surface — while the builder could see at a glance that the copy read as
forced. The register had no rule for that, so nothing could be filed against it.

The measured shape of the problem, for anyone arguing with this rule: 1,143
words of standing prose across 38 strings, median sentence 14 words and mean
13.9 — a band so tight that nothing on any surface carries emphasis. 531 of
those words are on the consent page, which a reader reaches once by redirect
from a client the department never checked, and which is right to argue. The
other 612 are in surfaces a writer lives in.

Rules 9, 10 and 11 extend DIRECTION.md rather than restating it. Rule 10 held
under adversarial review. Rule 9 held as a rule but lost its evidence. Rule 11
exists because the first two, enforced exactly as written, let a real defect
through. A wave arguing against any of them argues against the findings
register, not against taste.

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
