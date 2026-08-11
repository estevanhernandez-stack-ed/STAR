/* THE MORGUE — the cabinet shell.
   Owns the rail of saved rooms and which panel the stage shows. It does not
   know what a filed room looks like once it's open — that's the drawer and
   clip components landing in Tasks 3-5. app.js registers the function that
   turns a run_id into stage content via setRoomRenderer(); this file only
   ever calls it by name.

   Since the glow campaign's wave 1 it owns a THIRD thing: which run is
   streaming, set from both ends of a run's life in app.js via setLiveRun().
   It is here rather than there because this file owns what a rail click does,
   and a row for a run in flight has to go somewhere different from a row for a
   filed room — showRunning() rather than loadRoom(), which would fetch a room
   with no story_profile yet and paint a placeholder over a live stream.

   Since Task 4 the stage has four states, not three. The fourth is the card
   (web/account.js), reached from the entry at the FOOT of the rail and from
   nowhere else — that placement is the requirement, not a layout preference:
   prd.md's first identity story is a writer who will never sign in to
   anything, and the intake path from landing to a filed room has to contain
   zero mentions of Google or of accounts. A rail entry reading "Your card" in
   --pencil is what that costs. This file binds nothing to it; web/app.js does,
   the same way it already binds #new-room-btn.
*/

import { authedFetch } from "/auth.js";

const $ = (id) => document.getElementById(id);

const railList = $("rail-list");
const railFoot = $("rail-foot");
const intakePanel = $("intake-panel");
const progressPanel = $("progress-panel");
const resultsPanel = $("results-panel");
const accountPanel = $("account-panel");

// Every panel the stage can show, so the switch below is a list and not four
// hand-written triples. The fourth was added in Task 4 and the previous shape
// — each showX() naming the other two by hand — is exactly the shape where a
// fifth surface gets added and one function forgets to hide it.
const PANELS = [intakePanel, progressPanel, resultsPanel, accountPanel];

let _rooms = [];
let _activeRunId = null;
let _renderRoom = null; // (runId) => Promise<void> | void
// The last stage that was not the card. Written by stage(), read by
// showPreviousStage(); null until the first stage change, which is why that
// function falls back to intake rather than trusting it.
let _lastStageBeforeAccount = null;
// The run currently streaming, or null. Set by web/app.js at both ends of a
// run's life. The rail needs it because a row for a run in flight has to go
// somewhere different from a row for a filed room, and this file is the one
// that owns what a rail click does.
let _liveRunId = null;
// Did the last attempt to READ the list fail? Remembered rather than passed,
// because showIntake() and loadRoom() redraw the rail from this cache without
// going near the network — and an empty `_rooms` means two different things
// depending on this flag. Without it the honest sentence would appear once and
// then be replaced by the false one on the reader's next click.
let _unreadable = false;

/** Tell the rail which run is streaming, or that none is.
 *
 *  Called from both ends of a run's life in web/app.js — openStream sets it,
 *  endRun clears it — because a stale value here would send a reader to a live
 *  surface for a run that has already finished, which is the one failure this
 *  is meant to prevent in the other direction. */
export function setLiveRun(runId) {
  _liveRunId = runId;
}

export function setRoomRenderer(fn) {
  _renderRoom = fn;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** Draws the saved-room list from GET /api/rooms's summaries — title, era,
 *  status, created_at, search_count. `room_summary` on the server
 *  deliberately omits the bible and categories, so this is cheap to redraw
 *  on every rail change.
 *
 *  A room's marker is read from its status, not animated: `running` gets
 *  the pencil-coloured marker the brief calls for (nothing spins); `error`
 *  and `interrupted` get the oxide marker, reusing the same "flagged"
 *  meaning the stamp uses elsewhere rather than inventing a third color;
 *  everything else (`complete`, `partial`) gets a plain manila-edge marker
 *  — deliberately not aniline, which is reserved for an actual per-citation
 *  stamp against one checked source (Task 5). A room being "filed" is not a
 *  claim about every source inside it.
 *
 *  `unreadable` is the whole of Task 7's fix round. This function used to take
 *  an empty array from two callers that mean opposite things: a successful
 *  request that returned no rooms, and a request that failed. It printed the
 *  same sentence for both — "Nothing filed yet. Paste a treatment below and the
 *  department gets started." — which is not an empty rail, it is an assertion
 *  that the reader has no saved work, in the department's most inviting voice,
 *  on the one screen where the interface does not know that.
 *
 *  It is the same defect this phase has now caught four times: copy asserting a
 *  fact the code cannot see. `_salvage` returning `any` under a message that
 *  said "all four researchers filed"; a drawer explaining that a run "stopped"
 *  when the payload only proved nothing was filed; and this. refreshRail
 *  already knows which case it is at its two call sites; it just was not
 *  saying. */
export function renderRail(rooms, activeRunId, { unreadable = _unreadable } = {}) {
  _rooms = rooms || [];
  _activeRunId = activeRunId !== undefined ? activeRunId : _activeRunId;
  // Defaulted from the remembered value, not from `false`: only a caller that
  // actually went to the network is entitled to change it, and refreshRail
  // passes it explicitly on every one of its three exits including success.
  _unreadable = unreadable;

  if (_rooms.length === 0) {
    // No apology and no alarm — the department's register holds under a
    // failure the same way it holds under a partial room. It says what
    // happened, what is not being claimed, and what to do. "could not be
    // reached" is the honest scope: the request did not come back, which is
    // not the same as knowing the rooms are gone.
    railList.innerHTML = unreadable
      ? '<p class="rail-empty">Your filed rooms could not be reached just now. They are not lost — reload to try again.</p>'
      : '<p class="rail-empty">Nothing filed yet. Paste a treatment below and the department gets started.</p>';
    return;
  }

  railList.innerHTML = "";
  for (const room of _rooms) {
    const isRunning = room.status === "running";
    const isFlagged = room.status === "error" || room.status === "interrupted";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "rail-room" +
      (room.run_id === _activeRunId ? " active" : "") +
      (isRunning ? " running" : "") +
      (isFlagged ? " flagged" : "");
    btn.dataset.runId = room.run_id;
    btn.setAttribute("aria-current", room.run_id === _activeRunId ? "true" : "false");
    // A run in flight has no title and no era yet, and star/store.py writes the
    // document at creation off an empty story_profile — so the ordinary
    // fallbacks say two false things about it. "Untitled room" claims the
    // department read the treatment and found no title; "Era unstated" claims
    // it looked for a period and found none. Neither has happened. The row says
    // what is actually true instead, in the vocabulary web/app.js already uses
    // for this state ("Still in the department").
    const title = isRunning ? "In the department" : room.title || "Untitled room";
    const meta = isRunning
      ? "Researching now"
      : `${escapeHtml(room.era || "Era unstated")} &middot; ${escapeHtml(formatDate(room.created_at) || "—")}`;
    btn.innerHTML = `
      <span class="rail-room-marker" aria-hidden="true"></span>
      <span class="rail-room-text">
        <span class="rail-room-title">${escapeHtml(title)}</span>
        <span class="rail-room-meta">${isRunning ? escapeHtml(meta) : meta}</span>
      </span>`;
    // A run in flight is not a filed room, and loadRoom would treat it as one:
    // it fetches the room, finds no story_profile yet, and paints the "still in
    // the department" placeholder over a stream that is at that moment writing
    // into the progress panel's hidden DOM. The live surface already exists —
    // showRunning() had two callers and neither was a control, so once a reader
    // opened Your card mid-build there was no way back to their own run.
    btn.addEventListener("click", () => {
      if (_liveRunId !== null && room.run_id === _liveRunId) {
        showRunning();
        return;
      }
      loadRoom(room.run_id);
    });
    railList.appendChild(btn);
  }
}

/** Fetches a saved room and hands it to whatever's registered as the room
 *  renderer. Marks it active in the rail immediately, before the fetch
 *  resolves, so the click reads as responsive rather than waiting on the
 *  network to even acknowledge itself. */
export async function loadRoom(runId) {
  renderRail(_rooms, runId);
  showRoom();
  if (_renderRoom) {
    await _renderRoom(runId);
  }
}

/** Re-fetches the room list and redraws the rail. Called on load, and again
 *  after a build finishes so a freshly filed room appears without a reload.
 *
 *  Never throws — a network hiccup here should read as a rail that says so, not
 *  a stuck page. Both failure paths now pass `unreadable`, which is the only
 *  thing that separates them from a genuinely empty account: a refused request
 *  (web/auth.js retries a 401 once and then surfaces it) and a thrown one are
 *  both "we could not read the list", and neither is "you have no rooms".
 *
 *  A malformed 200 counts as unreadable too. `rooms` missing from the body
 *  reaches renderRail as undefined, which its `rooms || []` turns into the
 *  empty-account sentence — the same false claim by a different door. */
export async function refreshRail(activeRunId) {
  const nextActive = activeRunId !== undefined ? activeRunId : _activeRunId;
  try {
    const res = await authedFetch("/api/rooms");
    if (!res.ok) {
      renderRail([], nextActive, { unreadable: true });
      return;
    }
    const { rooms } = await res.json();
    renderRail(rooms, nextActive, { unreadable: !Array.isArray(rooms) });
  } catch {
    renderRail([], nextActive, { unreadable: true });
  }
}

/** Reveal one panel and hide the rest.
 *
 *  THIS IS THE WHOLE OF WHAT A STAGE STATE IS, and it is why the card can be
 *  opened during a live build without touching it. The EventSource lives in
 *  web/app.js and is never referenced here; a run that is streaming keeps
 *  streaming into #progress-panel's DOM while the panel is hidden, and comes
 *  back exactly as far along as it has got. Nothing in this file closes a
 *  stream, and nothing in it re-fetches a room. */
function stage(panel) {
  // Where the reader was before the card, so they can be put back exactly
  // there. Recorded here rather than at the call sites because this is the one
  // function every stage change passes through, and a second bookkeeping spot
  // is a second thing to forget.
  if (panel !== accountPanel) _lastStageBeforeAccount = panel;
  for (const el of PANELS) el.classList.toggle("hidden", el !== panel);
  // The rail entry carries the selection the way a rail room does, so "which
  // surface am I on" has one answer in one place.
  railFoot.setAttribute("aria-current", panel === accountPanel ? "true" : "false");
  railFoot.classList.toggle("active", panel === accountPanel);
}

export function showIntake() {
  stage(intakePanel);
  _activeRunId = null;
  renderRail(_rooms, null);
}

export function showRunning() {
  stage(progressPanel);
}

export function showRoom() {
  stage(resultsPanel);
}

/** The card — the fourth stage state.
 *
 *  It deliberately does NOT clear `_activeRunId`, the way showIntake does: a
 *  reader who opens the card from an open room and comes back should find the
 *  same room marked in the rail, because they never left it. And it does not
 *  redraw the rail at all, so a build in flight keeps its row exactly as the
 *  stream last left it. */
export function showAccount() {
  stage(accountPanel);
}

/** Back out of the card to whatever the reader was looking at.
 *
 *  A panel swap and nothing else — deliberately not loadRoom(), which would
 *  re-fetch the room and run resetRoomView over a surface the reader never
 *  left. The card is the only stage with no way out of its own, and the rail
 *  was carrying that job: clicking the open room to get back is what made an
 *  unsubmitted scene disposable. */
export function showPreviousStage() {
  stage(_lastStageBeforeAccount || intakePanel);
}
