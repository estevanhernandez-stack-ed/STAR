/* THE MORGUE — the cabinet shell.
   Owns the rail of saved rooms and which panel the stage shows. It does not
   know what a filed room looks like once it's open — that's the drawer and
   clip components landing in Tasks 3-5. app.js registers the function that
   turns a run_id into stage content via setRoomRenderer(); this file only
   ever calls it by name.
*/

import { authedFetch } from "/auth.js";

const $ = (id) => document.getElementById(id);

const railList = $("rail-list");
const intakePanel = $("intake-panel");
const progressPanel = $("progress-panel");
const resultsPanel = $("results-panel");

let _rooms = [];
let _activeRunId = null;
let _renderRoom = null; // (runId) => Promise<void> | void
// Did the last attempt to READ the list fail? Remembered rather than passed,
// because showIntake() and loadRoom() redraw the rail from this cache without
// going near the network — and an empty `_rooms` means two different things
// depending on this flag. Without it the honest sentence would appear once and
// then be replaced by the false one on the reader's next click.
let _unreadable = false;

/** Register the function that paints a loaded room onto the stage. */
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
    btn.innerHTML = `
      <span class="rail-room-marker" aria-hidden="true"></span>
      <span class="rail-room-text">
        <span class="rail-room-title">${escapeHtml(room.title || "Untitled room")}</span>
        <span class="rail-room-meta">${escapeHtml(room.era || "Era unstated")} &middot; ${escapeHtml(formatDate(room.created_at) || "—")}</span>
      </span>`;
    btn.addEventListener("click", () => loadRoom(room.run_id));
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

export function showIntake() {
  intakePanel.classList.remove("hidden");
  progressPanel.classList.add("hidden");
  resultsPanel.classList.add("hidden");
  _activeRunId = null;
  renderRail(_rooms, null);
}

export function showRunning() {
  intakePanel.classList.add("hidden");
  progressPanel.classList.remove("hidden");
  resultsPanel.classList.add("hidden");
}

export function showRoom() {
  intakePanel.classList.add("hidden");
  progressPanel.classList.add("hidden");
  resultsPanel.classList.remove("hidden");
}
