/* THE MORGUE — the drawer.
   One hanging folder with a cut tab, serving both the live run (Task 4
   routes SSE events into it) and a filed room (Task 6 reads it from
   GET /api/rooms/{id}). Five states share one component so a room never
   re-renders differently depending on how it was reached.

   Built static-first, per docs/design/DIRECTION.md: a drawer that only
   reads correctly while animating is a drawer that fails as a still frame.
   Motion (the stamp press, Task 4) is layered on top of this later; nothing
   here depends on an animation to be legible.

   Color discipline, checked against DIRECTION.md's palette table:
     - --oxide marks the FAILED tab. Same "flagged" meaning shell.js already
       gave it for the rail's error/interrupted marker (web/shell.js).
     - --aniline is NOT used here. DIRECTION.md reserves it for "filed AND
       verified" at the per-citation level — a claim only Task 5 can make,
       once it joins a finding to its ledger check. A drawer being "filed"
       only means this category's research pass completed; some of its
       findings may still carry unverified_urls. Stamping the drawer itself
       aniline would overclaim exactly what research obligation 3 warns
       against, and would collide with Task 2's own precedent (the rail's
       "complete" marker deliberately uses --manila-edge, not --aniline,
       for the same reason). The FILED stamp here is --ink: typographic,
       legible, and makes no verification claim.
     - Search-progress dots use --pencil (metadata), not --aniline — a
       landed search is not a verified fact.
*/

export const DRAWER_LABELS = {
  setting: "Setting & Atmosphere",
  objects_props: "Objects & Props",
  logistics: "Logistics",
  forces_conflicts: "Forces & Conflicts",
};

const VALID_STATES = new Set(["idle", "searching", "filed", "failed", "expanded"]);
const MAX_DOTS = 24; // beyond this, still-frame legibility loses to raw count fidelity

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function renderIdle(body) {
  body.innerHTML = `<p class="drawer-status">Not yet started</p>`;
}

/** SEARCHING: the current objective in --slug beneath the tab, and one dot
 *  per landed search. No total is implied — research obligation 6 ("never
 *  promise a duration") applies just as much to an implied search count as
 *  to a promised finish time, so this is an open-ended tally, not a bar. */
function renderSearching(body, data = {}) {
  const { objective = "", searchCount = 0 } = data;
  const count = Math.max(0, Math.floor(searchCount));
  const shown = Math.min(count, MAX_DOTS);
  const dots = Array.from({ length: shown }, () => '<span class="dot"></span>').join("");
  const overflow = count > shown ? `<span class="dot-overflow">+${count - shown}</span>` : "";
  const objectiveLine = objective
    ? `<p class="drawer-meta drawer-objective">&ldquo;${escapeHtml(objective)}&rdquo;</p>`
    : "";
  body.innerHTML = `
    <p class="drawer-status">Searching</p>
    ${objectiveLine}
    <div class="drawer-dots" aria-label="${plural(count, "search")} landed">${dots}${overflow}</div>
  `;
}

/** FILED: a typographic stamp plus the three counts the plan calls for.
 *  "Filed" only — never "verified". See the module header for why. */
function renderFiled(body, data = {}) {
  const { factCount = 0, sourceCount = 0, questionCount = 0 } = data;
  body.innerHTML = `
    <div class="stamp">Filed</div>
    <p class="drawer-meta drawer-counts">
      ${plural(factCount, "fact")} &middot;
      ${plural(sourceCount, "source")} &middot;
      ${plural(questionCount, "question")}
    </p>
  `;
}

/** FAILED: plain language, no euphemism, and the clip-equivalent of Task 2's
 *  rail precedent — the drawer stays fully visible rather than vanishing. */
function renderFailed(body, data = {}) {
  const message =
    data.message || "The department could not complete research for this category.";
  body.innerHTML = `
    <p class="drawer-status">Did not file</p>
    <p class="drawer-meta">${escapeHtml(message)}</p>
  `;
}

/** Builds one drawer at rest (idle). `category` must be one of the four keys
 *  in DRAWER_LABELS — the same keys `Category` uses server-side
 *  (star/models.py) and the same keys GET /api/rooms/{id}'s
 *  `result.categories` is keyed by. */
export function createDrawer(category) {
  const label = DRAWER_LABELS[category];
  if (!label) {
    throw new Error(`createDrawer: unknown category "${category}"`);
  }
  const el = document.createElement("div");
  el.className = "drawer";
  el.dataset.category = category;
  el.innerHTML = `
    <div class="tab"><span class="tab-label">${escapeHtml(label)}</span></div>
    <div class="drawer-body"></div>
  `;
  setDrawerState(el, "idle");
  return el;
}

/** Repaints one drawer's body for the given state. Safe to call repeatedly
 *  as a live run advances a category through idle -> searching -> filed (or
 *  -> failed); each call fully replaces the body's content, so there is no
 *  stale state left over from a previous call.
 *
 *  "expanded" is a deliberate no-op: Task 5 owns the expanded reading view
 *  (clips, receipts, the onionskin surface) and mounts it here. This state
 *  is accepted so the signature is stable across tasks, but nothing about
 *  its content is decided by this file. */
export function setDrawerState(el, state, data = {}) {
  if (!VALID_STATES.has(state)) {
    throw new Error(`setDrawerState: unknown state "${state}"`);
  }
  el.dataset.state = state;
  const body = el.querySelector(".drawer-body");
  switch (state) {
    case "idle":
      renderIdle(body);
      break;
    case "searching":
      renderSearching(body, data);
      break;
    case "filed":
      renderFiled(body, data);
      break;
    case "failed":
      renderFailed(body, data);
      break;
    case "expanded":
      break;
  }
  return el;
}

/** Convenience for callers that want all four drawers at once, in the fixed
 *  category order the 2x2 grid always uses. Each starts idle; callers drive
 *  state from there via setDrawerState. */
export function createDrawerGrid() {
  const grid = document.createElement("div");
  grid.className = "drawer-grid";
  for (const category of Object.keys(DRAWER_LABELS)) {
    grid.appendChild(createDrawer(category));
  }
  return grid;
}
