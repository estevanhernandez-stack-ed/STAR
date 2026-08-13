/* STAR frontend — build a room, watch it happen, open the drawers.

   The stage's state (intake / running / room) and the rail of saved rooms
   belong to shell.js. This file owns starting a build, streaming its
   progress, and painting a room's content once it's open.

   Both views are now the same four drawers (web/drawer.js). A live run
   drives them through idle -> searching -> filed off the SSE stream; a
   filed room mounts a second grid from GET /api/rooms/{id} and each card
   opens into its clips (web/clip.js). That is deliberate and it is the
   point of the phase: a room reached from the rail and a room that just
   finished building are the same object in the same component, so nothing
   can look different depending on how you got there.

   What this file stopped doing in Task 6: the three-button tab strip over
   Research Bible / Story Profile / Research Plan. The bible moved behind
   the docket's own button (docs/design/DIRECTION.md — "findings lead, the
   bible follows"); the profile moved onto the docket; the research plan is
   not gone but distributed — every question it holds carries a category,
   and web/clip.js's renderSceneNeeds files each one into the drawer it was
   written for, under the scene it was asked for. A plan read as one flat
   list behind two clicks was the single most-buried thing we produce.

   Research obligation 6 (never promise a duration) governs everything in
   the SSE handler below: no ETA, no progress bar implying completion.
   Elapsed time is shown because it is a fact about the past, not a claim
   about the future — see elapsedLabel().
*/

import {
  authedFetch,
  clearStashedRun,
  completeGoogleLink,
  getIdToken,
  setLiveRunProvider,
  stashLiveRun,
  takeStashedRun,
} from "/auth.js";
import {
  showAccount,
  showIntake,
  showRunning,
  showRoom,
  refreshRail,
  setLiveRun,
  setRoomRenderer,
  knownRooms,
} from "/shell.js";
import { initAccount, openAccount } from "/account.js";
// Served by star/server.py from config.max_room_title_chars(), not typed here.
// A cap duplicated in JS to match one defined in Python is two sources of
// truth, and only one of them ever moves.
import { LIMITS } from "/config.js";
import {
  DRAWER_LABELS,
  createDrawerGrid,
  setDrawerState,
  tickDrawerClocks,
} from "/drawer.js";
// The stamp's own formatters, from the module that prints the stamp. See the
// note above roomDate for why they moved out of this file.
import { isoStamp, stampDate } from "/clip.js";
import {
  initScriptCheck,
  openedCheck,
  resetCheck,
  setCheckRoom,
} from "/scriptcheck.js";

const $ = (id) => document.getElementById(id);

const timeline = $("timeline");
const progressPanel = $("progress-panel");

// The room view's fixed furniture. index.html ships all four and this file
// only ever replaces their CONTENTS, never the nodes themselves, so a
// reference taken once at module load cannot go stale.
const roomGrid = $("room-grid");
const bibleSurface = $("bible-surface");
const bibleBtn = $("bible-btn");
const checkSurface = $("check-panel");
const checkBtn = $("check-btn");
const docketBody = $("docket-body");

let searchCount = 0;

// Fallback only, and no longer the primary path. SSE "agent_done" once
// carried nothing but the friendly label star/server.py's _FRIENDLY assigns
// each author, so the client reverse-mapped display prose back to a routing
// key — which made _FRIENDLY's exact wording a load-bearing API contract with
// no test guarding it. The server sends `category` now (the same way "search"
// always has) and the handler below prefers it; this map survives for an
// event from an older server and nothing else. This comment stated the old
// behaviour as current until Task 6; the code stopped agreeing with it at
// star/server.py's ba4e3fe.
const AGENT_TO_CATEGORY = {
  "Setting researcher": "setting",
  "Props researcher": "objects_props",
  "Logistics researcher": "logistics",
  "Forces & conflicts researcher": "forces_conflicts",
};

// The three-letter researcher code the stamp carries (DIRECTION.md's
// "researcher's code", visual-directions.md's "lifted straight from
// found_by") — one clean abbreviation per drawer plate.
const CATEGORY_CODE = {
  setting: "SET",
  objects_props: "OBJ",
  logistics: "LOG",
  forces_conflicts: "FOR",
};

// Live-run tracking. Rebuilt fresh at the top of every buildRoom() call by
// resetProgress() — nothing here is meant to survive across two builds in
// the same session.
let drawerEls = new Map(); // category -> drawer element
let categorySearch = new Map(); // category -> { objective, count }
let filedCategories = new Set();
let elapsedTimer = null;
// null means "this page does not know when the run started" — see updateMeter.
let runStartedAt = null;

// The run this page is currently streaming, and how far into its event history
// it has got. auth.js reads all three through the provider registered at the
// foot of this file — beginGoogleLink on the way out to Google, and
// stashLiveRun on every run since wave 1 — because these three values are the
// only thing about a live run that is not recoverable from the server
// afterwards, and a page that goes away for any reason loses them.
let liveRunId = null;
let liveStreamKey = null;
let lastEventId = null;
// The one open stream, held so it can be closed. "New room" during a build
// used to leave the previous EventSource connected: it went on writing into
// drawer elements resetProgress had already replaced, and it would eventually
// yank the reader into the old room when that run finished. Harmless enough to
// live with until the monotonic id guard below arrived — two live streams
// sharing one lastEventId means the older one suppresses the newer one's
// events — so the stream is now closed where the state it drives is cleared.
let activeSource = null;

$("build-btn").addEventListener("click", buildRoom);

/** The banner's own sentence, moved out of index.html so that revealing it is a
 *  content change rather than a class change. Unchanged wording. */
const AUTH_UNREACHABLE =
  "Could not start a session with the department. Check your connection and reload.";

/** Show or hide #auth-error, writing and clearing its text rather than only
 *  toggling .hidden.
 *
 *  Clearing on hide is the load-bearing half: leave the sentence in place and
 *  the next reveal writes the same words over themselves, which is a mutation
 *  a screen reader may treat as nothing new. Empty-to-text is unambiguous. */
function showAuthError(show) {
  const banner = $("auth-error");
  // No-argument replaceChildren, not replaceChildren(""), which would append an
  // empty text node and leave the element non-empty to CSS and to the tree.
  if (show) banner.replaceChildren(document.createTextNode(AUTH_UNREACHABLE));
  else banner.replaceChildren();
  banner.classList.toggle("hidden", !show);
}

/* The first press's sentence, when a run is live.
   It says what continues and where to find it, and it does not say when the
   run will finish: star/config.py records 146s to 420s+ for one fixed
   treatment, so there is no number here that would not be a guess. */
const NEW_ROOM_ARMED = "Start a new one anyway";
const NEW_ROOM_NOTICE =
  "The build already running keeps going, and keeps spending searches. It is " +
  "in the rail under its own row, and it files there when it is done.";

/** Put the control back to its resting state. Called on the second press and
 *  whenever a run ends, so a build that finishes while the button is armed
 *  does not leave a warning about a run that is already filed. */
function disarmNewRoom() {
  const btn = $("new-room-btn");
  btn.setAttribute("data-armed", "false");
  btn.replaceChildren(document.createTextNode("New room"));
  $("new-room-notice").replaceChildren();
}

/* Armed only while a run is live, and the reason is money rather than tidiness.
   resetProgress() calls closeStream(), and closing the SSE response ends the
   GENERATOR only: star/server.py's stream_events is a bare `while True` with no
   disconnect check, and the pipeline is a separate task held by a strong ref in
   _runs[run_id]. The searches and the Gemini calls carry on, against a budget
   the live demo shares, with nothing on screen still pointed at them.

   Two presses, using the idiom web/account.js and web/scriptcheck.js already
   ship for their irreversible controls rather than inventing a third. With no
   run live the control behaves exactly as it did — one press, straight through
   — because there is nothing to warn about. */
$("new-room-btn").addEventListener("click", () => {
  const btn = $("new-room-btn");
  if (liveRunId !== null && btn.getAttribute("data-armed") !== "true") {
    btn.setAttribute("data-armed", "true");
    btn.replaceChildren(document.createTextNode(NEW_ROOM_ARMED));
    $("new-room-notice").replaceChildren(document.createTextNode(NEW_ROOM_NOTICE));
    return;
  }
  disarmNewRoom();
  showIntake();
  resetProgress();
  $("treatment").value = "";
  $("intake-error").textContent = "";
  $("build-btn").disabled = false;
});

// The card. Bound here rather than in shell.js for the same reason
// #new-room-btn is: shell.js owns which panel the stage shows, this file owns
// what goes in one.
//
// NOTHING ELSE HAPPENS HERE, and that is the acceptance criterion. No
// resetProgress(), no closeStream(), no showResults() — reaching the card
// during a live build must not disturb the stream, and the way that is
// guaranteed is that the only thing this listener does is reveal a panel and
// fill it. The EventSource opened by openStream() is untouched, goes on
// writing into #progress-panel's hidden DOM, and is exactly as far along when
// the reader comes back.
$("rail-foot").addEventListener("click", () => {
  showAccount();
  openAccount();
});

// The bible is one surface behind one control, and opening it puts the
// drawers away rather than stacking under them: it is a second VIEW of the
// room, not a section of the first. The button carries aria-expanded and
// aria-controls so the state is announced, and its label changes too —
// belt and braces, because a control whose only feedback is an ARIA
// attribute is a control most people cannot see change.
//
// Replaces the three-button `.tab` strip this file used to wire with a
// querySelectorAll snapshot taken once at module evaluation. That listener
// is gone with the markup it was attached to; nothing else in the app
// declares `.tab` (the drawer's cut tab is `.drawer-tab`, renamed in Task 5
// after these two collided — see web/drawer.css).
bibleBtn.addEventListener("click", () => {
  setRoomMode(roomMode === "bible" ? "drawers" : "bible");
});

// The Script Check is the room's third view, reached the same way and from
// the same head. Not a separate place, and not a separate stage state: what
// makes a check worth anything is that it runs against THIS room, and a
// surface you have to navigate away to reach says the opposite
// (spec.md > The marked scene > Where it lives).
checkBtn.addEventListener("click", () => {
  setRoomMode(roomMode === "check" ? "drawers" : "check");
});

// The room a delete would remove. showResults sets it; nothing else does, so
// the control can never be pointed at a room the reader is not looking at.
let openRoomId = null;

/* Two presses, and the first one only warns.
 *
 * The same arming web/scriptcheck.js's buildFoot uses for a check, and for the
 * same argument it makes there: a room costs real money and several minutes,
 * one stray click should not be able to spend that again, and the warning
 * belongs on the page in the department's voice rather than behind a browser
 * dialog nobody reads.
 *
 * It says the room is recoverable, because it is — unlike the check delete one
 * file over, which says the opposite and means it. */
function disarmRoomDelete() {
  const btn = $("room-delete-btn");
  if (!btn) return;
  btn.setAttribute("data-armed", "false");
  btn.replaceChildren(document.createTextNode("Delete this room"));
  const note = $("room-delete-note");
  if (note) note.replaceChildren();
}

const roomDeleteBtn = $("room-delete-btn");
if (roomDeleteBtn) {
  roomDeleteBtn.addEventListener("click", async () => {
    if (!openRoomId) return;
    const note = $("room-delete-note");
    if (roomDeleteBtn.getAttribute("data-armed") !== "true") {
      roomDeleteBtn.setAttribute("data-armed", "true");
      roomDeleteBtn.replaceChildren(document.createTextNode("Delete it"));
      note.replaceChildren(
        document.createTextNode(
          "This takes the room out of your rail along with every check filed " +
            "against it. It stays in Deleted, at the foot of the rail, where " +
            "you can put it back — after that it is destroyed for good."
        )
      );
      return;
    }
    roomDeleteBtn.disabled = true;
    try {
      await authedFetch(`/api/rooms/${encodeURIComponent(openRoomId)}`, {
        method: "DELETE",
      });
    } finally {
      roomDeleteBtn.disabled = false;
      disarmRoomDelete();
      showIntake();
      await refreshRail(null);
    }
  });
}

/* What the room is called, and what it belongs to.
 *
 * "Untitled room" used to be a permanent fate: star/store.py wrote it and no
 * rename path existed anywhere, so a build whose intake found no title
 * produced a room that could never be called anything else. The judge's
 * round-two review filed that under room hygiene — three Untitled rooms and an
 * errored husk, with no way to clean any of it up.
 *
 * One panel for both edits because they are one act. It ships closed: a room
 * already named right should not be carrying an open form about naming. */
function closeRoomEdit() {
  const panel = $("room-edit");
  if (!panel) return;
  panel.classList.add("hidden");
  $("room-edit-btn").setAttribute("aria-expanded", "false");
  $("room-edit-note").replaceChildren();
}

/** Fills the panel from the room the reader is looking at.
 *
 *  The parent list comes from the rail's own rooms rather than a second fetch,
 *  and it excludes this room — a room cannot follow itself, and the server
 *  refuses it by name, but a control that offers an option the server will
 *  reject is a control that invites the refusal. */
function fillRoomEdit(result) {
  const input = $("room-title-input");
  const select = $("room-parent-select");
  if (!input || !select) return;

  // The rail's title, not the story profile's: after a rename those differ,
  // and the field has to open on the name the room actually carries.
  const listed = knownRooms().find((room) => room.run_id === openRoomId);
  input.value = listed ? listed.title || "" : (result.story_profile || {}).title || "";
  input.maxLength = LIMITS.roomTitleChars;

  const current = result.continues || "";
  select.replaceChildren();
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "Nothing — this room starts a story";
  select.appendChild(none);

  let currentIsListed = false;
  for (const room of knownRooms()) {
    if (room.run_id === openRoomId) continue;
    const option = document.createElement("option");
    option.value = room.run_id;
    option.textContent = room.era
      ? `${room.title || "Untitled room"} · ${room.era}`
      : room.title || "Untitled room";
    select.appendChild(option);
    if (room.run_id === current) currentIsListed = true;
  }

  // A parent that is no longer in the rail — deleted, or purged after its
  // window closed. Said rather than silently reset to "nothing", because
  // dropping a link a writer drew, without telling them, is the app editing
  // their work on their behalf.
  if (current && !currentIsListed) {
    const gone = document.createElement("option");
    gone.value = current;
    gone.textContent = "A room that is no longer filed";
    select.appendChild(gone);
  }
  select.value = current;
}

const roomEditBtn = $("room-edit-btn");
if (roomEditBtn) {
  roomEditBtn.addEventListener("click", () => {
    const panel = $("room-edit");
    const opening = panel.classList.contains("hidden");
    panel.classList.toggle("hidden", !opening);
    roomEditBtn.setAttribute("aria-expanded", opening ? "true" : "false");
    if (opening) $("room-title-input").focus();
    else $("room-edit-note").replaceChildren();
  });
}

const roomEditSave = $("room-edit-save");
if (roomEditSave) {
  roomEditSave.addEventListener("click", async () => {
    if (!openRoomId) return;
    const note = $("room-edit-note");
    roomEditSave.disabled = true;
    note.replaceChildren();
    try {
      const response = await authedFetch(
        `/api/rooms/${encodeURIComponent(openRoomId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: $("room-title-input").value,
            continues: $("room-parent-select").value,
          }),
        }
      );
      if (!response.ok) {
        // The server's own sentence. Every refusal here names what failed and
        // what to do next, and replacing them with "Could not save" would
        // throw away the only part a reader can act on.
        let detail = "That did not save.";
        try {
          detail = (await response.json()).detail || detail;
        } catch {
          /* body wasn't JSON; keep the fallback */
        }
        note.replaceChildren(document.createTextNode(detail));
        return;
      }
      // What the room now carries, not what was typed: an empty name restores
      // the one the department gave it, and printing the typed value would
      // leave the heading disagreeing with the rail.
      const saved = await response.json();
      $("result-title").textContent = saved.title || "Your research room";
      $("room-title-input").value = saved.title || "";
      closeRoomEdit();
      await refreshRail(openRoomId);
    } finally {
      roomEditSave.disabled = false;
    }
  });
}

// One variable, three views, and exactly one visible at a time. It replaces
// the boolean setBibleOpen carried, which could only ever describe two: with
// a third surface a boolean becomes two booleans that have to be kept from
// both being true, and "both are open" is a state nothing in the layout can
// render.
let roomMode = "drawers";

function setRoomMode(mode) {
  roomMode = mode;
  roomGrid.classList.toggle("hidden", mode !== "drawers");
  bibleSurface.classList.toggle("hidden", mode !== "bible");
  checkSurface.classList.toggle("hidden", mode !== "check");

  // Both controls carry aria-expanded AND change their own label — belt and
  // braces, because a control whose only feedback is an ARIA attribute is a
  // control most people cannot see change.
  bibleBtn.setAttribute("aria-expanded", mode === "bible" ? "true" : "false");
  bibleBtn.textContent = mode === "bible" ? "Back to the drawers" : "The bible";
  checkBtn.setAttribute("aria-expanded", mode === "check" ? "true" : "false");
  checkBtn.textContent = mode === "check" ? "Back to the drawers" : "Check a scene";

  // The list of checks already filed on this room costs a request, so it is
  // fetched when the mode is opened rather than on every room paint. A reader
  // who never opens it never pays for it.
  if (mode === "check") openedCheck();
}

/** The activity feed's own reduced-motion path.
 *
 *  A smooth scroll is motion, and this one fires on every agent that finishes
 *  during a build — the CSS token every other component routes its motion
 *  through (--stamp-duration, web/tokens.css) cannot reach a scroll behaviour
 *  passed from JS, so this was the one piece of movement in the app with no
 *  reduced-motion path at all. Read at call time rather than cached at module
 *  load: the setting can change mid-session, and this costs nothing.
 *
 *  "auto" is the instant jump, not the browser default — the element still
 *  comes into view, it just gets there without travelling. */
function scrollBehavior() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ? "auto"
    : "smooth";
}

/** Append one line to the run's log.
 *
 *  #timeline carries aria-live="polite", so every call here is also an
 *  announcement. One honest limit, recorded at the point it applies rather
 *  than in a doc nobody opens: the FIRST entry of a build is appended in the
 *  same synchronous task that showRunning() un-hides the panel, and some
 *  assistive tech drops an insertion into a region that was not in the
 *  accessibility tree when the task began. Every later entry is unaffected.
 *  Not worked around with a timeout — a deferred first line would be a
 *  guess about AT behaviour dressed as a fix, and the run's own second
 *  event follows within seconds. */
function addEntry(cls, html) {
  const li = document.createElement("li");
  li.className = cls;
  li.innerHTML = html;
  timeline.appendChild(li);
  li.scrollIntoView({ behavior: scrollBehavior(), block: "nearest" });
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/*  stampDate — DD MON YYYY, matching the stamp's slug-face convention in
 *  docs/design/visual-directions.md's own mockup ("RET 09 AUG 2026") — now
 *  lives in web/clip.js, which is the module that prints the stamp. A finding
 *  requisitioned into a room after it was built carries a retrieval date of
 *  its own, and clip.js needs this format to render it; reaching upward from
 *  clip.js to here would invert the import graph (app -> drawer -> clip), and
 *  a second copy of two lines of formatting is how a drawer's date and a
 *  finding's date come to disagree about what a date looks like.
 *
 *  Still called here with no argument during a live run, where the retrieval
 *  genuinely just happened, so client "now" and server "now" differ by network
 *  latency only and not by anything worth reconciling. */

/** The room's own date, in the stamp's face — or nothing.
 *
 *  `created_at` is the room document's ISO timestamp (star/store.py), which is
 *  when the run happened and therefore when its searches ran. That is what the
 *  receipt stamps as `RET`, and the reason it has to come from the payload
 *  rather than from this browser's clock: a room built on 09 AUG and opened in
 *  September would otherwise stamp September on sources that came back in
 *  August — a fabricated provenance claim on the one element whose entire job
 *  is provenance. web/drawer.js's renderExpanded refuses to substitute the
 *  filed date for this exact reason; this is the value it was waiting for.
 *
 *  Missing or unparseable returns "", and every caller drops the line rather
 *  than filling it. A document written before the field existed is the real
 *  case; a malformed one is the defensive case. Neither is worth a guess. */
const roomDate = isoStamp;

/** Elapsed time only — never a prediction. Research obligation 6 forbids an
 *  ETA or a progress bar implying completion; it says nothing against
 *  stating how long the department has been at it, which is a fact about
 *  the past, not a promise about the future. star/config.py's own recorded
 *  range (146s-420s+) is exactly why no single number belongs here as an
 *  estimate — this clock only ever counts up from what already happened. */
function elapsedLabel() {
  const secs = Math.max(0, Math.floor((Date.now() - runStartedAt) / 1000));
  return `${Math.floor(secs / 60)}:${pad2(secs % 60)} elapsed`;
}

/** The meter, and the one clause it drops rather than guesses.
 *
 *  A run resumed after a page load has no start time this browser can see:
 *  GET /api/rooms/{id} returns `result: null` while the pipeline is still
 *  running, so `created_at` is not on the wire for exactly the case that needs
 *  it. Stamping Date.now() there would print "0:04 elapsed" over a build that
 *  has been going four minutes, which is the same defect as a drawer explaining
 *  a cause it cannot see. The search tally is a fact either way and stays. */
function updateMeter() {
  // "searches", not "cited searches". star/server.py:470 increments
  // run["search_count"] inside the block reading `call.args` — the tool CALL,
  // before any response exists — so this counts searches ISSUED. Whether one
  // came back, and whether anything it returned was cited, are facts this
  // number cannot carry. web/drawer.js:187 already says "issued" for the same
  // reason, in its own words: "'Issued' is what the event proves and it costs
  // nothing."
  const parts = [`${searchCount} searches so far`];
  if (runStartedAt !== null) parts.push(elapsedLabel());
  $("search-meter").textContent = parts.join(" · ");
  // One interval drives both clocks, so a drawer's "last search N ago" can
  // never disagree with the run meter beside it, and both stop the moment
  // the run does.
  tickDrawerClocks(progressPanel);
}

function startElapsedTimer({ startedAt = Date.now() } = {}) {
  runStartedAt = startedAt;
  updateMeter();
  elapsedTimer = setInterval(updateMeter, 1000);
}

function stopElapsedTimer() {
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = null;
}

/** Rebuilds the live drawer grid and clears every piece of per-run state.
 *  Called at the top of every build, and again on "New room" — the error path
 *  below still never navigates away on its own, so a stray interval or a stale
 *  drawer reference must not survive into whatever the user does next.
 *
 *  There are TWO recovery paths now, not one. The rail's "New room" is still
 *  always visible, and it still clears the treatment because "start fresh" is
 *  what it means. markRunFailed mounts a second one inside the failure block,
 *  which does everything this one does except the wipe — a reader whose build
 *  just failed should not have to go and find their treatment again. This
 *  comment named the rail button as "the" recovery path until wave 1 of the
 *  glow campaign, and that was the sentence that made the wipe look harmless. */
function resetProgress() {
  stopElapsedTimer();
  closeStream();
  // Let go of the run, not just of the panel.
  //
  // closeStream() ends this page's view of a run; these two end the rest of the
  // app's memory of it. They were in endRun() alone, and the abandon path never
  // reaches endRun — pressing "New room" twice during a build lands here and
  // nowhere else. That left shell.js's _liveRunId pointing at the run the
  // reader had just walked away from, so its rail row routed to showRunning()
  // and opened the panel this function had emptied one line earlier: "The
  // department is working", a fresh ellipsis, four idle drawers, no stream —
  // for a run that was genuinely still spending. The armed control's own notice
  // sends the reader there by name.
  //
  // Safe at the other two call sites: buildRoom clears here and openStream sets
  // both again a few lines later, and resumeStashedRun runs after
  // takeStashedRun has already deleted the stash on read.
  setLiveRun(null);
  clearStashedRun();
  // The heading and the failure block are panel state, so they reset with the
  // panel. Without this the next build would start under "The department
  // stopped" with the previous run's reason still pinned above the drawers.
  const heading = $("progress-heading");
  heading.replaceChildren(document.createTextNode(WORKING_HEADING));
  const dots = document.createElement("span");
  dots.className = "ellipsis";
  heading.appendChild(dots);
  const failure = $("progress-failure");
  failure.replaceChildren();
  failure.classList.add("hidden");
  timeline.innerHTML = "";
  $("search-meter").textContent = "";
  searchCount = 0;
  filedCategories = new Set();
  categorySearch = new Map();
  runStartedAt = null;
  liveRunId = null;
  liveStreamKey = null;
  lastEventId = null;
  const grid = createDrawerGrid();
  drawerEls = new Map([...grid.children].map((el) => [el.dataset.category, el]));
  const oldGrid = progressPanel.querySelector(".drawer-grid");
  if (oldGrid) {
    oldGrid.replaceWith(grid);
  } else {
    progressPanel.insertBefore(grid, timeline);
  }
}

/* The progress panel's two headings, kept together so the pair can be read in
   one place. The working one is duplicated in web/index.html because it is the
   panel's resting state and has to be in the markup; this constant is what
   restores it. */
const WORKING_HEADING = "The department is working";
const FAILED_HEADING = "The department stopped";
const START_OVER = "Start a new room";

/** The panel's terminal-failure state.
 *
 *  Two things, and the first was missing entirely: nothing in this app wrote
 *  #progress-heading, so a run that failed went on claiming the department was
 *  working, under a pulsing ellipsis, while sweepUnfiledDrawers filled all four
 *  cards with "Did not file". The screen contradicted itself, and after a build
 *  that spent real search budget the contradiction was the loudest thing on it.
 *
 *  The reason then goes ABOVE the drawer grid. It is in the timeline below as
 *  well — that is the run's chronological record and it keeps it — but the
 *  timeline sits under four cards at their 260px floor, and this is the surface
 *  a reader is looking at when they find out they paid for nothing.
 *
 *  No ETA, no retry-time, no advice about treatment length. star/config.py
 *  records 146s to 420s+ for ONE FIXED treatment, so length is not the measured
 *  variable and guidance about it would be a guess printed as help. */
function markRunFailed(message) {
  const heading = $("progress-heading");
  // replaceChildren, not textContent: it takes the .ellipsis span with it, and
  // the pulse is the half of this that a reader sees from across the room.
  heading.replaceChildren(document.createTextNode(FAILED_HEADING));

  const box = $("progress-failure");
  box.replaceChildren();

  const line = document.createElement("p");
  line.className = "progress-failure-line";
  // textContent rather than the escapeHtml-into-innerHTML the timeline uses.
  // Same result for these two server strings, stricter by construction.
  line.textContent = message;
  box.appendChild(line);

  // What it cost, in the same box as the failure.
  //
  // A failed build has already spent live searches and one of the department's
  // daily builds, and neither comes back — correctly, because the money went.
  // What was wrong was charging silently: a reader who presses Start a new room
  // three times has spent three days' slots learning that, and the control to
  // do it is directly below this line.
  if (searchCount > 0) {
    const spent = document.createElement("p");
    spent.className = "progress-failure-spent";
    spent.textContent =
      `It spent ${searchCount} live search${searchCount === 1 ? "" : "es"} ` +
      "before it stopped. Those are not refunded, and it used one of the " +
      "department's daily builds. Trying again costs the same.";
    box.appendChild(spent);
  }

  const again = document.createElement("button");
  again.type = "button";
  again.className = "progress-failure-btn";
  again.textContent = START_OVER;
  again.addEventListener("click", () => {
    // What the rail's "New room" does, minus the one line that made it a poor
    // recovery path from here: it clears #treatment, and that is the only write
    // to the field in this app. A reader whose build just failed should not
    // have to go and find their treatment again to try it.
    showIntake();
    resetProgress();
    $("intake-error").textContent = "";
    $("build-btn").disabled = false;
  });
  box.appendChild(again);

  box.classList.remove("hidden");
}

/** Marks every drawer that never reached "filed" by the time the run ended
 *  — a terminal error, an editor that ran out of time (partial), or
 *  (defensively) "complete" itself, in case a researcher produced no final
 *  response for some reason unrelated to the timeout or the editor. A
 *  drawer left "searching" forever after the run is already over is worse
 *  than an honest "did not file" — see web/drawer.js's FAILED state. */
function sweepUnfiledDrawers() {
  for (const [category, el] of drawerEls) {
    if (!filedCategories.has(category)) {
      setDrawerState(el, "failed");
    }
  }
}

async function buildRoom() {
  const treatment = $("treatment").value.trim();
  $("intake-error").textContent = "";
  $("build-btn").disabled = true;

  // Firebase Auth is a hard dependency: with no token, POST /api/rooms is a
  // 401 by construction. Check before spending a doomed round trip, and say
  // why rather than surfacing the generic error that request would produce.
  // getIdToken()'s own contract is that it never throws, but belt-and-
  // braces here too: a stuck disabled button with no message would be worse
  // than treating an unexpected throw the same as a null.
  let token;
  try {
    token = await getIdToken();
  } catch {
    token = null;
  }
  if (!token) {
    showAuthError(true);
    // Re-enable, THEN focus. Disabling the button the reader pressed dropped
    // focus to <body>, and re-enabling does not hand it back — measured in
    // Chromium: focus build-btn, disable, activeElement is BODY, re-enable,
    // still BODY. focus() on a disabled element is a no-op, so the order here
    // is load-bearing rather than stylistic.
    $("build-btn").disabled = false;
    $("build-btn").focus();
    return;
  }
  showAuthError(false);

  let runId;
  let streamKey;
  try {
    const res = await authedFetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ treatment }),
    });
    // Guarded the way showResults already guards its own error path. An
    // unguarded res.json() here surfaced the PARSE failure instead of the
    // request failure: a Cloud Run 429 or 503 with an HTML body, or anything
    // that did not come from FastAPI, put `Unexpected token '<', "<html>"...
    // is not valid JSON` on the first screen as the department's own message.
    // The success path below is the same exposure and takes the same guard.
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail || detail;
      } catch {
        /* body wasn't JSON; fall back to statusText */
      }
      throw new Error(detail);
    }
    // `stream_key` is the capability for this run's event stream, minted
    // server-side and handed back exactly once, here. It is the only way the
    // progress stream can identify its caller: EventSource sends no custom
    // headers, so the Authorization header every other request carries is
    // unavailable to it. See star/server.py's stream_events.
    let body;
    try {
      body = await res.json();
    } catch {
      throw new Error("The department answered, but not in a shape this page understands.");
    }
    ({ run_id: runId, stream_key: streamKey } = body);
  } catch (err) {
    $("intake-error").textContent = err.message;
    $("build-btn").disabled = false;
    // The other exit, and the same reason. F-010 gave this error span
    // role="alert" so it announces wherever focus sits; an alert still does not
    // give a keyboard reader anywhere to stand, and without this they tab from
    // the top of the document.
    $("build-btn").focus();
    return;
  }

  resetProgress();
  showRunning();
  startElapsedTimer();
  addEntry("done", "Treatment received. The department is assembling.");
  openStream(runId, streamKey);
  // The run exists server-side the moment this POST returns — star/server.py
  // persists it with status "running" at creation — but nothing asked the rail
  // to redraw until the run ENDED. So web/shell.js's running-marker branch was
  // unreachable on this path, and a live build showed "Nothing filed yet" in
  // the rail beside four drawers actively searching.
  //
  // Deliberately after openStream, and not awaited: the stream is what the
  // reader is waiting on, and it must not queue behind a list fetch.
  refreshRail(runId);
}

/** Opens one run's event stream and drives the progress panel off it.
 *
 *  Two callers, one handler, deliberately: a build started in this page and a
 *  build picked back up after a redirect are the same run, and a second copy of
 *  this logic is a second place for the two to drift apart.
 *
 *  `resumed` changes exactly one thing, and it is the error path. A run that
 *  has left the server's in-memory registry answers this endpoint with a 404,
 *  and EventSource's response to a failed connection is to keep retrying
 *  forever. On the build path that cannot happen — the run was created
 *  milliseconds ago. On the resume path it is the ordinary case for a run that
 *  finished while the reader was away, so a failure that arrives before any
 *  event does closes the stream and opens the filed room instead.
 *
 *  ON DUPLICATE ENTRIES, which is what this has to guarantee. Every event
 *  carries its index in the run's append-only history (star/server.py's _push),
 *  and this handler refuses any id it has already applied. That makes a
 *  duplicated timeline entry structurally impossible rather than merely
 *  unobserved — including when EventSource reconnects on its own and the server
 *  replays from a cursor this page has already passed. */
function openStream(runId, streamKey, { resumed = false } = {}) {
  closeStream();
  liveRunId = runId;
  // The rail's own copy, so a row for this run knows to go to the live surface
  // rather than fetching a room that has no story_profile yet.
  setLiveRun(runId);
  liveStreamKey = streamKey;
  // Stash the run for a page that does not survive it. Here rather than only
  // at the OAuth redirect, because the stream_key is lost the same way by a
  // reload, a crash, and a phone locking — and it is the one value about a
  // live run that no endpoint will reissue. Placed after both fields are set,
  // since auth.js reads them back through the provider registered at the foot
  // of this file.
  stashLiveRun();

  // encodeURIComponent on both: runId and streamKey are server-minted hex
  // today, so neither can carry a character that needs escaping — which is
  // exactly the kind of assumption that stops being true quietly. Encoding
  // costs nothing and does not depend on the server's id format staying hex.
  // EventSource re-sends this whole URL on every automatic reconnect, so the
  // key travels with the Last-Event-ID resume for free.
  const source = new EventSource(
    `/api/rooms/${encodeURIComponent(runId)}/events?k=${encodeURIComponent(streamKey)}`,
  );
  let received = false;

  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    received = true;
    // The monotonic guard. `id` is the event's position in the run's history,
    // so "already applied" is an integer comparison and not a heuristic.
    if (Number.isInteger(ev.id)) {
      if (lastEventId !== null && ev.id <= lastEventId) return;
      lastEventId = ev.id;
    }
    if (ev.type === "search") {
      searchCount += 1;
      const category = ev.category;
      if (category && drawerEls.has(category)) {
        // Accumulate rather than replace: the searching drawer now shows the
        // whole run of objectives this researcher has issued, not just the
        // latest one, plus the literal queries of the call in flight. See
        // web/drawer.js's renderSearching for why the previous dot row was
        // replaced. `count` stays a separate integer because the filed stamp
        // reads it after the searches array has served its purpose.
        const s = categorySearch.get(category) || { searches: [], count: 0 };
        s.count += 1;
        s.searches.push({
          objective: ev.objective || "",
          queries: Array.isArray(ev.queries) ? ev.queries : [],
          // Client arrival time, not a server timestamp. The drawer only
          // ever renders this as an age relative to the same clock, so the
          // two never have to agree — and an SSE event's arrival is when
          // the viewer actually learned of the search, which is what the
          // line on screen claims.
          at: Date.now(),
        });
        categorySearch.set(category, s);
        // A category that already filed must never visually un-stamp back
        // to "searching" — found by testing a stray/duplicate "search"
        // arriving after that category's agent_done. Whether the real
        // pipeline can ever produce that ordering is unverified either way,
        // so this guards it rather than assuming it can't happen. The tally
        // above still updates either way — a search that genuinely
        // happened is still true even if the drawer no longer visualizes
        // per-search progress.
        if (!filedCategories.has(category)) {
          setDrawerState(drawerEls.get(category), "searching", {
            searches: s.searches,
          });
        }
      }
      updateMeter();
    } else if (ev.type === "agent_done") {
      // The server now sends `category` on agent_done, the same way it
      // always has on search. Prefer it. AGENT_TO_CATEGORY stays only as a
      // fallback for an event from an older server, and is no longer the
      // primary path — reverse-mapping display prose back to a routing key
      // made _FRIENDLY's exact wording an API contract nobody was guarding.
      const category = ev.category ?? AGENT_TO_CATEGORY[ev.agent];
      if (category && drawerEls.has(category)) {
        // Defends against a researcher whose turn produces more than one
        // "final" text part in one run (an ADK behavior this file cannot
        // rule out) filing — and re-animating — the same drawer twice.
        if (!filedCategories.has(category)) {
          filedCategories.add(category);
          const s = categorySearch.get(category) || { count: 0, searches: [] };
          setDrawerState(drawerEls.get(category), "filed", {
            code: CATEGORY_CODE[category],
            date: stampDate(),
            searchCount: s.count,
            searches: s.searches,
          });
        }
      } else {
        // Intake, planning, and synthesis have no drawer — they still get
        // a line in the activity feed so the run doesn't read as silent
        // during the fan-out and the fan-in.
        addEntry("done", `<span class="who">${escapeHtml(ev.agent)}</span> filed their work.`);
      }
    } else if (ev.type === "warning") {
      // The empty-ledger signal (star/server.py's _maybe_warn_empty_ledger)
      // — run-wide, not per-category, so it goes to the activity feed
      // rather than any one drawer.
      addEntry("warn", escapeHtml(ev.message));
    } else if (ev.type === "complete") {
      endRun(source);
      // The one terminal branch that announced nothing. `partial` and `error`
      // both already call addEntry, so #timeline's live region speaks them;
      // this one went straight to showResults, and a screen-reader user who
      // had been told the department was assembling was never told it had
      // finished. Appended before the stage switches, so the region is still
      // the visible panel's when it speaks.
      addEntry("done", "The room is filed.");
      showResults(runId);
      refreshRail(runId);
    } else if (ev.type === "partial") {
      // The editor ran out of time, but the researchers did not. Their
      // findings and citations are real and already paid for, so show them
      // rather than throwing away a four-minute build.
      endRun(source);
      addEntry("warn", escapeHtml(ev.message));
      showResults(runId);
      refreshRail(runId);
    } else if (ev.type === "error") {
      endRun(source);
      // The server's sentence alone. This read "Something broke: The department
      // hit an unexpected problem and stopped" — the failure stated twice, the
      // second time in a register nothing else in the app uses. Both messages
      // star/server.py can send here declare the failure in their first clause
      // ("...was stopped before anything could be filed", "...hit an unexpected
      // problem and stopped"), so the prefix framed nothing. The bare-exception
      // case it was written for was deleted from the server in b676afe/1798a9e
      // because it leaked library names and a stray credential.
      //
      // Note for anyone tempted to lean on colour instead: #timeline li.error
      // recolours only the 9px dot, not the text, unlike .warn which recolours
      // both. This line is distinguished by what it says, not by how it looks.
      addEntry("error", escapeHtml(ev.message));
      markRunFailed(ev.message);
      $("build-btn").disabled = false;
    }
  };

  source.onerror = () => {
    /* On the build path the stream closes naturally on completion; ignore.
       On the resume path a failure before the first event is the run having
       left the server's registry — see this function's header. */
    if (!resumed || received) return;
    endRun(source);
    showResults(runId);
    refreshRail(runId);
  };

  activeSource = source;
  return source;
}

function closeStream() {
  if (activeSource) activeSource.close();
  activeSource = null;
}

/** One run's end, from every terminal branch.
 *
 *  Clearing the live-run pair matters beyond tidiness: it is what the link
 *  redirect reads. A finished run left in these variables would be stashed on
 *  the way to Google and then reopened as a stream on the way back, which is a
 *  request for a run the server has already let go of. */
function endRun(source) {
  stopElapsedTimer();
  sweepUnfiledDrawers();
  source.close();
  if (activeSource === source) activeSource = null;
  liveRunId = null;
  liveStreamKey = null;
  // Cleared here rather than in each terminal branch, for the same reason the
  // pair above is: a stale live-run id would send a reader from the rail to a
  // progress panel for a run that has already filed.
  setLiveRun(null);
  // And the armed control goes back to resting: a run that finishes while the
  // button is armed would otherwise leave a warning about spending on a run
  // that has already stopped spending.
  disarmNewRoom();
  // The stash outlives the run unless something drops it. takeStashedRun
  // deletes on read, but only a load reads it, and a run that finishes while
  // the page stays open never gets one — so the next load would resume a room
  // that had already filed.
  clearStashedRun();
}

/** Clears the room view back to its resting state before a repaint.
 *
 *  Every one of these is a real cross-room leak, not defensive tidiness, and
 *  WHERE THIS IS CALLED FROM is the whole of whether it works. It shipped after
 *  the fetch, which closed nothing: shell.js's loadRoom reveals the stage before
 *  awaiting the renderer, so a reader on room A who clicks room B in the rail
 *  watched A's title, A's docket, A's four drawers and A's open bible sit there
 *  for the entire round trip, under a rail that had already marked B active. A
 *  load that failed was worse — showResults returns early on !res.ok, so A
 *  stayed mounted behind the intake panel indefinitely.
 *
 *  It is now the first statement in showResults, before the request is even
 *  issued, which covers the in-flight window and every early return after it.
 *
 *  The title goes to a transitional string rather than being blanked or left
 *  alone: blank collapses the docket's heading row mid-navigation, and leaving
 *  the previous room's title is the leak itself. */
function resetRoomView(nextRunId) {
  setRoomMode("drawers");
  bibleBtn.classList.add("hidden");
  checkBtn.classList.add("hidden");
  bibleSurface.innerHTML = "";
  roomGrid.replaceChildren();
  docketBody.innerHTML = "";
  // The same cross-room leak this function exists to close, on the surface
  // where it would cost the most: a scene pasted against room A left sitting
  // in the box under room B's title, over a marked scene citing A's ledger.
  //
  // The room id goes through so a re-entry into the room already open keeps an
  // unsubmitted scene. That is not a weakening of the leak fix: a leak needs
  // two rooms, and this is the one case where there is only one.
  resetCheck(nextRunId);
  $("result-title").textContent = "Opening the room";
  $("result-stats").textContent = "";
}

/** Fetches one room and paints it into the results panel.
 *
 *  Both the live-build "complete" handler above and shell.js's loadRoom() (a
 *  rail click) call this same function, so a saved room and a just-finished
 *  one render identically — the promise this file has carried since Task 3 and
 *  the reason the drawer component has one payload shape for both. */
async function showResults(runId) {
  // First, before the request goes out. shell.js's loadRoom has already
  // revealed the stage by the time this runs — see resetRoomView.
  resetRoomView(runId);
  openRoomId = runId;
  // Disarmed on every room open, so an armed control never carries over from
  // the room a reader just left to the one they are now looking at. The edit
  // panel closes for the same reason, and because a half-typed name for one
  // room sitting over another room's heading is the app losing track of what
  // the reader is doing.
  disarmRoomDelete();
  closeRoomEdit();

  const res = await authedFetch(`/api/rooms/${runId}`);
  if (!res.ok) {
    // Without this check, `result` below is undefined and the story_profile
    // read throws — but only after the results panel is already revealed,
    // leaving an empty panel with no explanation. Fail back to intake with
    // a real message instead.
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* body wasn't JSON; fall back to statusText */
    }
    showIntake();
    $("intake-error").textContent = `Could not load your results: ${detail}`;
    $("build-btn").disabled = false;
    return;
  }
  const { status, result } = await res.json();
  const hasProfile = Boolean(
    result && result.story_profile && Object.keys(result.story_profile).length > 0
  );

  showRoom();
  $("build-btn").disabled = false;

  // A room can be listed in the rail before it has anything to show: still
  // running, or interrupted/errored before intake ever finished. Say so
  // plainly rather than reading `null.story_profile` and crashing the panel.
  if (!hasProfile) {
    const copy = {
      // Reworded in the glow campaign's wave 1. The old sentence — "Reconnecting
      // to a live run isn't available yet" — described the product's roadmap
      // rather than the reader's next step, and stopped being true in the same
      // wave: every run is stashed now, so a reload in the same tab picks its
      // own run back up. This branch is what is left after that, and it is a
      // narrower thing: a run that IS live but that THIS page is not watching —
      // another tab, or a stash already consumed. Says that, and offers the
      // one action available.
      running: [
        "Still in the department",
        "This room is still being researched, and this page is not watching that run. Check again, or open it once it has filed.",
      ],
      // States what the payload proves — nothing was filed — and not why.
      // "the server restarted" was one cause of a document stuck at
      // status "running"; the other is _persist swallowing an exception on
      // the TERMINAL write (star/server.py), which leaves the creation-time
      // document in place after a run that completed and filed four drawers.
      // In that case both halves of the old sentence were false, and the
      // owner was told their finished research never happened. Same defect
      // as the failed-drawer copy fixed in 98384c3, in a sibling branch.
      interrupted: [
        "Interrupted before it filed",
        "This run never finished — nothing was filed under it. Start a new room instead.",
      ],
      error: [
        "Did not file",
        "This run hit an error before anything could be filed. Start a new room instead.",
      ],
    }[status] || [
      "Nothing filed yet",
      "This room has no research to show.",
    ];
    $("result-title").textContent = copy[0];
    // The room's own account of itself, when it has one, in place of the
    // generic sentence above. The copy in `copy[1]` names the CLASS of failure
    // — this run hit an error — because until star/store.py started keeping a
    // `note` that was the most any reopened room could say: the specific
    // explanation was pushed down the SSE stream while the run died and went
    // with the tab that was watching. A writer coming back the next morning
    // got "hit an error" for a run that had actually run past its time limit,
    // and no way to tell the two apart or to know a shorter treatment would
    // work. Both sentences say the same thing when there is no note; when
    // there is one, the stored sentence is the more specific of the two and
    // printing both would say it twice.
    const filedNote = (result && result.note) || "";
    docketBody.innerHTML =
      `<p class="docket-note">${escapeHtml(filedNote || copy[1])}</p>`;

    // What it cost, on the reopen path. A room that failed still spent live
    // searches and a day's build, and the sentences above say only that it
    // filed nothing — which reads like it cost nothing. The count is the
    // room's own, from the stored document, so it is the run's real spend and
    // not a number this file made up.
    const spentSearches = (result && result.search_count) || 0;
    if (spentSearches > 0 && status !== "running") {
      const spent = document.createElement("p");
      spent.className = "docket-note";
      spent.textContent =
        `It spent ${spentSearches} live search${spentSearches === 1 ? "" : "es"} ` +
        "before it stopped. Those are not refunded, and it used one of the " +
        "department's daily builds.";
      docketBody.appendChild(spent);
    }
    // The one action a reader has on a run they are not watching. Without it
    // the only way to learn a build had finished was to reload the whole page
    // on a hunch — the surface said "check back" and gave nothing to check
    // with.
    //
    // A control rather than a timer, deliberately. A poll would need a handle
    // cleared on every stage change, and shell.js owns stage changes while this
    // file owns the interval; a leaked interval hammering /api/rooms is a worse
    // failure than one extra press. Recorded as a deviation from the wave
    // brief, which proposed a 5s poll.
    if (status === "running") {
      const again = document.createElement("button");
      again.type = "button";
      again.className = "docket-btn";
      again.textContent = "Check again";
      again.addEventListener("click", () => showResults(runId));
      docketBody.appendChild(again);
    }
    return;
  }

  // Below the early return, deliberately, so the no-profile branch never gets
  // here. A room with no story profile filed nothing to check a scene against,
  // and offering a check there offers to spend live searches against an empty
  // ledger — on the same screen whose copy has just told the reader to start a
  // new room instead. `_run_check` would still accept it (star/server.py
  // refuses only a build genuinely in flight), so this is the surface
  // declining rather than the server.
  setCheckRoom(runId);
  paintRoom(result, status);
  // After paintRoom, which writes the heading this reads back from the rail.
  fillRoomEdit(result);
}

/** The filed room: a docket, four drawers, and a bible one control away.
 *
 *  Drawer state is FILED for all four, every time. That is the state
 *  docs/design/DIRECTION.md's >40% manila rule is written against, and it is
 *  also the honest default — a room opened with one drawer already expanded
 *  would be asserting that one researcher's category is the one you came for. */
function paintRoom(result, status) {
  const profile = result.story_profile || {};
  const plan = result.research_plan || {};
  const categories = result.categories || {};
  // One date for the whole room, read once. Both the FILED stamp and every
  // receipt's RET line are claims about the same run, and reading created_at
  // twice would be two chances to format it differently.
  const filed = roomDate(result.created_at);

  $("result-title").textContent = profile.title || "Your research room";
  $("result-stats").textContent = statsLine(result, filed);
  docketBody.innerHTML = renderDocket(profile, status, result);

  const grid = createDrawerGrid();
  // Spread first: `children` is a LIVE HTMLCollection and mountRoomDrawer adds
  // a node inside each drawer. Nothing it adds is a child of the grid today,
  // so iterating the collection directly would work — and would break silently
  // the first time a later change mounts something at grid level.
  for (const el of [...grid.children]) {
    mountRoomDrawer(el, categories[el.dataset.category], plan, filed);
  }
  roomGrid.replaceChildren(grid);

  bibleSurface.innerHTML = renderBible(result, status);
  makeLinksSafe(bibleSurface);
  bibleBtn.classList.remove("hidden");
  checkBtn.classList.remove("hidden");
}

/** Counts and provenance, in the slug face. Source count is the ledger's own
 *  size (star/server.py sends `len(run["ledger"])`), so it is sources SEEN, not
 *  sources cited — worth saying plainly rather than letting "106 sources" imply
 *  106 footnotes. Each piece is dropped rather than defaulted when it is
 *  missing: "? web searches" was a shrug printed where a number belongs.
 *
 *  The search half used to read "17 cited web searches", and the discipline
 *  this docstring argues for the number BESIDE it is exactly what that broke.
 *  star/server.py:470 increments run["search_count"] inside the block reading
 *  `call.args` — the tool CALL — while the ledger is written separately from
 *  the responses, and the check path increments before the request is even
 *  sent. It counts searches ISSUED. "Cited" asserts both that something came
 *  back and that a finding leaned on it, and this number knows neither; the
 *  server ships a guard for exactly that gap (`search_count > 0 and
 *  len(ledger) == 0`). Copy rule 3, applied to a number instead of to a word.
 *
 *  "Cited link" elsewhere in the app is NOT the same claim and stays: a model
 *  really did cite that URL, which is what makes its absence from the ledger
 *  worth reporting. */
function statsLine(result, filed) {
  const parts = [];
  // typeof, not Number(): `Number(null)` is 0, and a room whose count never
  // reached the client would have printed a confident "0 web searches" for a
  // run that ran seventeen.
  if (typeof result.search_count === "number") {
    parts.push(plural(result.search_count, "web search"));
  }
  if (typeof result.source_count === "number" && result.source_count > 0) {
    parts.push(`${plural(result.source_count, "source")} returned`);
  }
  if (filed) parts.push(`filed ${filed}`);
  return parts.join(" · ");
}

/** Standard English pluralization, sibilants included — "search" takes "+es".
 *  The same rule web/clip.js exports, duplicated here rather than imported
 *  because this file's only other reason to reach into clip.js would be
 *  escapeHtml, which it already has its own copy of. Recorded as a known
 *  duplication, not an oversight: see this file's escapeHtml below. */
function plural(n, word) {
  const suffix = /(?:[sxz]|[cs]h)$/i.test(word) ? "es" : "s";
  return n === 1 ? `${n} ${word}` : `${n} ${word}${suffix}`;
}

/** The docket — the department's read of the treatment, on the cover sheet.
 *
 *  This is the old Story Profile tab, unbundled. It was the second of three
 *  tabs and nobody who wanted their research clicked it; as a cover sheet it
 *  costs one glance and identifies the room. `logline` leads because it is the
 *  one line that says what this room is FOR.
 *
 *  THE ONE THING TASK 7 REMOVED: the "Needs grounding" row, which chipped out
 *  `profile.key_entities`. Three reasons, in the order they mattered.
 *
 *  It was the only block on the cover sheet that neither identifies the room
 *  (title, era/genre, logline do that) nor states what the department did
 *  (the stats line does that). It listed nouns.
 *
 *  It said, generically, what the drawers now say specifically. Since Task 6
 *  every drawer carries its own questions and the scene each was asked for,
 *  filed under the researcher who asked it — the same information attached to
 *  the evidence that answers it. On the real Detroit room the chips read
 *  "Purple Gang", "U.S. Border Patrol", "Whisky bootlegging", every one of
 *  which the logline directly above already names in a sentence.
 *
 *  And it cost the still frame 55px at the top of the page. At 1440x900 the
 *  drawer row starts below the fold by exactly the kind of margin a chip row
 *  spends. This is the frame most likely to appear in a submission gallery and
 *  the drawers are the argument; a list of extracted nouns is not.
 *
 *  `profile.key_entities` is untouched in the payload and still stored. Nothing
 *  was deleted from the room — one restatement was dropped from its cover.
 *
 *  Every value is server data on an adversarial path — the profile is extracted
 *  from the treatment by a model — so all of it is escaped, chips included. */
// `result` is a parameter because it used to be a free variable, and on the one
// status that reads it the docket did not paint at all. The reference below is
// short-circuited unless `status === "partial"`, which is why this survived
// every complete run and every test: `renderDocket` threw a ReferenceError only
// on a salvaged room, and `paintRoom` assigns its return straight into
// `docketBody.innerHTML`, so the throw took the whole docket with it. A partial
// room is a real terminal state — `_salvage` files one whenever at least one
// researcher came back — and it is the state where a reader most needs the
// docket to explain what happened.
function renderDocket(profile, status, result) {
  const chips = (values) =>
    (Array.isArray(values) ? values : [])
      .map((value) => String(value).trim())
      .filter(Boolean)
      .map((value) => `<span class="chip">${escapeHtml(value)}</span>`)
      .join("");
  const row = (label, html) =>
    html ? `<div class="kv"><div class="k">${label}</div>${html}</div>` : "";

  const slug = [profile.era, profile.genre]
    .map((v) => String(v || "").trim())
    .filter(Boolean)
    .map((v) => escapeHtml(v))
    .join(" &middot; ");

  return `
    ${status === "partial" && !String(result.research_bible || "").trim() ? partialDocketNote() : ""}
    ${slug ? `<p class="docket-slug">${slug}</p>` : ""}
    ${
      profile.logline
        ? `<p class="docket-logline">${escapeHtml(profile.logline)}</p>`
        : ""
    }
    ${row("Locations", chips(profile.locations))}
    ${renderVerifyNotes(result)}
  `;
}

/** What the researchers said to check before writing, on the docket.
 *
 *  The judge's round-two review asked for exactly this. The "Verify before
 *  writing" block is well written and it lives inside the bible's prose: "It
 *  belongs in the room's summary too — a writer who skims drawers and never
 *  reads the bible top-to-bottom shouldn't miss the one line that saves them a
 *  rewrite." One stored room's first note tells its writer their own treatment
 *  dates its blackout two months wrong. That line is five screens down inside
 *  section one.
 *
 *  THE NOTES ARE THE SERVER'S. star/bible.py lifts them out of the document
 *  and ships them in the payload; parsing the bible again here would be a
 *  second implementation of one extraction in a second language, which is how
 *  web/consent.js came to say "four calls" the day a fifth tool landed.
 *
 *  Nothing is rendered when there is nothing to say. Most sections report "None
 *  noted in field findings" and the server drops those — an empty caution box
 *  over a clean room teaches a reader to skim past the one that matters. */
function renderVerifyNotes(result) {
  const notes = Array.isArray(result.verify_notes) ? result.verify_notes : [];
  if (notes.length === 0) return "";
  return `
    <div class="verify-notes">
      <p class="verify-notes-head">Verify before writing</p>
      <ul class="verify-notes-list">
        ${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}
      </ul>
    </div>`;
}

/** Did this category's researcher file anything at all?
 *
 *  ONE rule with two consumers — the drawer's mounted state and the bible
 *  surface's sentence about how many researchers filed. They describe the same
 *  fact about the same room, on the same screen, so they read it through the
 *  same function: a page that says "two of the four researchers filed" over
 *  four drawers stamped FILED would be worse than either mistake alone.
 *
 *  `markdown` is star/findings.py's `raw`, the researcher's prose kept verbatim.
 *  Empty means the agent never wrote its output_key — reachable whenever a run
 *  is salvaged while some researchers are still working. Non-empty with no
 *  findings means they wrote and nothing parsed, which is a filing. */
function categoryFiled(doc) {
  return Boolean(String(doc?.markdown || "").trim());
}

function filedCount(categories) {
  return Object.values(categories || {}).filter(categoryFiled).length;
}

/** The partial room, on the cover sheet.
 *
 *  Stated up front rather than left for whoever clicks through to the bible,
 *  because a partial room is otherwise indistinguishable from a finished one
 *  until you go looking — and finding out by absence is how a reader concludes
 *  something went wrong. It did not. See renderBible for the full register.
 *
 *  "with its sources" was cut from this line in review round 1. A finding whose
 *  every cited URL failed to resolve against the ledger keeps its place with
 *  citations: [] (star/findings.py), and renders as a clip with an UNSOURCED
 *  stamp and no receipts at all. A one-line summary is exactly where a
 *  universal claim does the most damage, because nothing next to it qualifies
 *  it. What is true without exception is that the research is in the drawers. */
/*  Gated on the bible actually being absent, not on status === "partial".
 *  star/server.py's _salvage deliberately KEEPS a bible that synthesis wrote
 *  before the ceiling tripped ("rather than discarding a real bible"), so
 *  `partial` and `has a bible` are not mutually exclusive. Gated on status
 *  alone, this note printed "Filed without a bible" on a cover sheet with a
 *  working bible button beside it — and noBibleCopy, which does the honest
 *  counting, never runs in that branch to correct it. Both surfaces now read
 *  the same fact rather than two proxies for it. */
function partialDocketNote() {
  return `<p class="docket-note">Filed without a bible. The research is in the drawers.</p>`;
}

/** One drawer of a filed room, mounted with its own toggle.
 *
 *  The toggle is created HERE and inserted as a direct child of the card rather
 *  than into `.drawer-body`, and that placement is load-bearing:
 *  setDrawerState replaces the body's innerHTML on every state change, so a
 *  control living inside it would be destroyed by the very click that used it.
 *  As a sibling of the body it survives filed <-> expanded, keeps its focus
 *  through the transition, and keeps its aria-controls pointing at a node that
 *  does not get replaced.
 *
 *  It sits BEFORE the body for the same reason every disclosure does: the
 *  control precedes what it controls, which is both the reading order and what
 *  aria-controls describes. On an expanded card — 1300px of clips for a real
 *  category — a close control only at the bottom would be a control you have to
 *  scroll past the content to find. */
function mountRoomDrawer(el, doc, plan, filed) {
  const category = el.dataset.category;
  const body = el.querySelector(".drawer-body");
  body.id = `drawer-body-${category}`;

  // A category absent from the payload is not a category with no findings.
  // star/server.py's _build_categories always emits all four, so this is a
  // document written by an older server — say the drawer did not file rather
  // than stamping FILED on an object that does not exist.
  if (!doc) {
    setDrawerState(el, "failed", {
      message: "This room was filed without a record for this category.",
    });
    return;
  }

  // A researcher that never wrote anything is not a researcher that filed
  // nothing of note, and the difference is visible in the payload: when a run
  // is salvaged mid-flight (star/server.py's _salvage) `_build_categories`
  // still emits all four keys, and a category whose agent never reached its
  // output_key comes through parse_findings(None, …) as markdown "" with no
  // findings and no field notes. Stamping FILED on that says a researcher
  // filed when none did. `markdown` is the raw prose held verbatim
  // (star/models.py), so a non-empty one is proof something was written even
  // when nothing in it parsed — that case stays FILED, and clip.js already
  // has the copy for it.
  // Says only what the payload proves — that nothing was filed — and not WHY.
  // The earlier wording ("when the run stopped") smuggled in a second claim,
  // that the run ended early. True for the salvaged case this branch was
  // written for, but the gate is not scoped to `partial`: a "complete" room
  // reaches it too if a researcher's turn ever commits an empty output_key
  // while its siblings finish. Nobody has produced that state and it may not
  // be reachable, which is exactly why the copy should not bet on it. An
  // interface that explains a cause it cannot see is guessing out loud.
  if (!categoryFiled(doc)) {
    setDrawerState(el, "failed", {
      message: "This researcher filed nothing for this room.",
    });
    return;
  }

  const payload = {
    doc,
    plan,
    code: CATEGORY_CODE[category],
    // `date` and `retrieved` are the same value here and that is a claim, not
    // a shortcut. web/drawer.js refuses to default one from the other because
    // a live render's "today" is not a retrieval date for a stored room. Both
    // of these come from the room's own created_at: a room was filed by the
    // run that retrieved its sources, so for a stored room the two facts are
    // genuinely the same day, and this is the caller stating that on purpose.
    date: filed,
    retrieved: filed,
    // Which room these clips belong to, so each one can offer the card that
    // defends it. Read from module state rather than threaded down through
    // paintRoom's arguments: `openRoomId` is what every other control on this
    // screen already acts on, and a second copy travelling by a different
    // route is how a card ends up citing the room a reader was looking at
    // before this one.
    runId: openRoomId,
  };

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "drawer-toggle";
  toggle.setAttribute("aria-controls", body.id);
  el.insertBefore(toggle, body);

  const setOpen = (open) => {
    setDrawerState(el, open ? "expanded" : "filed", payload);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "Close the drawer" : "Open the drawer";
    // Four buttons reading "Open the drawer" are four identical entries in a
    // screen reader's control list. The accessible name contains the visible
    // one verbatim (WCAG 2.5.3) and adds the plate the eye already has.
    toggle.setAttribute(
      "aria-label",
      `${toggle.textContent}: ${DRAWER_LABELS[category]}`
    );
  };

  toggle.addEventListener("click", () => {
    const open = el.dataset.state !== "expanded";
    setOpen(open);
    // Expanding a RIGHT-column drawer sends it to the next grid row, full
    // width, below a first row that already runs past the fold. Measured on the
    // filed Gdansk room from a room scrolled to its top, every drawer, the rest
    // closed: the two left-column cards move 0px, and the two right-column ones
    // move +623px and +602px. The first of those is on screen when it is
    // clicked and 84px below the fold when the click resolves, so the click
    // reads as dead — the card the reader pressed is simply gone.
    //
    // The card, not the toggle. The toggle sits below the drawer's plate, so
    // aligning IT to the top of the scroller would cut off the head of the very
    // thing the reader just asked to see.
    //
    // Here rather than inside setOpen, because scrolling is a response to a
    // press and not a property of being open: setOpen(false) runs once at
    // construction for all four drawers, and a future caller restoring an
    // expanded drawer must not yank the page around.
    //
    // No-op for the left column, which does not move, and below 560px where the
    // grid is one column. Costs nothing in either case.
    if (open) el.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  });
  setOpen(false);
}

/** The bible, or the honest account of a room that has none.
 *
 *  Adversarial by construction: the bible is synthesised by a model from live
 *  web pages it did not choose. It goes through DOMPurify or it does not render
 *  as HTML at all — if either vendored library failed to load, the fallback is
 *  escaped plain text, never the raw string. */
function renderBible(result, status) {
  const markdown = String(result.research_bible || "").trim();
  if (markdown) {
    return `
      <h3 class="bible-heading">The research bible</h3>
      ${shortBibleNote(result)}
      <div class="bible-body">${bibleHtml(markdown)}</div>`;
  }
  const { heading, body } = noBibleCopy(status, result.categories);
  return `
    <h3 class="bible-heading">${heading}</h3>
    ${body.map((line) => `<p class="bible-note">${line}</p>`).join("")}`;
}

/** A bible that stops early, said above the bible rather than discovered
 *  halfway down it.
 *
 *  A room reports "complete" when the pipeline reached its end, which is not
 *  the same claim as "the bible is whole" — and for seven of the fourteen
 *  rooms stored on 2026-08-11 the two came apart. The document just stops,
 *  usually mid-sentence, with sections the researchers filed for missing. A
 *  reader who scrolls to the bottom finds that out the slow way and has no
 *  way to tell a short bible from a short subject.
 *
 *  THE COUNT IS THE SERVER'S, not this file's. star/bible.py measures which of
 *  the room's own filed drawers reached the document and ships the answer in
 *  the payload. Recomputing it here would be the second implementation of one
 *  fact in a language that cannot see the first — which is exactly how
 *  consent.js came to say "four calls" on the day a fifth tool shipped. */
function shortBibleNote(result) {
  const counts = result.bible_coverage;
  if (!counts || !counts.missing) return "";
  if (counts.missing.length === 0) {
    // Every section arrived and the document still stopped short. Only rooms
    // built since the editor's own finish reason started being recorded can
    // say this — counting sections cannot see it, because by that question
    // the document is whole.
    if (!counts.truncated) return "";
    return `<p class="bible-short">This bible reached all ${counts.expected} of its
      sections and then stopped before it finished, mid-sentence. Nothing is
      missing from the room: the findings behind every section are filed above
      with their sources.</p>`;
  }
  const missing = counts.missing.map(escapeHtml);
  const names =
    missing.length === 1
      ? missing[0]
      : `${missing.slice(0, -1).join(", ")} and ${missing[missing.length - 1]}`;
  return `<p class="bible-short">This bible is short: it covers ${counts.covered} of
    the ${counts.expected} drawers this room filed, and stops before ${names}.
    The findings those sections would have been written from are filed above
    and carry their sources.</p>`;
}

function bibleHtml(markdown) {
  if (window.marked && window.DOMPurify) {
    return DOMPurify.sanitize(marked.parse(markdown));
  }
  return `<pre class="bible-raw">${escapeHtml(markdown)}</pre>`;
}

/** A room with no bible, in the department's voice.
 *
 *  A partial run (star/server.py's _salvage) is a COMPLETE OUTCOME OF A
 *  DIFFERENT SHAPE, and the copy is written to hold that line under pressure:
 *  the research that exists was gathered and checked the way all of it is, and
 *  the one step that did not run is the editor's. Nothing here apologises,
 *  hedges, or lets a reader conclude the research is suspect.
 *
 *  Holding that register does not license overstating the room, and review
 *  round 1 caught this copy doing exactly that, twice:
 *
 *    - "All four researchers filed" was asserted, never counted. `_salvage`
 *      returns True if ANY category has findings, so a ceiling that trips while
 *      two researchers are still searching produces a partial room with two
 *      empty categories. The count is now read from the payload through
 *      categoryFiled, the same function that decides whether each drawer mounts
 *      FILED or FAILED, so the sentence and the drawers cannot disagree.
 *
 *    - "Every fact carries the source it came from and the excerpt that source
 *      returned" was false in two independent ways. star/findings.py keeps a
 *      Finding whose every cited URL failed to resolve, with citations: [] and
 *      the URLs in unverified_urls — that clip has an UNSOURCED stamp and no
 *      receipt at all, and star/server.py's _maybe_warn_empty_ledger exists
 *      because a whole run can land that way. Separately, _best_excerpt returns
 *      "" for a ledger entry carrying no excerpts, which is why clip.js already
 *      ships "There is nothing to quote." The sentence now promises what the
 *      clips actually show: the sources that came back, the excerpt where there
 *      was one, and a mark on the links that never came back.
 *
 *  The distinction from the empty-complete case is kept: a "complete" room with
 *  no bible means synthesis produced nothing, which is a different fact and
 *  gets a different sentence. */
function noBibleCopy(status, categories) {
  // Spelled out, and the noun after the count, because the obvious
  // construction is the wrong one: plural() renders "2 researchers", and
  // "2 researchers of the four filed" is not a sentence anyone writes. Caught
  // by reading the rendered string in a browser rather than the template.
  // Four gets its own branch — "Four of the four researchers filed" reads like
  // a hedge about a room where nothing is missing.
  const filed = filedCount(categories);
  const total = Object.keys(DRAWER_LABELS).length;
  const spelled = ["No", "One", "Two", "Three", "Four"];
  let whoFiled;
  if (filed >= total) {
    whoFiled = "All four researchers filed.";
  } else if (filed > 0) {
    whoFiled = `${spelled[filed]} of the four researchers filed. The others did not, and their drawers say so.`;
  } else {
    // Unreachable from a partial room — _salvage refuses to produce one
    // without findings, and findings require prose. Defensive, and it still
    // must not claim a filing.
    whoFiled = "No researcher filed.";
  }
  // One sentence, used by both branches: it is the claim about evidence, and
  // there is only one true version of it.
  const whatIsThere =
    "Every fact in the drawers shows the sources that came back for it, with " +
    "the search's own excerpt where there was one, and any cited link that " +
    "never came back is marked on its clip rather than dropped.";

  if (status === "partial") {
    return {
      heading: "This room is filed as clips",
      body: [
        `${whoFiled} What they filed was gathered the same way, and checked the same way, as the research in a room that has a bible. ${whatIsThere}`,
        "The step that did not run is the editor's: folding those findings into one written document. The drawers hold the research; read it there.",
      ],
    };
  }
  return {
    heading: "No bible was written for this room",
    body: [
      `The editor produced nothing to read. What the researchers filed is untouched by that. ${whatIsThere}`,
    ],
  };
}

function makeLinksSafe(container) {
  container.querySelectorAll("a").forEach((a) => {
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** Picks a build back up after the page went to Google and came back.
 *
 *  The OAuth flow is a full-page navigation, so `{run_id, stream_key}` — which
 *  live nowhere but this file's memory — are gone by the time the reader
 *  returns. The run is not: the asyncio task keeps going and `_persist` writes
 *  at terminal status. What is lost is the stream, and the stash auth.js wrote
 *  before the redirect is what buys it back.
 *
 *  The server is asked first, because the run may well have finished while the
 *  reader was choosing a Google account, and reopening a stream for a run that
 *  has already filed is a 404 with a spinner on top of it.
 *
 *  WHY THE STREAM REPLAYS FROM THE BEGINNING RATHER THAN FROM THE STASHED ID.
 *  EventSource sets Last-Event-ID itself on automatic reconnects and there is
 *  no way for a page to set it on a fresh construction — it is not a header a
 *  caller can supply. That turns out to be the right behaviour here rather than
 *  a limitation worked around: everything the earlier events built lived in
 *  page memory and died with the page, so a resume that started at the stashed
 *  id would leave four drawers stuck at idle and then stamp them "did not file"
 *  on a run where they did. Replaying the whole history rebuilds the timeline,
 *  the drawer states, and the search tally from the run's own record, and the
 *  monotonic guard in openStream is what makes that free of duplicates. The
 *  stashed id is still carried, because it is the one number a future in-page
 *  continuation would need and it costs nothing to keep. */
async function resumeStashedRun() {
  const stashed = takeStashedRun();
  if (!stashed) return null;

  let status = null;
  try {
    const res = await authedFetch(`/api/rooms/${encodeURIComponent(stashed.run_id)}`);
    if (res.ok) ({ status } = await res.json());
  } catch {
    status = null;
  }

  // Unreadable is not the same as finished. Fall through to the ordinary load
  // rather than opening a room this page could not confirm exists.
  if (status === null) return null;

  if (status !== "running") {
    await showResults(stashed.run_id);
    return stashed.run_id;
  }

  resetProgress();
  showRunning();
  // No startedAt: the running branch of GET /api/rooms/{id} returns
  // `result: null`, so there is no created_at to read and this page genuinely
  // does not know when the build began. updateMeter drops the clause.
  startElapsedTimer({ startedAt: null });
  // Neutral, because this path is no longer only the sign-in's. Every run is
  // stashed now, so a reload, a crash, or a locked phone arrives here too, and
  // "Back from the sign-in" would be false for three of the four ways in.
  addEntry("done", "Picking the run up where it was.");
  openStream(stashed.run_id, stashed.stream_key, { resumed: true });
  return stashed.run_id;
}

// Wire the shell to this file's room renderer, then sign in and populate
// the rail. A failed sign-in shows the same banner buildRoom's own check
// would show later — no reason to wait for a build attempt to learn the
// department can't be reached at all.
setRoomRenderer(showResults);

// The Script Check surface binds its own controls to index.html. Done here
// rather than at that module's own load, so importing it costs nothing until
// this file says the DOM is the app's — which is what lets its renderer be
// tested in Node against a stubbed document.
initScriptCheck();

// The card does the same, and does less: #account-panel ships EMPTY, so this
// only takes the reference. Not one sentence of the card's copy reaches the
// DOM until the rail's entry is used, which is how the intake path carries
// zero mentions of Google or of accounts while the surface that offers both
// lives in the same document.
initAccount();

// auth.js asks for this on its way out to Google, and — since wave 1 —
// on every openStream, because a reload loses the stream_key the same way a
// redirect does. Read at call time rather than pushed on every event: the
// values are already tracked for the stream's own sake, and a getter cannot go
// stale between updates.
setLiveRunProvider(() =>
  liveRunId && liveStreamKey
    ? { run_id: liveRunId, stream_key: liveStreamKey, last_event_id: lastEventId }
    : null
);

(async function init() {
  // FIRST, and before the token is asked for. completeGoogleLink strips the
  // returned fragment out of the address bar as its opening move, and on a
  // successful link it is what puts the linked token in place — so the rail
  // below is drawn with the session the reader just finished establishing
  // rather than the one they had a moment ago. It resolves to a plain result
  // object on every path including "nothing happened"; nothing here throws.
  //
  // What it does NOT do is render anything, and that is still true now the
  // card exists: the intake carries no mention of Google or of accounts by
  // design, so a link that came back refused must not paint a sentence onto
  // the first screen. The outcome is cached inside auth.js and web/account.js
  // reads it when the reader opens the card — which is the only place on this
  // app where that sentence belongs.
  const linked = await completeGoogleLink();

  // A link that began somewhere else goes back there.
  //
  // `beginGoogleLink` has always stashed a `returnTo` and `completeGoogleLink`
  // has always handed it back, and until now nothing navigated to it — which
  // worked only because the one caller was the card, whose `returnTo` is this
  // page. The OAuth consent screen is the second caller and it is not: a reader
  // sent to sign in from `/consent.html?...` would land here, correctly linked,
  // with the request that sent them abandoned and a client still waiting.
  //
  // Safe because `auth.js` filters the value to a same-origin absolute path
  // before it is ever stashed, so this cannot become an open redirect no matter
  // what a caller passes. The guard against a redirect loop is that the card's
  // own `returnTo` is this path, so it fails the comparison and does nothing.
  if (linked?.status === "linked" && linked.returnTo) {
    const here = `${location.pathname}${location.search}`;
    if (linked.returnTo !== here) {
      location.assign(linked.returnTo);
      return;
    }
  }

  let token;
  try {
    token = await getIdToken();
  } catch {
    token = null;
  }
  if (!token) {
    showAuthError(true);
    return;
  }
  // The rail is drawn either way. A resumed run marks itself active in it
  // rather than replacing it — a reader who comes back mid-build still has
  // every other room one click away.
  const resumedRunId = await resumeStashedRun();
  await refreshRail(resumedRunId ?? undefined);
})();
