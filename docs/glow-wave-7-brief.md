# Glow wave 7 — said twice, meant once

**Branch:** `glow/wave-7-said-twice-meant-once`
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md)
**Measuring stick:** [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md)

Six rows, one shape: a value declared more than once and drifting. `F-018`,
`F-014`, `F-016`, `F-017`, `F-019`, `F-020`.

Every claim below was **re-verified 2026-08-11**. Where a row and this file
disagree, this file is right.

## Why this wave is worth building, since two of its rows change no pixels

`F-017` and `F-019` render byte-identical output. Wave 3 passed on them for
exactly that reason, and a wave that ships only tidiness deserves the same
answer.

**The argument is `F-016`, and it is evidence rather than principle.** The same
card is declared across six surfaces in five files, and one of those copies has
already drifted far enough to be *visible*: in `10-bible` the docket's title sits
at x≈361 and the bible's heading at x≈369 — an 8px left-edge break between two
stacked full-width cards. That is what an unmanaged duplicate becomes. `F-017`
and `F-019` are the same duplication one step earlier, before it has cost
anything.

So the wave ships the visible defect and closes the two that would become it.

## The scope law

A wave ships only its findings; anything found mid-build becomes a register
addition. The invariants that bite hardest here:

- **Invariant 5 — contrast measured, not eyeballed.** `F-016` has a live trap:
  `.bible` carries **no** `box-shadow` and sits on `--onionskin`, so any shared
  card rule would both add a shadow it does not have and put `--manila-edge`
  under onionskin. **That is a new colour pair and it must be measured and
  recorded, or the shared rule is not shippable.**
- **Invariant 6 — no third-party requests.** `F-020` must not become a CDN or a
  new asset.
- **Invariant 7 — no build step.** Plain CSS.

Repo law as always: commit per item, declarative sentence-case subjects, no
conventional-commit prefix, the `Co-Authored-By` trailer, and every test proven
by reintroducing the bug it guards.

---

## 1. F-018 — the stick dropped half of DIRECTION.md's own phrase

**Zero pixels. Do this first: everything else in the campaign is measured against
this file.**

`DIRECTION.md:111` reads "**Filed and verified**" and `:117` says aniline is
"used only for a verified state". The stick's palette row transcribed that as
"Filed." and dropped the load-bearing half.

**Build:** restore DIRECTION.md's wording — "`--aniline`: **Filed and verified**,
at the citation level" — and add that container-level stamps take `--ink`.

**Strike the lens's fallback.** It proposed putting aniline on the drawer stamp's
rule. `drawer.js:13-38` argues on the record that a drawer has no citation to
check, so an aniline drawer stamp claims a verification the component cannot
see — which copy rule 3 forbids in words and this would assert in colour.
**Verified still true:** zero pixels within ±24 of `#5C3D91` in either
`07-room-filed` or `06b-progress-filed`.

## 2. F-014 — the ramp's top step spent twice in 50px

**Verified:** `.bible-heading` is `--text-lg` (`bible.css:61`) and `.bible-body h1`
is `--text-lg` (`bible.css:115`). Both take `var(--label)`, uppercase, bold,
`--track-label`. So "THE RESEARCH BIBLE" and "GDANSK 1978: WRITER'S RESEARCH
BIBLE" ship as two identical 22px tracked uppercase lines ~52px apart, repeating
the words "RESEARCH BIBLE", separated only by a rule.

**Build:** drop `.bible-heading` to `--label-md`, so the document's own h1 is the
only 22px line on the surface. Size only; same `--ink` on `--onionskin` pair
(12.70:1, already recorded), so invariant 5 has nothing to restate.

**Reject the other half of the lens's fix: do not add `--text-xl` to
`tokens.css`.** `bible.css:68-87` argues explicitly that this surface "picks its
own size and states the optical size to match it, rather than inheriting whatever
axis value a future change to `--text-md` would imply". A shared token invites a
second caller without the `opsz` pin, which is the coupling that comment exists
to prevent.

## 3. F-016 — one card, three paddings, six surfaces

**Verified, and the row undercounts the surfaces.** Six card surfaces across five
files carry three distinct desktop paddings:

| padding | surfaces |
|---|---|
| `1.5rem 1.75rem 1.6rem` | `.docket`, `.check` |
| `1.75rem 2rem 2rem` | `.intake`, `.account`, `.consent` |
| `2rem 2.25rem 2.5rem` | `.bible` — the outlier, and the visible break |

**Build the visible defect first: align `.bible`.** It is the single unanchored
value and the only one producing the 8px break in `10-bible`. No comment anywhere
in `web/` argues a card padding value, so nothing is being overruled.

**The shared `.card` rule is the durable form and it has two recorded blockers.**
Both are real; neither is a reason to skip the alignment above:

1. `.bible` has no `box-shadow` and sits on onionskin — a shared rule "holding
   radius, shadow and padding" adds a shadow it does not have and creates a new
   `--manila-edge` on `--onionskin` pair. **Measure and record, or scope the
   shared rule to exclude `.bible`.**
2. `consent.html` deliberately does not load `shell.css` (see F-020), so a shared
   rule there cannot reach `.consent`.

Three mobile paddings also differ in **top as well as bottom**: one rule plus two
overrides, not one rule.

## 4. F-017 and F-019 — the duplicates, before they drift

**F-019, verified byte-identical.** `.clip` (`clip.css`) and `.rail-card`
(`scene.css`) are the same four declarations with the same four values:
`background: var(--onionskin)`, `border-radius: 3px`,
`border-left: 3px solid var(--manila-edge)`, `padding: 0.95rem 1.1rem 1rem`.

Cascade is safe: `.clip[data-unsourced]` and `.rail-card[data-verdict]` are
attribute selectors at higher specificity than a shared class rule.

**Corrections that hold:** `.scene-page` is **not** a third copy — it shares three
declarations and carries eight more, all argued at `scene.css:238-248`, so it
joins as a consumer with an override. The two 560px blocks are **not** identical;
only the two padding declarations collapse.

**F-017, verified:** `.clip-stamp` and `.rail-unsourced-stamp` are **11
declarations each** — the row's own correction against the lens's "13", and it is
right. `.clip-stamp-note` has **no twin in `scene.css`**, so this is four pairs
and one orphan, not a wholesale double-build.

**Build:** merge into shared selector lists in `shell.css`, whose `.banner`
comment already records "Oxide on `--onionskin` is 4.75:1 — the same pair the
UNSOURCED stamp already uses." State recolour stays per-file as
`border-left-color`. Invariant 5 holds untouched: both sit on onionskin and no
pair moves.

**Byte-identical rules render byte-identical pixels, so nothing on screen may
change.** That is the acceptance test for these two, not a caveat: capture before
and after and diff.

## 5. F-020 — the consent page's duplicated mark

**Verified:** `consent.html` links exactly two stylesheets, `/tokens.css` and
`/consent.css`. `.star-mark` is byte-identical in two files, carrying a `1.7rem`
literal.

**Build: ship the token, not the link.** `--mark-lg: 1.7rem` in `tokens.css`,
which both documents already load, kills the duplication with zero new
dependency.

**Do not link `/shell.css` to the consent page.** It imports 36.5KB and three
unmeasured globals onto the one screen where a reader hands something away:
`a { color: var(--aniline) }` at **4.37:1** on manila, `:focus-visible` at
**1.88:1** on manila, and a `body` flex layout `consent.css` does not override.
That is a separate, measured call and not this wave's.

**Correction that holds:** the focus-ring is not a true duplicate — `shell.css`
sets only `outline-color` over a global shorthand the consent page has no
equivalent of.

## What "done" means

1. Items committed separately, in the repo's voice.
2. `python -m pytest -q` green, `ruff check star tests scripts harness` clean.
3. Every behaviour change carries a test; every test proven by reintroducing the
   bug.
4. No new dependency, no build step, no CDN.
5. **Two different closing standards, and do not confuse them.** `F-014` and
   `F-016` close on a re-measured screenshot: the 8px break is gone and the
   bible's ramp has one 22px line. `F-017` and `F-019` close on the opposite
   evidence — a capture that is **unchanged**. If those two move a pixel, the
   merge was wrong.
