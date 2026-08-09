# GUI Phase 3 — The Morgue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the room as a clipping library where every fact carries a stamp saying who found it, where, and when — so a screenwriter who distrusts AI can see the research is real before reading a word of copy.

**Architecture:** Native ES modules, no build step, zero third-party browser requests. A cabinet-green shell holds a rail of saved rooms and a main stage of four manila drawers. One `Drawer` component serves the live run and the finished room. The clip — one fact, its stamp, its receipt, and the scene it unlocks — is the unit of the product; the assembled bible is secondary.

**Tech Stack:** Vanilla ES modules, CSS custom properties, self-hosted WOFF2, `marked` + DOMPurify vendored locally.

**Design direction:** `docs/design/DIRECTION.md` — read it first. It is the decision record and carries the reasoning this plan only implements.
**Research:** `docs/design/research-*.md`, `docs/design/critique-adversarial.md`, `docs/design/visual-directions.md`.
**Spec:** `docs/superpowers/specs/2026-08-09-star-gui-design.md` — superseded by DIRECTION.md wherever the two disagree.

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtime AI is Google Cloud only.** No other AI provider anywhere. Hackathon disqualification criterion.
- **The Parallel Search API must genuinely execute at runtime** via `parallel-web` in `star/tools/parallel_search.py`. Do not modify or stub it. Disqualification criterion.
- **Zero third-party browser requests.** No CDN, no Google Fonts link, no remote anything. Every font and library is a file in `web/vendor/`. The only permitted external calls are Google's identity endpoints in `web/auth.js`, which are the auth provider.
- **No build step.** Native ES modules, plain CSS. No `package.json`, no bundler, no preprocessor.
- **`star/ledger.py` and `star/findings.py` stay pure.** Do not import them into anything with I/O.
- **`star/store.py` is the only module that touches Firestore.**
- **No secret may reach the browser.** `FIREBASE_API_KEY` is a public project identifier and is safe; `GOOGLE_API_KEY` and `PARALLEL_API_KEY` are secrets.
- **Never commit `.env`.**
- **Commit style:** sentence-case imperative, not Conventional Commits.
- Suite is at 154 passing, 7 pre-existing third-party deprecation warnings, `ruff check star tests scripts` at 0 findings. Keep all three.
- Server-side changes should be minimal. If a task seems to need a new endpoint, check whether `GET /api/rooms` and `GET /api/rooms/{id}` already carry the data — they usually do.

## The two rules that make or break the direction

Copied from `DIRECTION.md` because a task implementer will not read that file's reasoning, only this plan's requirements.

1. **Manila (`#D2B98C`) must own more than 40% of the room's pixel area in the filed state.** `#232B27` is dark; if the cards shrink to accent-sized chips the page becomes near-black-with-a-warm-accent, which is the exact AI-default look being avoided. The cards are the page; the cabinet is the frame. Task 3 measures this, not by eye.
2. **The stamp stays typographic.** No distress textures, no rotation past 2.5 degrees, no gradients anywhere in the design. Aniline violet is a flat stamp-ink solid used only for a verified state — the moment it becomes a gradient or a brand wash, the direction has failed on its own terms.

## What the research obliges, beyond the visuals

Each is owned by a specific task; none is a polish item.

| # | Obligation | Owner |
| --- | --- | --- |
| 1 | Every finding shows the scene it unlocks, from `ResearchQuestion.why` | Task 5 |
| 2 | Every citation is click-through to the real ledger excerpt | Task 5 |
| 3 | Say what was actually checked — never the bare word "verified" | Task 5 |
| 4 | Show real uncertainty: `parse_rate`, `unverified_count`, researcher notes | Task 5 |
| 5 | State what happens to the treatment, in the intake, before the paste | Task 2 |
| 6 | Never promise a duration; show progress, not an ETA | Task 4 |
| 7 | Use "grounded"; never "lookbook"; prefer source type over source count | Tasks 2, 5 |

## How this phase is verified

There is no JS test runner and this plan does not add one. Visual work is verified by driving a real browser.

**Every task ends with the controller driving Playwright** against a local server: navigate, interact, screenshot, and check the specific assertions that task lists. A task is not done until its screenshot has been looked at. Implementers should state plainly what they could not verify without a browser rather than claiming it works.

The Python suite still guards the API and must stay green, but it will not catch a broken grid.

---

### Task 1: Vendor everything, and build the token layer

Nothing renders until the type and palette exist, and the CDN tags are a demo-day failure mode that should die first.

**Files:**

- Create: `web/vendor/fonts/` (WOFF2 files)
- Create: `web/vendor/marked.min.js`, `web/vendor/purify.min.js`
- Create: `web/tokens.css`
- Modify: `web/index.html` (drop the CDN script tags, add the local ones)
- Modify: `.gitignore` if needed — **vendored files must be committed**, not ignored

**Interfaces:**

- Produces: the CSS custom properties every later task consumes, and `window.marked` / `window.DOMPurify` from local files.

- [ ] **Step 1: Fetch the three typefaces as WOFF2**

All three are SIL OFL and self-hostable. Download the actual font binaries into `web/vendor/fonts/`:

- **Archivo Narrow** — Omnibus-Type, on Google Fonts. Need Regular (400) and Bold (700).
- **Newsreader** — Production Type, on Google Fonts. **Fetch the variable font** if available; its `opsz` axis is load-bearing, because the bible is a long read at one size and clip excerpts are captions at another. If only static instances are available, fetch 400, 500, and the 400 italic.
- **Sligoil** — Velvetyne Type Foundry, at `velvetyne.fr`. Need the Regular weight. **If Sligoil cannot be fetched cleanly, fall back to Sometype Mono or DM Mono** (both OFL) and say which you used in your report.

Do **not** add a Google Fonts `<link>`. Download the files. Verify each is a real WOFF2 by checking the file magic (`wOF2`) rather than trusting the extension — a 404 HTML page saved as `.woff2` is the classic failure here.

- [ ] **Step 2: Vendor `marked` and DOMPurify**

Fetch `marked.min.js` and `purify.min.js` and place them in `web/vendor/`. Pin the same versions `index.html` currently references from cdnjs (marked 12.0.2, DOMPurify 3.1.6) so behaviour does not change under us. Verify each file starts with JavaScript and not an HTML error page.

- [ ] **Step 3: Write `web/tokens.css`**

```css
/* THE MORGUE — the clipping library behind the newsroom.
   Every value here is a decision recorded in docs/design/DIRECTION.md.
   Two rules govern this file:
     - Manila owns >40% of the room's pixel area in the filed state.
     - Aniline is a flat stamp-ink solid. Never a gradient. Never a brand wash.
*/

@font-face {
  font-family: "Archivo Narrow";
  src: url("/vendor/fonts/archivo-narrow-400.woff2") format("woff2");
  font-weight: 400; font-display: swap;
}
@font-face {
  font-family: "Archivo Narrow";
  src: url("/vendor/fonts/archivo-narrow-700.woff2") format("woff2");
  font-weight: 700; font-display: swap;
}
@font-face {
  font-family: "Newsreader";
  src: url("/vendor/fonts/newsreader.woff2") format("woff2");
  font-weight: 200 800; font-display: swap;
}
@font-face {
  font-family: "Newsreader";
  src: url("/vendor/fonts/newsreader-italic.woff2") format("woff2");
  font-weight: 200 800; font-style: italic; font-display: swap;
}
@font-face {
  font-family: "Sligoil";
  src: url("/vendor/fonts/sligoil.woff2") format("woff2");
  font-weight: 400; font-display: swap;
}

:root {
  /* Cabinet — the frame, never the subject */
  --cabinet: #232B27;        /* olive-drab steel furniture, not "dark mode" */
  --drawer-shadow: #171D1A;  /* the recessed well; one step down, never black */

  /* Manila — the cards ARE the page */
  --manila: #D2B98C;
  --manila-edge: #B99F70;    /* folder edge, tab shadow */
  --onionskin: #E9E2D2;      /* expanded reading surface. A COMPONENT.
                                If this ever becomes a page ground, the
                                direction lands in the cream-and-serif
                                default by the side door. */

  /* Stamp pads — exactly two, each meaning exactly one thing */
  --aniline: #5C3D91;        /* FILED. Flat ink. Never a gradient. */
  --oxide: #B3341F;          /* FLAGGED. UNSOURCED, and later anachronism. */

  /* Pencil — metadata, labels, and the unstamped state */
  --pencil: #7E8B7F;
  --ink: #1B211D;            /* text on manila */

  /* Type */
  --label: "Archivo Narrow", "Arial Narrow", sans-serif;
  --body: "Newsreader", Georgia, serif;
  --slug: "Sligoil", "SFMono-Regular", ui-monospace, monospace;

  /* Scale — a filing label is small and wide-tracked; body text is not */
  --label-sm: 0.6875rem;  /* 11px drawer plates, stamp slugs */
  --label-md: 0.8125rem;  /* 13px folder tabs */
  --text-sm: 0.875rem;    /* 14px clip excerpts */
  --text-md: 1.0625rem;   /* 17px findings */
  --text-lg: 1.375rem;    /* 22px room title */

  --track-label: 0.14em;  /* labels are tracked wide; body text never is */
}

@media (prefers-reduced-motion: reduce) {
  :root { --stamp-duration: 0ms; }
}
:root { --stamp-duration: 220ms; }
```

**Note the `prefers-reduced-motion` block precedes the default deliberately** so the default wins in specificity order — verify this actually works rather than assuming; if it does not, invert it.

- [ ] **Step 4: Swap the CDN tags for local files**

In `web/index.html`, replace the two `cdnjs.cloudflare.com` script tags with `/vendor/marked.min.js` and `/vendor/purify.min.js`, and add `<link rel="stylesheet" href="/tokens.css">` before the existing stylesheet.

- [ ] **Step 5: Verify zero third-party requests**

Run the server, then grep the served HTML and CSS for external origins:

```bash
.venv/Scripts/python.exe -m uvicorn star.server:app --port 8000 &
curl -s http://localhost:8000/ | grep -o 'https\?://[^"'"'"']*' | sort -u
```

Expected: nothing but the GitHub source link in the footer. No `cdnjs`, no `fonts.googleapis`, no `fonts.gstatic`.

Then confirm each font actually loads:

```bash
for f in web/vendor/fonts/*.woff2; do
  printf "%-40s %s\n" "$(basename $f)" "$(head -c 4 "$f")"
done
```

Expected: every line ends in `wOF2`.

- [ ] **Step 6: Run the Python suite and ruff**

Run: `.venv/Scripts/python.exe -m pytest -q` — expected 154 passing.
Run: `.venv/Scripts/python.exe -m ruff check star tests scripts` — expected 0 findings.

- [ ] **Step 7: Commit**

```bash
git add web/vendor web/tokens.css web/index.html
git commit -m "Vendor the morgue's type and libraries, kill the CDN"
```

---

### Task 2: The cabinet — shell, rail, and an honest intake

**Files:**

- Modify: `web/index.html`
- Create: `web/shell.js`
- Create: `web/shell.css`
- Modify: `web/app.js`

**Interfaces:**

- Consumes: tokens from Task 1; `GET /api/rooms` (already built in Phase 2).
- Produces:
  - `renderRail(rooms, activeRunId)` — draws the saved-room list
  - `loadRoom(runId)` — fetches and hands off to the room renderer
  - `showIntake()` / `showRoom()` / `showRunning()` — stage state switches

- [ ] **Step 1: Restructure `index.html` around cabinet and stage**

A persistent left rail in `--drawer-shadow`, a main stage in `--cabinet`. The rail lists saved rooms from `GET /api/rooms` with title, era, and date — `room_summary` already returns exactly these fields and deliberately omits the bible, so the rail is cheap.

Room titles come from `story_profile.title`. A room still running shows a pencil-coloured marker; nothing spins.

- [ ] **Step 2: Write the intake, and tell the truth in it**

This is research obligation 5 and it is not optional. Before the paste, the intake must say what happens to the treatment. Plain, specific, no reassurance theatre:

> Your treatment is stored with your research so you can come back to it. It is visible only to this browser's session. Nothing is used to train anything.

Check every clause is actually true of our system before shipping it. If any clause cannot be verified from the code, cut that clause rather than soften it — an unverifiable privacy claim is worse than no claim.

The intake heading and hint should use **"grounded"** (research obligation 7). Never "lookbook."

- [ ] **Step 3: Wire the rail to real data**

On load: sign in (already silent), `GET /api/rooms`, render the rail. Clicking a room loads it. "New room" returns to the intake.

Handle the empty rail as an invitation, not a void — an empty screen is a moment for direction. One line under the intake, not a centred grey "No rooms yet."

- [ ] **Step 4: Verify in a browser**

The controller will drive Playwright and check:

- The rail renders saved rooms and clicking one loads it
- The intake states the retention policy above the fold
- The cabinet reads as furniture, not as a dark-mode dashboard
- No console errors, no failed requests

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/shell.js web/shell.css web/app.js
git commit -m "Build the cabinet shell with a saved-room rail and an honest intake"
```

---

### Task 3: The drawer — one component, five states

The heart of the phase. A hanging folder with a cut tab, serving both the live run and the filed room.

**Files:**

- Create: `web/drawer.js`
- Create: `web/drawer.css`

**Interfaces:**

- Consumes: tokens from Task 1.
- Produces:
  - `createDrawer(category)` → a DOM element
  - `setDrawerState(el, state, data)` where state is `"idle" | "searching" | "filed" | "failed" | "expanded"`
  - `DRAWER_LABELS` — the four drawer plates: Setting & Atmosphere, Objects & Props, Logistics, Forces & Conflicts

**Build the static states before any motion.** A drawer that only reads correctly while animating is a drawer that fails as a still frame, which is one of the four demo requirements. Motion lands in Task 4.

- [ ] **Step 1: Build the 2×2 grid and the four drawers**

Each drawer is a manila card with a cut tab carrying its plate label in `--label` at `--label-sm` with `--track-label`. Beneath: the count line in `--slug`.

State reference:

```text
IDLE        tab pencil, card at rest, no counts
SEARCHING   tab marked, current objective in --slug beneath,
            one dot per landed search
FILED       stamp present, counts shown: facts, sources, questions
FAILED      tab in --oxide, "did not file" in plain language
EXPANDED    Task 5 owns this
```

- [ ] **Step 2: Enforce the Manila rule, by measurement**

The 40% rule is a hard constraint, not a feeling. Measure it in the browser:

```javascript
// Run in the console against the filed state at 1440x900.
const total = innerWidth * innerHeight;
const manila = [...document.querySelectorAll(".drawer, .clip, .tab")]
  .reduce((sum, el) => {
    const r = el.getBoundingClientRect();
    return sum + Math.max(0, r.width) * Math.max(0, r.height);
  }, 0);
console.log((manila / total * 100).toFixed(1) + "% manila");
```

Expected: **above 40%.** If it comes in lower, the cards are too small or the gutters too wide — fix the layout, do not adjust the rule.

- [ ] **Step 3: Verify in a browser**

Controller drives Playwright with a stubbed filed room and checks:

- All four drawers render at 1440×900 with no overflow
- The manila measurement clears 40%
- A screenshot of the filed state reads as a filing cabinet with cards, and would carry the idea as a still frame with no motion and no explanation

- [ ] **Step 4: Commit**

```bash
git add web/drawer.js web/drawer.css
git commit -m "Build the drawer component in its five states"
```

---

### Task 4: The live run — route by category, and stamp

**Files:**

- Modify: `web/app.js`
- Modify: `web/drawer.js`, `web/drawer.css`

**Interfaces:**

- Consumes: `createDrawer` / `setDrawerState` from Task 3.
- Produces: SSE events routed into drawers by `ev.category` — already carried on every search event since Phase 1, so this is routing, not parsing.

- [ ] **Step 1: Route the stream into the drawers**

`search` events carry `category`; route each to its drawer, show the objective, add a dot. `agent_done` files that drawer. `complete` and `partial` end the run. `warning` surfaces the empty-ledger signal. `error` shows the message the server sent, which is already generic by design.

**Research obligation 6: never promise a duration.** No ETA, no progress bar implying completion, no "about four minutes." Our own `config.py` records 146s to 420s+ for one fixed treatment. Show what is happening, not when it will end. Elapsed time is honest; predicted time is not.

- [ ] **Step 2: Build the stamp**

The signature moment. A finding lands unstamped; the stamp presses down carrying the domain, the retrieval date, and the researcher's code.

Typographic only — `--slug` in `--aniline`, a 1px rule box, rotation no more than 2.5deg. **No distress texture, no gradient, no image.** The press is a short scale-and-settle over `--stamp-duration`, which is 0ms under `prefers-reduced-motion`.

- [ ] **Step 3: Verify in a browser**

Controller runs a real build (one live build, roughly fifteen searches) and checks:

- Objectives appear in the right drawers, and drawers fill visibly in parallel
- The stamp lands and reads at a glance
- Nothing anywhere claims a completion time
- A mid-run screenshot shows four drawers working simultaneously

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/drawer.js web/drawer.css
git commit -m "Route the live run into the drawers and land the stamp"
```

---

### Task 5: The expanded drawer — clips, receipts, and the truth about what we checked

Where the product earns trust. This task owns four of the seven research obligations.

**Files:**

- Create: `web/clip.js`
- Create: `web/clip.css`
- Modify: `web/drawer.js`

**Interfaces:**

- Consumes: the `categories` payload from `GET /api/rooms/{id}` — `findings[]`, each with `fact`, `citations[]` (`url`, `title`, `excerpt`), and `unverified_urls[]`, plus `parse_rate`, `unverified_count`, `field_notes`.
- Produces: `renderClip(finding, sceneNeed)` and `expandDrawer(category, doc, plan)`.

- [ ] **Step 1: Render the clip**

One finding is one clip. The fact in `--body` at `--text-md` on `--onionskin`. Beneath it, receipts as small manila fragments in `--slug`: **domain on the face, full URL as the link target** with `rel="noopener noreferrer"`. Multiple citations stack as overlapping offset clips; clicking one lifts it and reveals the ledger excerpt verbatim.

**Research obligation 2:** a citation that cannot be clicked through to its real excerpt is worse than no citation — people trust a cited answer more even when it is wrong. Click-through is what makes it honest.

- [ ] **Step 2: Show the scene each finding unlocks**

**Research obligation 1, and the highest-value change in this phase.** `research_plan.questions[]` carries `why`, described in our own model as *"What scene-writing need this answers."* Join by `category` and surface it on the clip — one line, `--pencil`, labelled as what it is.

We cannot join per-finding, only per-category, so present it honestly at that level: what this researcher was asked and why it matters to a scene. Do not fabricate a per-finding link we do not have.

- [ ] **Step 3: Stamp the unsourced clip, and say exactly what was checked**

A finding with `unverified_urls` gets the second pad: `UNSOURCED` in `--oxide`, angled, **and the clip stays on screen.**

**Research obligation 3.** Do not write "verified." Our check proves the source genuinely came back from a search; it says nothing about whether the fact matches it. Copy must be precise about that narrow claim. Something in this register, refined in place:

> This source was returned by a live search and its title and excerpt come from the page itself.

and for the failure:

> This link was not among the sources the researcher received. It has not been shown to you as a source.

- [ ] **Step 4: Show real uncertainty**

**Research obligation 4.** Surface `parse_rate` when it is below 1.0, `unverified_count` per drawer, and the researchers' own "verify before writing" notes from `field_notes`. Calibrated confidence is the differentiator — ChatGPT signalled uncertainty 15 times across 200 responses while producing 134 wrong citations. We have real uncertainty data. Show it plainly, without alarm.

- [ ] **Step 5: Verify in a browser**

Controller drives Playwright against a real room and checks:

- Clicking a receipt reveals the actual ledger excerpt
- A finding with an unverified URL shows `UNSOURCED` and stays visible
- The scene-need line renders per drawer
- No copy anywhere says the bare word "verified"

- [ ] **Step 6: Commit**

```bash
git add web/clip.js web/clip.css web/drawer.js
git commit -m "Render clips with their receipts, their scene, and their stamps"
```

---

### Task 6: The bible, and the partial room

**Files:**

- Modify: `web/app.js`, `web/shell.js`
- Create: `web/bible.css`

- [ ] **Step 1: Make the bible a secondary surface**

Reachable from the room header, not the default view. Full-width `--onionskin`, `--body` with the `opsz` axis set for long reading. Rendered through the vendored `marked` and DOMPurify — it is synthesised from live web content and remains an adversarial data path.

- [ ] **Step 2: Give `partial` a real state**

A run that overran returns findings with no bible. The spec never imagined this and the current UI shows an italicised apology.

Treat it as a **complete outcome of a different shape**: the drawers are full, the clips are stamped, and the bible surface says the editor did not finish assembling — in the interface's voice, without apologising, and without implying the research failed. It did not.

- [ ] **Step 3: Verify in a browser**, including a simulated partial room.

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/shell.js web/bible.css
git commit -m "Make the bible secondary and give a partial room its own state"
```

---

### Task 7: Responsive, accessible, and good as a still

**Files:** all `web/*.css`

- [ ] **Step 1: Collapse the grid below 900px** — 2×2 becomes one column; the rail becomes a top bar. The cards must stay large enough that manila still dominates.
- [ ] **Step 2: Quality floor** — visible keyboard focus on every interactive element, `prefers-reduced-motion` honoured by the stamp, contrast checked for `--pencil` on `--cabinet` and `--ink` on `--manila`.
- [ ] **Step 3: The still-frame pass.** Screenshot the filed room at 1440×900 and ask whether it carries the whole idea with no motion and no explanation. This is one of the four demo requirements and the frame most likely to appear in the submission gallery. Remove one thing — the design skill's advice, and it is usually right.
- [ ] **Step 4: Commit**

```bash
git add web/
git commit -m "Collapse to one column, honour reduced motion, and cut one thing"
```

---

## Done when

- Zero third-party browser requests; every font and library served from `web/vendor/`.
- Four drawers fill visibly in parallel during a live run, and the same four read as a filing cabinet when filed.
- Manila owns more than 40% of the room's pixel area, measured.
- Every citation clicks through to its real ledger excerpt.
- Every finding shows the scene it unlocks.
- An unsourced citation is stamped and stays on screen.
- Nothing claims a duration; nothing says the bare word "verified."
- The intake states what happens to the treatment before the paste.
- The filed room reads as a still frame with no motion and no explanation.
- 154 Python tests pass; ruff reports 0 findings.

## Not in this phase

- Script Check and its inline-annotated scene. Phase 4.
- The export zip.
- Source-type inference (primary versus secondary). Research says it matters; doing it properly needs a classifier we do not have, and guessing from the domain would be exactly the unearned confidence this design exists to avoid.

## After this phase, before the video

**Deploy.** The adversarial critique caught that the live URL serves the old UI. A judge clicking through from the submission must find what they watched. `bash scripts/deploy.sh` with `FIREBASE_API_KEY` set.
