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
 *  verified stamp (Task 5). A room being "filed" is not a claim that
 *  everything in it was verified. */
export function renderRail(rooms, activeRunId) {
  _rooms = rooms || [];
  _activeRunId = activeRunId !== undefined ? activeRunId : _activeRunId;

  if (_rooms.length === 0) {
    railList.innerHTML =
      '<p class="rail-empty">Nothing filed yet. Paste a treatment below and the department gets started.</p>';
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
 *  Never throws — a network hiccup here should read as an empty rail, not a
 *  stuck page. */
export async function refreshRail(activeRunId) {
  const nextActive = activeRunId !== undefined ? activeRunId : _activeRunId;
  try {
    const res = await authedFetch("/api/rooms");
    if (!res.ok) {
      renderRail([], nextActive);
      return;
    }
    const { rooms } = await res.json();
    renderRail(rooms, nextActive);
  } catch {
    renderRail([], nextActive);
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
