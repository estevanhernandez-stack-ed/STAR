# Glow wave 1 — runs and work

**Branch:** `glow/wave-1-runs-and-work`
**Register:** [`superpowers/research/2026-08-10-star-ui-audit-findings.md`](superpowers/research/2026-08-10-star-ui-audit-findings.md)
**Measuring stick:** [`superpowers/specs/2026-08-10-star-design-language.md`](superpowers/specs/2026-08-10-star-design-language.md)

Five findings, one theme: **a writer loses work, loses a credential, or keeps
paying for a run they can no longer see.** Each survived a dedicated adversarial
skeptic that traced the control flow and, in several cases, corrected the fix.
The corrections are load-bearing and are written into each item below — build
what is here, not what the original finding said.

## The scope law for this wave

A wave ships only its findings. Anything discovered mid-build becomes a proposed
register addition, not a drive-by fix. The nine invariants in
`.vibe-glow/state.json` outrank every item here; the two that will actually bite:

- **Invariant 6 — zero third-party requests.** No toast library, no notification
  package, no CDN. Every fix below is hand-written.
- **Invariant 7 — no build step.** Plain ES modules and plain CSS only.
- **Invariant 9 — copy never promises a duration.** Anything added to the
  progress or rail surfaces shows progress, never an ETA. `star/config.py`
  records 146s to 420s+ for one fixed treatment; any number would be a lie told
  with the project's own data.

Repo law, from `docs/checklist.md` and the git history: commit after each item,
declarative sentence-case subject lines with no conventional-commit prefix, and
`Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` on every
commit. Tests are `python -m pytest -q` (which globs the Node suites under
`tests/js/`) and `ruff check star tests scripts harness`.

---

## F-004 — A rail click on the room you are already in wipes an unsubmitted scene

**Severity 4, visibility 3.** Smallest and most contained. Start here.

Every rail row wires to `loadRoom(room.run_id)` (`web/shell.js:136`) with no
comparison to the active room. `loadRoom` (`:145-151`) calls `showResults`,
whose first statement is `resetRoomView()` (`web/app.js:627`), which calls bare
`resetCheck()` (`:613`) → `clearCheck({keepScene:false})` →
`els.input.value = ""` (`web/scriptcheck.js:681`).

Clicking the room you are already in is the natural way back from Your card,
which has no back control. Doing it destroys pages of typed scene text. The loss
is unrecoverable: no storage touches `#scene`, and an in-page `.value = ""` with
no navigation is outside browser form restore.

**The guard that exists is disarmed, not late.** `setCheckRoom`'s
`if (runId === roomId) return` (`scriptcheck.js:653`) cannot match, because
`resetCheck` has already set `roomId = null` (`:667`).

**Build:**
- Thread room identity through the reset: `resetRoomView(runId)` →
  `resetCheck({ keepScene: runId === currentRoomId })`.
- `clearCheck`'s `keepScene` parameter already exists (`scriptcheck.js:672`,
  `:681`) but all three call sites pass `false`, so there is no live path to
  copy — this is the first real consumer.
- Give the account panel a back control that returns to the previous stage
  without re-entering `showResults`.

**Verify:** type into `#scene` without submitting, open Your card, click the
same room in the rail, assert the text survives. Then click a *different* room
and assert it is cleared — `app.js:610-612` documents that reset as the fix for
a cross-room leak that put room A's marked scene under room B's title, and that
behaviour must not regress.

---

## F-005 — A paid, failed build still says the department is working

**Severity 4, visibility 3.**

Nothing anywhere writes `#progress-panel`'s h2. The error branch
(`web/app.js:545-549`) is `endRun` + `addEntry` + re-enable, with no `stage()`
call, so the static string at `web/index.html:151` stands after a terminal
failure — under `.ellipsis::after`'s `pulse` animation (`web/shell.css:667-670`),
which is killed only by `prefers-reduced-motion`. Meanwhile `sweepUnfiledDrawers`
(`app.js:577-584`) renders the same "Did not file" message in every unfiled
drawer, so the screen reads as four identical failures under a live "working"
heading.

**Correction to the original finding — do not build this part.** The error line
is *not* off-screen. `addEntry` calls `scrollIntoView` on every appended entry
including the error one (`app.js:228`). The defect is a stale heading
contradicting a visible message, not a hidden message.

**Build:**
- On `ev.type === "error"`, rewrite the panel heading to name the failure and
  stop the ellipsis animation.
- Mount the failure message above the drawer grid rather than leaving it only in
  the timeline below it.
- Add a recovery control beside it that starts a new room **without** wiping the
  treatment textarea — the rail's "New room" sets `$("treatment").value = ""`
  (`app.js:133`), which is the only write to that field in the app.

**Do not** add an ETA, a retry-time estimate, or advice about treatment length
(invariant 9, and F-018's neighbour finding established the repo has no evidence
length drives duration).

**Verify:** force a terminal error and assert the heading changed, the ellipsis
stopped, and the treatment survived.

---

## F-013 — A token issued during a build is destroyed by the build finishing

**Severity 3, visibility 2.**

Issue an MCP token during the 146-420s wait, the build completes, `showResults`
switches the stage away, and returning via the rail runs `openAccount()` →
`replaceChildren` → `readCard()` which hardcodes `issued: null`
(`web/account.js:521`). Only a sha256 is stored (`star/tokens.py:159-169`), so
revoke-and-reissue is the only recovery.

**The skeptic made this cheaper in two ways — build the cheap version.**
- `stage()` only adds `.hidden` (`web/shell.js:189`), so the plaintext node
  **survives the stage switch intact**. The sole destroyer is `openAccount()`'s
  unconditional `replaceChildren` on re-entry (`account.js:473`).
- The plaintext **already lives in module scope** — `redraw` writes it to
  `card.issued` (`account.js:559-562`) and nothing clears it until the next
  `openAccount()`. Nothing needs storing.

**Build:** skip the re-read when a live plaintext exists, so re-entering the card
renders what is already held rather than discarding it. Requires an attached
Google account to reach at all (`account.js:393`), so this path is unreachable
for an anonymous session — scope tests accordingly.

**Verify:** issue a token, navigate away and back, assert the plaintext still
renders and was not re-issued.

---

## F-001 — A run in flight has no rail row, and closing it keeps spending

**Severity 4, visibility 4.** The highest-ranked finding in the register.

`web/app.js:411-416` runs `resetProgress/showRunning/startElapsedTimer/addEntry/
openStream` with **no `refreshRail`** — every `refreshRail` call sits at terminal
events, `init`, or `account.js:606`. So `web/shell.js:119-127`'s already-written
`isRunning` marker branch is never reached on the build path, and
`06-progress-running--default.png` shows the rail printing "Nothing filed yet"
beside four live SEARCHING drawers.

Pressing "New room" then calls `resetProgress()` → `closeStream()`
(`app.js:310-312`), and **the server does not care**: `stream_events`'
`generate()` (`star/server.py:895-915`) is a bare `while True` with no
`try/finally` and no `request.is_disconnected()`, and the pipeline is a separate
task pinned by a strong ref in `_runs[run_id]["task"]` (`:836`). Closing the SSE
response ends the generator only. The searches and Gemini calls keep running and
keep spending against a budget the live demo shares.

`showRunning()` has exactly two callers (`app.js:412`, `:1136`), neither of them
a control, so with no rail row there is no path back to a live build once you
open Your card.

**Correction — "orphans" overstates it.** The run is persisted at creation with
status `running` (`server.py:833`), so the room is filed and appears on the next
rail refresh. What is lost is the live view and any signal that money is still
being spent.

**Build:**
- Call `refreshRail(runId)` immediately after `POST /api/rooms` succeeds, so the
  running row exists and `shell.js`'s marker branch fires.
- Route that row's click to `showRunning()` when `run_id === liveRunId`, giving
  the live build a way back.
- Arm "New room" while a run is live using the **two-press pattern the app
  already ships** (`account.js:213`, `scriptcheck.js:598`): first press states
  the build keeps running and where to find it, second press proceeds.

**Known cosmetic consequence to handle:** `room_to_document` reads title and era
off an empty `story_profile` at creation (`star/store.py:62-63`), so the running
row will read "Untitled room · Era unstated" until the terminal write. Decide
whether the running row renders its own label instead, and say which you chose.

**Verify twice** — this is timing-dependent, and a single passing run of a race
is not verification.

---

## F-003 — Reload during a build drops the run, and the resume path already exists

**Severity 4, visibility 3.** Build last; it interacts with F-001's lifecycle.

Reload, crash, or a locked phone during a 146-420s build drops the only stream
key. Every piece of the machinery to fix this already ships, wired to exactly one
trigger:

- `stashLiveRun` (`web/auth.js:874-890`) writes via `writeStash` →
  `sessionStorage.setItem` (`:918-925`).
- `takeStashedRun` (`:897-908`) calls `removeStash` before it validates —
  delete-on-read.
- Its only call site is `auth.js:557`, inside `beginGoogleLink`.
- `openStream({resumed:true})` replays from event 0: EventSource cannot set
  Last-Event-ID on fresh construction, so `_resume_cursor(None, …)` returns 0
  (`star/server.py:271-293`) and `generate()` yields from `run["events"][0]`
  forward (`:895-913`), while the monotonic guard at `app.js:459-462` dedupes and
  `resetProgress` clears `lastEventId` first (`app.js:321`, called by
  `resumeStashedRun` at `:1135`).
- The server side holds: `run["events"]` is append-only, `_evict_old_runs` never
  touches a `running` entry (`server.py:593`), and `scripts/deploy.sh:72-73` pins
  `--max-instances=1 --min-instances=1` precisely so live runs keep instance
  affinity — the reconnect lands on the same warm process.

**Build:**
- Export `stashLiveRun` from `auth.js` (it is currently module-private; only
  `takeStashedRun` and `setLiveRunProvider` are exported) and call it from
  `openStream()` on every run, not only from `beginGoogleLink`.
- Add a companion **clear-on-terminal** export. `endRun` (`app.js:577-584`) nulls
  `liveRunId`/`liveStreamKey` but nothing removes the RUN_KEY stash, and an
  unstashed finished run would make the next reload open that room instead of
  the intake.
- Rewrite `resumeStashedRun`'s timeline line (`app.js:1141`, "Back from the
  sign-in. Picking the run up where it was.") — it is OAuth-specific and becomes
  false on a reload resume. Branch it or make it neutral.
- Give the `running` branch of `showResults` a "Check again" control re-issuing
  `GET /api/rooms/{id}`, polled while that panel is visible. **No ETA, no
  duration** (invariant 9).

**Honest limit to state in the code or the notes:** `sessionStorage` covers
reload and a same-tab lock, and usually survives crash session-restore. It does
not cover a closed tab or a new tab. This is best-effort on that third case, and
the copy must not imply otherwise.

**Verify twice.** Timing-dependent.

---

## What "done" means for this wave

1. All five items built, each committed separately in the repo's voice.
2. `python -m pytest -q` green, `ruff check star tests scripts harness` clean.
3. Behaviour changes carry a test in the repo's own framework — Python under
   `tests/`, browser modules as `.mjs` under `tests/js/` (globbed and asserted
   non-empty by `tests/test_js_auth.py`).
4. No new dependency, no build step, no CDN reference.
5. Nothing outside the five findings changed. Discoveries go to the register.
