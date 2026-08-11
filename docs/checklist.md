# STAR — Build Checklist, cycle #20

> Vibe Cartographer cycle **#20**, `/checklist`, 2026-08-10. Mode: fully-autonomous
> (*Autonomous — Self*). Persona: Architect. Deepening rounds: 0, per the builder's standing
> pattern when the substrate is understood.
>
> **This cycle is a vibe-glow wave, not an app cycle.** Its authoritative input is
> [`glow-wave-1-brief.md`](glow-wave-1-brief.md), which supersedes [`spec.md`](spec.md) and
> [`prd.md`](prd.md) for scope. It ships exactly five findings — F-004, F-005, F-013, F-001,
> F-003 — from [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md),
> measured against [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md).
>
> Cycle #19's whole-app checklist is preserved in git at `053695a`. `process-notes.md` had
> penciled #20 for the judge critique's Part 3 — that work moves to #21.

## Build Preferences

- **Build mode:** Autonomous. From the record, not re-asked: `autonomy_level:
  fully-autonomous`, experience `experienced`, and 18 prior Cart cycles run as an autonomous
  build system with structured checklists and subagent delegation.
- **Comprehension checks:** N/A (autonomous mode).
- **Git:** Commit after each item. Declarative sentence-case subjects, no conventional-commit
  prefix, matching this repo's existing voice ("Guard the progress stream with a per-run key").
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` on every commit.
  Commits are the revert points; a checkpoint that fails reverts to the last clean one.
- **Verification:** On. Checkpoints after items **3** and **5**. The spacing is deliberate:
  item 3 closes the three independent fixes, and item 5 closes the run-lifecycle work before
  resume is layered on top of it.
- **Timing law:** Items 4, 5, 6 and 7 touch a live SSE run. Each is verified **at least
  twice**. A single passing run of a race is not verification.
- **Branch:** `glow/wave-1-runs-and-work`, already checked out, off `glow-identity` so the
  wave carries the register it is built against.

## The architectural through-line

Four of these five items are not new machinery. They are wiring that the app already
contains, connected to one more caller:

- `clearCheck` already takes `keepScene`; nothing has ever passed `true`.
- `shell.js`'s running-marker branch is already written; the build path never reaches it.
- The whole resume path — stash, delete-on-read, replay-from-zero, monotonic dedupe, and a
  Cloud Run deploy pinned to one instance so a reconnect lands warm — already ships, wired to
  a single trigger.
- The issued token already lives in module scope; nothing reads it back.

That shape is why this wave is cheap and why it is worth doing first. The exception is item 5,
which adds a genuinely new interaction (arming a destructive control), and it reuses the
two-press pattern the app already ships in two other places rather than inventing a third.

## The invariants that constrain every item

From `.vibe-glow/state.json`. These outrank the items below.

- **6 — zero third-party requests.** No toast library, no notification package, no CDN.
- **7 — no build step.** Plain ES modules, plain CSS. No framework, no bundler.
- **9 — copy never promises a duration.** `star/config.py` records 146s-420s+ for one fixed
  treatment; any number is a lie told with the project's own data. Show progress, never an ETA.

---

## Checklist

- [ ] **1. An unsubmitted scene survives re-entering the room you are already in**
  Spec ref: `glow-wave-1-brief.md > F-004`
  What to build: Thread room identity through the reset path so a same-room rail click stops
  wiping the scene box. `resetRoomView(runId)` → `resetCheck({ keepScene: runId === currentRoomId })`,
  consuming `clearCheck`'s existing but unused `keepScene` parameter (`web/scriptcheck.js:672`,
  `:681`). Note the existing `setCheckRoom` guard (`:653`) is **disarmed**, not late —
  `resetCheck` sets `roomId = null` at `:667` before it can match — so do not try to rescue it;
  pass identity down instead. Then give the account panel a back control that returns to the
  previous stage without re-entering `showResults`.
  Acceptance: Typing into `#scene`, opening Your card, and clicking the same room in the rail
  leaves the text intact. Clicking a *different* room still clears it.
  Verify: Run `uvicorn star.server:app`, do both paths by hand, and add a Node test under
  `tests/js/` asserting `keepScene` is true only on a same-room reset. Confirm
  `app.js:610-612`'s documented cross-room leak fix has not regressed.

- [ ] **2. A failed build stops claiming the department is working**
  Spec ref: `glow-wave-1-brief.md > F-005`
  What to build: On `ev.type === "error"` (`web/app.js:545-549`), rewrite `#progress-panel`'s
  h2 — nothing in the app writes it today, so the static string at `web/index.html:151` stands
  after a terminal failure — and stop `.ellipsis::after`'s `pulse` (`web/shell.css:667-670`).
  Mount the failure message above the drawer grid rather than only in the timeline below it.
  Add a recovery control beside it that starts a new room **without** wiping the treatment;
  `app.js:133` is the only write to that field in the app.
  Acceptance: After a terminal error the heading names the failure, the ellipsis is static, the
  message sits above the four "Did not file" cards, and the treatment textarea still holds what
  was typed.
  Verify: Force a terminal error (a stubbed error event or a forced timeout) and read the panel.
  **Do not** move the error line for being off-screen — it is not; `addEntry` already
  `scrollIntoView`s every entry including this one (`app.js:228`). **Do not** add an ETA or
  advice about treatment length (invariant 9).

- [ ] **3. An issued token survives re-entering the card**
  Spec ref: `glow-wave-1-brief.md > F-013`
  What to build: Skip the re-read when a live plaintext exists, so `openAccount()`'s
  unconditional `replaceChildren` (`web/account.js:473`) stops discarding it. Two facts make
  this cheap and must be built on rather than worked around: `stage()` only adds `.hidden`
  (`web/shell.js:189`) so the node survives the stage switch intact, and the plaintext already
  lives in module scope at `card.issued` (`account.js:559-562`). Nothing needs storing — what is
  missing is a render path that reads what is already held.
  Acceptance: Issue a token, navigate away and back via the rail, and the same plaintext is
  still on screen, not re-issued and not lost.
  Verify: Requires an attached Google account (`account.js:393` disables the control otherwise),
  so scope the automated test to the render path and do the round trip by hand.

> **CHECKPOINT A** — the three independent fixes are in. Run `python -m pytest -q` and
> `ruff check star tests scripts harness`. Confirm the app still boots and a filed room still
> opens. Nothing after this point is independent.

- [ ] **4. A live run has a row in the rail**
  Spec ref: `glow-wave-1-brief.md > F-001`
  What to build: Call `refreshRail(runId)` immediately after `POST /api/rooms` succeeds
  (`web/app.js:411-416` currently has none, so `web/shell.js:119-127`'s `isRunning` marker
  branch is unreachable on the build path). Route that row's click to `showRunning()` when
  `run_id === liveRunId` — today `showRunning` has two callers and neither is a control, so a
  live build has no way back once Your card is opened. Decide and state whether the running row
  renders its own label: `room_to_document` reads title and era off an empty `story_profile` at
  creation (`star/store.py:62-63`), so the row otherwise reads "Untitled room · Era unstated"
  until the terminal write.
  Acceptance: Starting a build puts a row in the rail immediately, carrying the running marker.
  Clicking it returns to the live progress panel with the stream intact.
  Verify: **Twice.** Start a build, confirm the row appears while the four researchers are still
  searching, open Your card, click back, and confirm the stream is still live and the timeline
  did not restart.

- [ ] **5. New room is armed while a run is live**
  Spec ref: `glow-wave-1-brief.md > F-001`
  What to build: Arm the "New room" control while a run is live, using the two-press pattern the
  app already ships at `web/account.js:213` and `web/scriptcheck.js:598` rather than inventing a
  third idiom. First press states that the build keeps running and where to find it; second press
  proceeds. This is the one genuinely new interaction in the wave, and the reason it matters:
  `resetProgress()` → `closeStream()` ends the SSE generator only — `star/server.py:895-915` is a
  bare `while True` with no disconnect check, and the pipeline is a separate task pinned by a
  strong ref at `:836`, so the searches and Gemini calls keep spending.
  Acceptance: Pressing "New room" mid-build does not immediately close the stream. The first
  press explains; the second proceeds. With no run live, the control behaves exactly as before.
  Verify: **Twice.** Copy must not promise a duration (invariant 9). State that the build
  continues, not when it will finish.

> **CHECKPOINT B** — the run lifecycle is now visible and guarded. Full test run again. Confirm a
> build completes end to end and files a room. Resume is layered on this; do not proceed on a
> red checkpoint.

- [ ] **6. Every run is stashed, and the stash is cleared when it ends**
  Spec ref: `glow-wave-1-brief.md > F-003`
  What to build: Export `stashLiveRun` from `web/auth.js` (currently module-private; only
  `takeStashedRun` and `setLiveRunProvider` are exported) and call it from `openStream()` on
  every run rather than only from `beginGoogleLink` (`auth.js:557`). Add a companion
  clear-on-terminal export and call it from `endRun` (`app.js:577-584`), which nulls
  `liveRunId`/`liveStreamKey` but leaves the RUN_KEY stash behind — without this, a finished run
  would make the next reload open that room instead of the intake.
  Acceptance: Reloading mid-build reopens the live run and replays its timeline without
  duplicate entries. Reloading after a run has finished lands on the intake, not on the old room.
  Verify: **Twice.** The replay path is already proven — EventSource cannot set Last-Event-ID on
  fresh construction, so `_resume_cursor(None, …)` returns 0 and `generate()` yields from event 0
  while `app.js:459-462`'s monotonic guard dedupes. Confirm no duplicates in the timeline.

- [ ] **7. A running room offers a check-again, and the resume line stops lying**
  Spec ref: `glow-wave-1-brief.md > F-003`
  What to build: Give the `running` branch of `showResults` a "Check again" control re-issuing
  `GET /api/rooms/{id}`, polled while that panel is the visible one. Rewrite
  `resumeStashedRun`'s timeline line (`app.js:1141`, "Back from the sign-in. Picking the run up
  where it was.") — it is OAuth-specific and becomes false on a reload resume; branch it or make
  it neutral. State the honest limit in the code comment: `sessionStorage` covers reload and a
  same-tab lock and usually survives crash session-restore, but not a closed or new tab. The copy
  must not imply otherwise.
  Acceptance: A room still researching offers a way to re-check without a full reload. The resume
  entry reads true on both the OAuth path and the reload path.
  Verify: **Twice.** No ETA, no duration, no "about N minutes" anywhere in the added copy
  (invariant 9).

- [ ] **8. Documentation & security verification**
  Spec ref: `glow-wave-1-brief.md > What "done" means for this wave`
  What to build: Wave-scoped, proportionate to a five-item change that adds no dependency.
  **Docs:** set the seven register rows for F-001/F-003/F-004/F-005/F-013 to their true status,
  set the wave's ledger entry in `.vibe-glow/state.json` to `shipped`, append a `## /checklist`
  and build section to `process-notes.md`, and re-check that README's Quickstart still describes
  what the app does after the changes. **Comment drift:** grep comments near every changed
  surface for claims the change contradicted — a stale comment asserting the old behaviour is a
  finding of this item, fixed before the wave closes. This repo comments heavily and the audit
  showed those comments are load-bearing. **Security:** confirm no new dependency entered
  `pyproject.toml` and no CDN reference entered `web/` (invariants 6 and 7); run a secrets scan
  over the diff; confirm `.gitignore` still covers `.env`, `.mcp.json` and the evidence dir; and
  confirm `.env.example` still documents every variable the changed code reads. No new inputs
  cross a trust boundary in this wave, so the OWASP pass is a sanity check on the diff, not a
  fresh audit.
  Acceptance: `python -m pytest -q` green, `ruff check star tests scripts harness` clean, no new
  dependency, no CDN, no secret in the diff, register and ledger tell the truth.
  Verify: Run both commands, read the diff end to end, and state plainly what was checked and
  what was not.

## Gut-check

Eight items, not the usual 8-12 by padding — a wave is not an app cycle, and the register is the
backlog. Five ship findings, three are structural: two checkpoints and a close-out.

The risk concentrates in items 4-7, all of which touch a live SSE run, which is why both
checkpoints sit in front of them and why each carries the twice-verified law. The cheapest three
go first deliberately: they are independent, they prove the branch is healthy, and if the run
lifecycle work turns out harder than the traces suggest, three real fixes are already banked.
