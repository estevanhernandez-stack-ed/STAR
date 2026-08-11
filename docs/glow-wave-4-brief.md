# Glow wave 4 — the evidence itself

**Branch:** `glow/wave-4-the-evidence-itself`
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md)
**Measuring stick:** [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md)

One finding, `F-025`, on the surface the whole product exists to show: the
sourced evidence behind a claim. It was never filed by any of the five lenses,
and it is the better explanation of the "looks like a hackathon demo app"
reaction than `F-002`, which was the only row that seemed to cover it.

This brief carries the measurements the finding rests on. **Build what is here.**

## The scope law

A wave ships only its findings. Anything found mid-build becomes a proposed
register addition, not a drive-by fix — three already exist as `F-022` to
`F-024` from wave 3. The invariants that bite here:

- **Invariant 6** — no third-party requests. No markdown library from a CDN.
  DOMPurify is already vendored; nothing new joins it without being vendored.
- **Invariant 7** — no build step. Plain ES modules and plain CSS.
- **Copy rule 3 / obligation 3** — the word "verified" never reaches a reader,
  and nothing may imply the department checked a source it only retrieved.

Repo law: commit after each item, declarative sentence-case subjects, no
conventional-commit prefix, `Co-Authored-By: Claude Opus 5 (1M context)
<noreply@anthropic.com>`. Tests are `python -m pytest -q` and
`ruff check star tests scripts harness`.

---

## What was measured

On the filed **Gdansk 1978** room, in Chromium, 2026-08-11.

**Citation rail — 9 cards, 17 excerpts.**

| | |
|---|---|
| excerpts carrying markdown artifacts | **17 of 17** |
| excerpt length | 917–2573 chars, median **1462** |
| length cap anywhere in `web/` | **none** |
| card height | 1100–2087px, in a ~830px viewport |

Artifact counts across the 17: **73** pipe characters (table rows), **50**
markdown headings, **44** `**`, **30** `_italic_`, **17** `[n]`, **16**
`[[ n ]]()`.

**Drawer clips — 12 sampled.** 10 of 12 carry markdown. **1 of 12** contains the
`<strong>` tag that `clip.js`'s DOMPurify allowlist exists to preserve.

**The Sony Walkman card, by rendered height:** stamp+type 27px, claim 25px,
`VERDICT_READING` 42px, **the answer 21px**, standing caveat 84px, legend 14px,
citations **1421px**. The answer is **1.2%** of a 1730px card. The citation
block is **82%**.

## The three openings that decide the fix

These are real excerpt openings, not constructed examples:

```
|Entry Gate No.
# Lista uzbrojenia i wyposażenia indywidualnego żołnierza…  ## Współczesne…  |  | Mundur „Tytan” | 2024 |
[](https://en.wikipedia.org/wiki/File:GDANSK,_Falowiec_na_Obroncow_Wybrzeza.JPG) [Gdańsk](https://…) 's longest falowiec at…
```

**A character cap or a first-sentence cap would frequently cap a table cell or
an empty image link.** That is why the order below is not negotiable.

## Build

**1. Establish the payload's real format before writing a stripper.**

`scriptcheck.js:21-31` states the API returns HTML — `<strong>` match
highlighting and entities like `&quot;` — "verified against the stored
Detroit-1929 room". Today's excerpts are markdown. Either the API changed its
output or it varies by source, and a stripper written against the wrong format
is wasted work. Check the stored Detroit-1929 room against the Gdansk one
before touching either renderer. **Both comments are wrong today if the format
changed, and correcting them is part of this item, not a follow-up.**

**2. Strip structure, then take prose, then cap. In that order.**

- Drop non-prose lines outright: headings, table rows, bare and empty image
  links, caption fragments.
- Unwrap inline markdown to its text: `[label](url)` to `label`, `**x**` and
  `_x_` to `x`, `[[ n ]]()` and `[n]` to nothing.
- Take the first surviving prose paragraph, then cap.
- Cap at a **sentence boundary**, not a character count, with a character
  ceiling as the backstop. A quotation cut mid-word is the defect
  `d089b34` already fixed once on the bible.

**3. Keep the highlight where it exists, and stop paying for it where it does
not.** `clip.js` runs excerpts through DOMPurify to preserve `<strong>`, which
appears in 1 of 12 clips. That machinery is not wrong and should not be removed
— but the stripper must run in a defined order relative to it, and
`scriptcheck.js`'s `plainExcerpt` must reach the same text by its own route,
since that file's standing property is that no string in it ever becomes markup.
**Do not weaken that property to share code.**

**4. Both surfaces, one behaviour.** The citation rail and the drawer clips read
the same ledger and must show the same shape of quotation. `F-017` and `F-019`
already record that these two surfaces duplicate rules; this is a third pair.
Whether the stripper lands in a shared module is a judgment call for the build —
`plainExcerpt` and `renderExcerpt` have genuinely different output contracts.

## Out of scope, on purpose

**`F-002` is held for wave 5.** Its fix demotes `VERDICT_READING` to a slug, and
four of the nine measured cards carry no note at all — every one `confirmed`,
because `verdicts.py:91` requires a note only for `unverifiable`. On those four
the demoted sentence is the only prose the card has. The real question is
whether `confirmed` and `anachronism` should owe the reader a sentence, which is
a `star/verdicts.py` contract change whose blast radius reaches the verdict
distribution: a stricter parse pushes unannotated claims into `unverifiable`.
That deserves a measurement against a real run, not a decision made while
building something else.

## What "done" means

1. Each item committed separately in the repo's voice.
2. `python -m pytest -q` green, `ruff check star tests scripts harness` clean.
3. Every behaviour change carries a test in the repo's own framework, and every
   test is proven by reintroducing the bug it guards.
4. No new dependency, no build step, no CDN.
5. **Verification honesty.** Re-measure the same nine cards after the change and
   state the new proportions. A close-out that says "excerpts are cleaner"
   without a number is not a close-out — the finding was filed on numbers and
   closes on numbers.
