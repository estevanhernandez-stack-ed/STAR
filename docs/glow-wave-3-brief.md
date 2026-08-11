# Glow wave 3 — without sight or a mouse

**Branch:** `glow/wave-3-without-sight-or-a-mouse`
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md)
**Measuring stick:** [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md)

Five findings, one theme. Every one of them is invisible in all 14 captures and
undetectable by axe or Lighthouse — live-region absence is not machine-checkable
— which is exactly why they survived a 67-finding audit and two waves.

Each fix below carries the corrections its skeptic made. **Build what is here,
not what the register row says**, and where they differ this file is right.

## The scope law

A wave ships only its findings. Anything found mid-build becomes a proposed
register addition, not a drive-by fix. The invariants that bite here:

- **Invariant 5** — contrast measured, not eyeballed. 4.5:1 text, 3:1 controls
  and boundaries. A finding that moves a colour pair restates the ratio.
- **Invariant 6** — no third-party requests. No a11y library, no CDN.
- **Invariant 7** — no build step. Plain ES modules and plain CSS.
- **Invariant 9** — copy never promises a duration. Anything announced must show
  progress, never an ETA.

Repo law: commit after each item, declarative sentence-case subjects, no
conventional-commit prefix, `Co-Authored-By: Claude Opus 5 (1M context)
<noreply@anthropic.com>`. Tests are `python -m pytest -q` (globs the Node suites)
and `ruff check star tests scripts harness`.

---

## F-012 — a 146-420s build says nothing to a screen reader

**Severity 4, visibility 2.** Start here; it is the largest barrier.

An exhaustive grep of all 22 files in `web/` for `aria-live`, `role="status"`,
`role="alert"`, `role="log"`, `aria-busy` and `aria-atomic`, plus every
`setAttribute` call, returns **exactly two live regions in the whole app** —
`scriptcheck.js:476` and `index.html:209`, both on the check surface, neither in
`#progress-panel`. Between pressing Build and the room appearing, focus sits on
`<body>`, the panel swap is a class toggle, and the literal status messages go
into an inert `<ul>`.

**Build:**
- `aria-live="polite" aria-relevant="additions"` on `#timeline` **only**. Each
  entry lands as one atomic addition, entries are never rewritten after
  insertion, and the sole removal (`resetProgress`) runs before the panel is
  revealed.
- **Do not live-region `#search-meter` or the drawer bodies.** `updateMeter`
  rewrites them on a 1000ms interval and they would babble.
- Only the `complete` branch needs a closing entry — `partial` and `error`
  already call `addEntry`.

**Honest limit to record in the code:** the first entry fires in the same
synchronous task that un-hides the panel, so some AT will drop that one
announcement. The rest are unaffected. Say so rather than implying full
coverage.

---

## F-006 — the answer to a paid request arrives in silence

**Severity 3, visibility 4.** Merged: L3-12 and L5-3 are **one edit**, because a
native `.focus()` on a `tabindex="-1"` element also scrolls it into view.

`mountResult` does `replaceChildren` + `classList.remove("hidden")` and nothing
else. A grep for `scrollIntoView|scrollTo|scrollTop|\.focus\(\)` across all of
`web/` returns exactly one scroll call in the entire app — on the build timeline
— and none in `scriptcheck.js`. So the visible feedback for a request that just
spent live searches is a status line clearing and a button re-enabling.

**Build:**
- Move focus to a **named heading** inside the result. **Not** the unnamed
  `role=generic` wrapper — it would announce nothing useful or dump the whole
  subtree.
- Let the focus call do the scrolling. Do not also call `scrollIntoView`, or it
  double-scrolls.
- Reuse `scrollBehavior()` (`app.js:217`) — it reads `matchMedia` at call time
  and returns `"auto"` under reduce. It is authored once with one caller today;
  lift it into a shared module rather than copying it.
- **Root cause of the focus drop is `els.run.disabled = true` (`:726`)**, not
  the mount. The finding never named it.
- Keep `#check-status` and write the result's meter line into it rather than
  clearing it, so the status region says what landed.

---

## F-010 — every failure message in the app is silent

**Severity 3, visibility 3.**

`#intake-error` and `#check-error` are bare spans written via `textContent`,
with no role and no focus move. `#check-status` has `role="status"` but the
errors go to a sibling span that does not. Includes the message saying the
department cannot be reached at all.

**Build:**
- `role="alert"` on `#intake-error` and `#check-error`. Both ship empty and get
  text written in, which is what alert fires on. ARIA19 is the canonical
  technique for post-submit form errors.
- `#auth-error` is the exception and needs one more step: it ships **with** its
  sentence and is revealed by removing `.hidden`, which fires nothing. Ship the
  div empty with the role, move the sentence to a constant, and write it in at
  the two reveal sites (`app.js:364`, `:1218`).

**Do not apply the role to `.consent-refusal` as a class.** Six of its seven
construction sites ship **with their text at build time** as static first-paint
prose; only `consent.js:451` is created empty and written into. A class-wide
role would make six paragraphs assertive live regions at page load — the same
defect this finding diagnoses, six times over. Scope it to `:451` imperatively.

**Also in scope, uncited by the finding:** `.consent-status` (`consent.js:450`)
takes WORKING and ATTACHING with no role — the same 4.1.3 gap on the consent
page's working state.

---

## F-009 — the flagged-room marker is unreadable and colour-only

**Severity 3, visibility 3.** Every ratio below was independently recomputed and
matched, four for four.

An 8px dot is the only signal a run errored or was interrupted. `--oxide`
`#B3341F` is **2.79:1** on `--drawer-shadow` (recorded, `shell.css:154-158`) and
**2.37:1** on `--cabinet` once `.rail-room.active` repaints the row (recorded,
`:719`). It is `aria-hidden`, and `.rail-room-meta` renders only `era · date`,
so no screen-reader user gets the status and it is carried by colour alone.
WCAG 1.4.11 and 1.4.1.

**Build:**
- Repaint `.rail-room.flagged .rail-room-marker` with
  `color-mix(in srgb, var(--oxide) 70%, var(--manila))` — the shade
  `#timeline li.error::before` already uses, argued on the record. Resolves to
  `#BC5C40`: **3.28:1 on `#232B27`** (recorded, `shell.css:722`) and **3.87:1 on
  `#171D1A`** (computed here, unrecorded anywhere — record it). Both clear 3:1.
- **Scope to `.flagged` only.** `--manila-edge` (6.73:1) and `--pencil`
  (4.80:1) already pass on the rail ground; do not generalise to
  `.rail-room-marker`.
- Append the status word to `.rail-room-meta` (`shell.js:134`) so the fact is
  not colour-only. Leave the dot `aria-hidden`.

The 1.3.1 citation in the register is the weakest of the three; 1.4.11 and 1.4.1
carry this on their own.

---

## F-021 — the writer's own pages can be unreachable by keyboard

**Severity 2, visibility 1.** Smallest, and it must land as one edit.

A scene runs to 8000 characters inside `max-height: 32rem; overflow-y: auto`
(`scene.css:250-266`). The zero-marks state is **designed for** — `server.py:1071-1094`
writes a dedicated cover note for "a scene of pure interior dialogue [that]
asserts nothing about the world", and the rail ships bespoke copy for it. In
that state the scroller holds no focusable child at all.

**Build:**
- `tabindex="0"` **plus** a role **plus** an accessible name on `.scene-page`,
  together. Separately they are worse than nothing: a tab stop with no name.
- Prefer **`role="region"`** over `role="group"`. MDN's guidance is that `group`
  should not carry major perceivable sections, and the marked scene is the
  primary content of the result; region also earns a landmark stop.
- The current `aria-label` on a bare div is an ARIA authoring-conformance error
  (`generic` is name-prohibited) — though, contrary to the register row, **all
  three engines do expose it**; the variance is at the screen-reader layer.
- The existing `:focus-visible` ring on `.check` covers it (`shell.css:139-141`,
  `--ink` at 12.70:1 on onionskin). No new pair.

**Browser facts, corrected from the register row:** Firefox has made scrollers
tab stops since **Firefox 4 (2011)**, so this is **Safari-only**, not two
engines. Chrome's stable landing was **132**, not 127. Accept the permanent tab
stop deliberately — a short scene that never overflows still gets one — and say
so in the code.

---

## What "done" means

1. Five items, each committed separately in the repo's voice.
2. `python -m pytest -q` green, `ruff check star tests scripts harness` clean.
3. Each behaviour change carries a test in the repo's own framework.
4. No new dependency, no build step, no CDN.
5. **Verification honesty:** none of these five is visible in a screenshot. Say
   plainly what was verified by reading the accessibility tree, what by source,
   and what remains unverified without a real screen reader. A capture proves
   nothing here, and a close-out that implies otherwise is worse than one that
   admits the gap.
