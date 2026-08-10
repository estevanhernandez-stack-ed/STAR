/* STAR frontend — build a room, watch it happen, read the bible.

   The stage's state (intake / running / room) and the rail of saved rooms
   belong to shell.js. This file owns starting a build, streaming its
   progress, and painting a room's content once it's open — the tab-based
   render below is the seam Task 5/6 replace with drawers and a dedicated
   bible surface for the FILED room; the live RUNNING view is this task's
   own seam, and it now routes into web/drawer.js's four-drawer grid
   instead of the plain timeline that used to be the only feedback.

   Research obligation 6 (never promise a duration) governs everything in
   the SSE handler below: no ETA, no progress bar implying completion.
   Elapsed time is shown because it is a fact about the past, not a claim
   about the future — see elapsedLabel().
*/

import { authedFetch, getIdToken } from "/auth.js";
import {
  showIntake,
  showRunning,
  showRoom,
  refreshRail,
  setRoomRenderer,
} from "/shell.js";
import { createDrawerGrid, setDrawerState } from "/drawer.js";

const $ = (id) => document.getElementById(id);

const timeline = $("timeline");
const progressPanel = $("progress-panel");

let searchCount = 0;

// SSE "agent_done" (star/server.py) carries only the friendly agent label
// its own _FRIENDLY dict assigns each author — unlike "search" events, it
// never carries `category`. Category has to be recovered client-side from
// the same four labels _FRIENDLY gives the researcher authors. There is no
// shared source of truth across the Python/JS boundary for this map; keep
// it in sync with star/server.py's _FRIENDLY by hand if either changes.
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
let runStartedAt = null;

$("build-btn").addEventListener("click", buildRoom);
$("new-room-btn").addEventListener("click", () => {
  showIntake();
  resetProgress();
  $("treatment").value = "";
  $("intake-error").textContent = "";
  $("build-btn").disabled = false;
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));
    tab.classList.add("active");
    $("tab-" + tab.dataset.tab).classList.remove("hidden");
  });
});

function addEntry(cls, html) {
  const li = document.createElement("li");
  li.className = cls;
  li.innerHTML = html;
  timeline.appendChild(li);
  li.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** DD MON YYYY, matching the stamp's slug-face convention in
 *  docs/design/visual-directions.md's own mockup ("RET 09 AUG 2026"). Uses
 *  the browser's local clock — for a live run the retrieval genuinely just
 *  happened, so client "now" and server "now" differ by network latency
 *  only, not by anything worth reconciling. */
function stampDate(d = new Date()) {
  return `${pad2(d.getDate())} ${d.toLocaleString("en-US", { month: "short" }).toUpperCase()} ${d.getFullYear()}`;
}

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

function updateMeter() {
  $("search-meter").textContent = `${searchCount} cited searches so far · ${elapsedLabel()}`;
}

function startElapsedTimer() {
  runStartedAt = Date.now();
  updateMeter();
  elapsedTimer = setInterval(updateMeter, 1000);
}

function stopElapsedTimer() {
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = null;
}

/** Rebuilds the live drawer grid and clears every piece of per-run state.
 *  Called at the top of every build, and again on "New room" — the error
 *  path below never navigates away on its own (the rail's own "New room"
 *  button is the recovery path, always visible), so a stray interval or a
 *  stale drawer reference must not survive into whatever the user does
 *  next. */
function resetProgress() {
  stopElapsedTimer();
  timeline.innerHTML = "";
  $("search-meter").textContent = "";
  searchCount = 0;
  filedCategories = new Set();
  categorySearch = new Map();
  const grid = createDrawerGrid();
  drawerEls = new Map([...grid.children].map((el) => [el.dataset.category, el]));
  const oldGrid = progressPanel.querySelector(".drawer-grid");
  if (oldGrid) {
    oldGrid.replaceWith(grid);
  } else {
    progressPanel.insertBefore(grid, timeline);
  }
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
    $("auth-error").classList.remove("hidden");
    $("build-btn").disabled = false;
    return;
  }
  $("auth-error").classList.add("hidden");

  let runId;
  try {
    const res = await authedFetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ treatment }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    runId = (await res.json()).run_id;
  } catch (err) {
    $("intake-error").textContent = err.message;
    $("build-btn").disabled = false;
    return;
  }

  resetProgress();
  showRunning();
  startElapsedTimer();
  addEntry("done", "Treatment received. The department is assembling.");

  const source = new EventSource(`/api/rooms/${runId}/events`);
  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.type === "search") {
      searchCount += 1;
      const category = ev.category;
      if (category && drawerEls.has(category)) {
        const s = categorySearch.get(category) || { objective: "", count: 0 };
        s.count += 1;
        if (ev.objective) s.objective = ev.objective;
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
            objective: s.objective,
            searchCount: s.count,
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
          const s = categorySearch.get(category) || { count: 0 };
          setDrawerState(drawerEls.get(category), "filed", {
            code: CATEGORY_CODE[category],
            date: stampDate(),
            searchCount: s.count,
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
      stopElapsedTimer();
      sweepUnfiledDrawers();
      source.close();
      showResults(runId);
      refreshRail(runId);
    } else if (ev.type === "partial") {
      // The editor ran out of time, but the researchers did not. Their
      // findings and citations are real and already paid for, so show them
      // rather than throwing away a four-minute build.
      stopElapsedTimer();
      sweepUnfiledDrawers();
      source.close();
      addEntry("warn", escapeHtml(ev.message));
      showResults(runId);
      refreshRail(runId);
    } else if (ev.type === "error") {
      stopElapsedTimer();
      sweepUnfiledDrawers();
      source.close();
      addEntry("error", `Something broke: ${escapeHtml(ev.message)}`);
      $("build-btn").disabled = false;
    }
  };
  source.onerror = () => {
    /* stream closes naturally on completion; ignore */
  };
}

/** Fetches one room and paints it into the results panel. This is the seam
 *  Task 3's drawer component replaces — both the live-build "complete"
 *  handler above and shell.js's loadRoom() (a rail click) call this same
 *  function, so a saved room and a just-finished one render identically. */
async function showResults(runId) {
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
      running: [
        "Still in the department",
        "This room is still being researched. Reconnecting to a live run isn't available yet — check back once it's filed.",
      ],
      interrupted: [
        "Interrupted before it filed",
        "This run did not finish — the server restarted before any research was filed. Start a new room instead.",
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
    $("result-stats").textContent = "";
    $("tab-bible").innerHTML = `<p>${escapeHtml(copy[1])}</p>`;
    $("tab-profile").innerHTML = "";
    $("tab-plan").innerHTML = "";
    return;
  }

  const profile = result.story_profile || {};
  $("result-title").textContent = profile.title || "Your research room";
  $("result-stats").textContent = `${result.search_count ?? "?"} cited web searches`;

  // The bible is synthesized from live web content — an adversarial data
  // path. Render it only through DOMPurify; if either library failed to
  // load, fall back to escaped plain text rather than raw HTML.
  const bibleMd = result.research_bible || "_No bible produced yet for this room._";
  if (window.marked && window.DOMPurify) {
    $("tab-bible").innerHTML = DOMPurify.sanitize(marked.parse(bibleMd));
  } else {
    $("tab-bible").innerHTML = `<pre>${escapeHtml(bibleMd)}</pre>`;
  }
  makeLinksSafe($("tab-bible"));

  $("tab-profile").innerHTML = renderProfile(profile);
  $("tab-plan").innerHTML = renderPlan(result.research_plan || {});
}

function renderProfile(p) {
  const chips = (arr) => (arr || []).map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join("");
  return `
    <div class="kv"><div class="k">Logline</div>${escapeHtml(p.logline || "—")}</div>
    <div class="kv"><div class="k">Era</div>${escapeHtml(p.era || "—")}</div>
    <div class="kv"><div class="k">Genre</div>${escapeHtml(p.genre || "—")}</div>
    <div class="kv"><div class="k">Locations</div>${chips(p.locations)}</div>
    <div class="kv"><div class="k">Needs grounding</div>${chips(p.key_entities)}</div>`;
}

function renderPlan(plan) {
  const qs = plan.questions || [];
  if (!qs.length) return "_No plan captured._";
  return qs
    .map(
      (q) => `
      <div class="q">
        <div class="cat">${escapeHtml(String(q.category).replace("_", " & "))}</div>
        <div>${escapeHtml(q.question)}</div>
        <div class="why">${escapeHtml(q.why || "")}</div>
      </div>`
    )
    .join("");
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

// Wire the shell to this file's room renderer, then sign in and populate
// the rail. A failed sign-in shows the same banner buildRoom's own check
// would show later — no reason to wait for a build attempt to learn the
// department can't be reached at all.
setRoomRenderer(showResults);

(async function init() {
  let token;
  try {
    token = await getIdToken();
  } catch {
    token = null;
  }
  if (!token) {
    $("auth-error").classList.remove("hidden");
    return;
  }
  await refreshRail();
})();
