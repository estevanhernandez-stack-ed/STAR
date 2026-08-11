# Glow wave 6 — the room after it files

**Branch:** `glow/wave-6-the-room-after-it-files`
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md)
**Measuring stick:** [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md)

`F-007`, `F-008`, `F-011` — the three highest-ranked rows left, and all three
live on one surface: the room a writer opens after a build files. The drawer they
click, the number on the docket, and the drawer's own construction.

Every figure below was **re-measured on 2026-08-11** against the filed Gdansk
room, not carried over from the audit. Where a row and this file disagree, this
file is right.

## The scope law

A wave ships only its findings. Anything found mid-build becomes a proposed
register addition — `F-022` to `F-025` all arrived that way. The invariants that
bite here:

- **Invariant 5** — contrast measured, not eyeballed. None of these three moves a
  colour; if one starts to, it restates the ratio or it is not shippable.
- **Invariant 7** — no build step. Plain CSS and plain ES modules.
- **Reduced motion** — `F-007` adds the app's second animated scroll. It honours
  `prefers-reduced-motion` through the existing helper or it does not ship.
- **Copy rule 3** — never claim a check that did not happen. `F-008` is that rule
  applied to a number rather than to a word.

Repo law: commit after each item, declarative sentence-case subjects, no
conventional-commit prefix, `Co-Authored-By: Claude Opus 5 (1M context)
<noreply@anthropic.com>`. Tests are `python -m pytest -q` and
`ruff check star tests scripts harness`. Every test proven by reintroducing the
bug it guards.

---

## F-007 — a click that sends the card off screen

**Severity 3, visibility 4. Start here; it is the one a reader feels.**

Measured, all four drawers, each from `stage.scrollTop = 0` with the rest closed:

| drawer | column | card top before | after | moved | ends |
|---|---|---|---|---|---|
| 1 | left | 351 | 351 | **0px** | visible |
| 2 | right | 351 | 974 | **+623px** | **84px below the fold** |
| 3 | left | 1089 | 1089 | **0px** | unchanged |
| 4 | right | 1089 | 1690 | **+602px** | 800px below the fold |

Viewport 890px, and `#stage` is the scroller, not the document.

**The row's scope correction is exactly right and now has numbers behind it:**
left-column drawers do not move at all, so this is a right-column defect. Drawer
2 is the clearest case — visible when clicked, gone when the click resolves.

**Build:** `toggle.scrollIntoView({ behavior: scrollBehavior(), block: "start" })`
after `setDrawerState` in `setOpen(true)` (`app.js:1190`).

**`scrollBehavior()` really is reusable here, and this is worth stating because
the identical instruction was NOT buildable in wave 3.** `F-006` asked for the
same helper and it could not be used, because a focus-driven scroll takes no
`behavior` option. This is a direct `scrollIntoView` call, which does. The helper
is alive at `app.js:280` with exactly one caller (`app.js:302`), so `F-007` is
genuinely its second consumer — the thing `F-006`'s row wrongly claimed to be.

**Decide during the build and record the answer:** should closing scroll too? A
reader who scrolled down to read an open right-column drawer will have it jump
602px upward on close. The row says `setOpen(true)` only. If the close case is a
real second defect, file it rather than fixing it here.

---

## F-008 — the number says the ledger vouched for it, and it did not

**Severity 3, visibility 4.**

`run["search_count"] += 1` sits at `server.py:470`, inside the block reading
`call.args` — the tool **call**, before any response exists. Verified in place.
It counts searches **issued**.

The copy calls them cited, in two places:

- `app.js:982` — `plural(result.search_count, "cited web search")` → "17 cited
  web searches"
- `app.js:358` — `` `${searchCount} cited searches so far` ``

**The docstring eight lines above the first one argues the opposite discipline
in its own words**, about the number right beside it:

> so it is sources SEEN, not sources cited — worth saying plainly rather than
> letting "106 sources" imply 106 footnotes.

And `drawer.js:187` already ships the correct instinct with the argument written
out: `` `${plural(searches.length, "search")} issued` ``, because *"'Issued' is
what the event proves and it costs nothing."*

**Build:** drop "cited" from both call sites. The source half already reads
"sources returned" and needs nothing. This is copy rule 3 applied to a number:
"cited" asserts the ledger vouched for those searches, which is precisely what
`search_count` cannot know.

Three surfaces print this number — the docket, the live meter, and the room —
so check all three read correctly after, not just the one you edited.

---

## F-011 — the hanging folder does not hang

**Severity 3, visibility 3.**

The row says **0px overlap**, from a pixel scan. The box measurement is **1.6px**.
Both are true and the reason matters: `.drawer-tab` carries a `clip-path`, so its
painted extent is narrower than its box, and 1.6px at the tab's sloped edges
scans as nothing.

Measured: tab `top: calc(var(--tab-rise) * -1)` = **-28px**, tab height **29.6px**,
so exactly **1.6px** of its base falls under the face. The layering is not the
problem — `drawer.css:96-108` documents the stack and it is correct
(`::after` -1, tab 0, face `::before` 1, content 2). The numbers give the face
nothing to occlude.

**Build:** `padding: 0.4rem 1.15rem 1.05rem` on `.drawer-tab` (`drawer.css:178`),
up from `0.55rem`. That is +8px of height with the top edge pinned by `--tab-rise`,
giving **~9.6px** of base under the face. Arithmetic checked against the measured
values above.

**Adjust `clip-path` in the same edit.** It is
`polygon(6% 0%, 94% 0%, 100% 100%, 0% 100%)` — percentage-based on the element
box, so growing the box re-slopes the cut sides. A taller tab with the same
percentages is a differently-angled tab.

`--tab-rise` is untouched, so the grid's derived row-gap and margin cannot drift,
and the tab is absolutely positioned, so nothing reflows.

---

## Out of scope, named so it is not re-found

- **`F-014`**, the bible's type ramp spent twice, is the natural opener for wave
  7. It is one token change on a different surface reached through a different
  control, and folding it in here would make "the filed room" mean nothing.
- **`F-016`, `F-017`, `F-019`, `F-020`** — the dedup cluster. Two of them render
  byte-identical pixels, and wave 3 already passed on them for that reason. They
  want their own wave with its own argument.

## What "done" means

1. Three items, each committed separately in the repo's voice.
2. `python -m pytest -q` green, `ruff check star tests scripts harness` clean.
3. Each behaviour change carries a test, and each test is proven to fail when
   the bug is put back.
4. No new dependency, no build step, no CDN, no new colour pair.
5. **Re-measure.** `F-007` closes on the displacement table above re-run;
   `F-011` closes on the tuck measured in a browser, not eyeballed. `F-008` is
   the one that closes on reading, and all three of its surfaces get read.
