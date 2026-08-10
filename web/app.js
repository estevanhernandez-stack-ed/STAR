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

import { authedFetch, getIdToken } from "/auth.js";
import {
  showIntake,
  showRunning,
  showRoom,
  refreshRail,
  setRoomRenderer,
} from "/shell.js";
import {
  DRAWER_LABELS,
  createDrawerGrid,
  setDrawerState,
  tickDrawerClocks,
} from "/drawer.js";

const $ = (id) => document.getElementById(id);

const timeline = $("timeline");
const progressPanel = $("progress-panel");

// The room view's fixed furniture. index.html ships all four and this file
// only ever replaces their CONTENTS, never the nodes themselves, so a
// reference taken once at module load cannot go stale.
const roomGrid = $("room-grid");
const bibleSurface = $("bible-surface");
const bibleBtn = $("bible-btn");
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
let runStartedAt = null;

$("build-btn").addEventListener("click", buildRoom);
$("new-room-btn").addEventListener("click", () => {
  showIntake();
  resetProgress();
  $("treatment").value = "";
  $("intake-error").textContent = "";
  $("build-btn").disabled = false;
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
  setBibleOpen(bibleBtn.getAttribute("aria-expanded") !== "true");
});

function setBibleOpen(open) {
  bibleBtn.setAttribute("aria-expanded", open ? "true" : "false");
  bibleBtn.textContent = open ? "Back to the drawers" : "The bible";
  bibleSurface.classList.toggle("hidden", !open);
  roomGrid.classList.toggle("hidden", open);
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

/** DD MON YYYY, matching the stamp's slug-face convention in
 *  docs/design/visual-directions.md's own mockup ("RET 09 AUG 2026"). Called
 *  with no argument during a live run, where the retrieval genuinely just
 *  happened, so client "now" and server "now" differ by network latency only
 *  and not by anything worth reconciling. */
function stampDate(d = new Date()) {
  return `${pad2(d.getDate())} ${d.toLocaleString("en-US", { month: "short" }).toUpperCase()} ${d.getFullYear()}`;
}

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
function roomDate(createdAt) {
  if (!createdAt) return "";
  const parsed = new Date(createdAt);
  return Number.isNaN(parsed.getTime()) ? "" : stampDate(parsed);
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
  // One interval drives both clocks, so a drawer's "last search N ago" can
  // never disagree with the run meter beside it, and both stop the moment
  // the run does.
  tickDrawerClocks(progressPanel);
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
function resetRoomView() {
  setBibleOpen(false);
  bibleBtn.classList.add("hidden");
  bibleSurface.innerHTML = "";
  roomGrid.replaceChildren();
  docketBody.innerHTML = "";
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
  resetRoomView();

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
    docketBody.innerHTML = `<p class="docket-note">${escapeHtml(copy[1])}</p>`;
    return;
  }

  paintRoom(result, status);
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
  docketBody.innerHTML = renderDocket(profile, status);

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
}

/** Counts and provenance, in the slug face. Source count is the ledger's own
 *  size (star/server.py sends `len(run["ledger"])`), so it is sources SEEN, not
 *  sources cited — worth saying plainly rather than letting "106 sources" imply
 *  106 footnotes. Each piece is dropped rather than defaulted when it is
 *  missing: "? cited web searches" was a shrug printed where a number belongs. */
function statsLine(result, filed) {
  const parts = [];
  // typeof, not Number(): `Number(null)` is 0, and a room whose count never
  // reached the client would have printed a confident "0 cited web searches"
  // for a run that ran seventeen.
  if (typeof result.search_count === "number") {
    parts.push(plural(result.search_count, "cited web search"));
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
function renderDocket(profile, status) {
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
    ${status === "partial" ? partialDocketNote() : ""}
    ${slug ? `<p class="docket-slug">${slug}</p>` : ""}
    ${
      profile.logline
        ? `<p class="docket-logline">${escapeHtml(profile.logline)}</p>`
        : ""
    }
    ${row("Locations", chips(profile.locations))}
  `;
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
    setOpen(el.dataset.state !== "expanded");
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
      <div class="bible-body">${bibleHtml(markdown)}</div>`;
  }
  const { heading, body } = noBibleCopy(status, result.categories);
  return `
    <h3 class="bible-heading">${heading}</h3>
    ${body.map((line) => `<p class="bible-note">${line}</p>`).join("")}`;
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
