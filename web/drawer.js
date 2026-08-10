/* THE MORGUE — the drawer.
   One hanging folder with a cut tab, serving both the live run (Task 4
   routes SSE events into it) and a filed room (Task 6 reads it from
   GET /api/rooms/{id}). Five states share one component so a room never
   re-renders differently depending on how it was reached.

   Built static-first, per docs/design/DIRECTION.md: a drawer that only
   reads correctly while animating is a drawer that fails as a still frame.
   Task 4 layers the stamp's press animation on top (--stamp-duration,
   0ms under prefers-reduced-motion) without changing what any state reads
   as a frozen frame — the animation is not load-bearing for legibility.

   Color discipline, checked against DIRECTION.md's palette table:
     - --oxide marks the FAILED tab. Same "flagged" meaning shell.js already
       gave it for the rail's error/interrupted marker (web/shell.js).
     - --aniline is NOT used here, still. DIRECTION.md's "signature" stamp
       (domain, retrieval date, researcher's code, in --aniline) is
       specified at the per-CITATION level: it fires "when the ledger check
       passes" against one Finding's citations. Task 4's own live-run
       consumer of this file — the drawer's FILED transition — has no
       citation to check. `agent_done` (star/server.py) carries only the
       friendly agent label, never a URL or a fact; the domain and
       fact/source/question counts a filed category eventually carries only
       exist once GET /api/rooms/{id} is fetched and parsed, which is
       Task 5's territory (findings, citations, the ledger check). Stamping
       the DRAWER aniline here would claim a verification this component
       still cannot see, exactly what research obligation 3 warns against —
       so this stays Task 3's --ink, extended rather than reversed. What
       Task 4 legitimately DOES know at the moment a category files: which
       researcher (the category itself, encoded as a three-letter code) and
       when (today, genuinely — the render happens the moment the event
       arrives). Both are now on the stamp; no domain is fabricated to fill
       the third slot the citation-level design calls for. See renderFiled
       below and drawer.css's .stamp rule for the full reasoning.
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

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/* Naive "+s" breaks on "search" ("searchs") — a real bug this file already
 * had (Task 3's aria-label on the dot row), surfaced while testing Task 4's
 * new "N searches completed" stamp line, which hits the exact same word.
 * Standard English pluralization for words ending in a sibilant sound
 * takes "+es", not "+s". */
function plural(n, word) {
  if (n === 1) return `${n} ${word}`;
  const suffix = /(?:[sxz]|[cs]h)$/i.test(word) ? "es" : "s";
  return `${n} ${word}${suffix}`;
}

function renderIdle(body) {
  body.innerHTML = `<p class="drawer-status">Not yet started</p>`;
}

/** SEARCHING: the running log of what this researcher has actually asked.
 *
 *  Task 3 shipped this state as one objective line plus a row of anonymous
 *  dots, one per landed search. A live run killed that design: the dots left
 *  a 265px card holding about 55px of content for the ~80 seconds a build
 *  spends in this state, which is most of what anyone watching ever sees.
 *  Worse, a grey dot is the weakest possible claim — it asserts that work
 *  happened without showing any of it, which is exactly the register this
 *  whole direction exists to avoid.
 *
 *  What replaces it is strictly more honest, not just fuller: every objective
 *  the researcher has issued, in order, and the literal query strings of the
 *  one in flight (star/server.py forwards `search_queries` off the tool call
 *  for this). Those strings went over the wire to Parallel Search verbatim.
 *  Showing them is the cheapest proof available that the search is real, and
 *  it is available while the run is still going rather than only after.
 *
 *  Only the newest entry shows its queries — earlier ones collapse to their
 *  objective. That keeps the card's height bounded as a category runs 2-6
 *  calls, and it reads correctly: here is everything asked, here is exactly
 *  what is being searched right now.
 *
 *  Still no total and still no bar — research obligation 6 ("never promise a
 *  duration") applies to an implied search count as much as to a promised
 *  finish time. The tally counts up from what already happened.
 *
 *  `searches` is [{ objective, queries }], oldest first.
 *
 *  Shared with FILED below, which shows the same log with the queries left
 *  off. Both states drawing from one builder is what stops a card from
 *  emptying out at the moment it succeeds: the searching card fills with the
 *  work, and filing adds a stamp to it rather than replacing it. The first
 *  cut of this had FILED render a stamp alone, which read on screen as the
 *  drawer throwing away everything it had just shown you.
 *
 *  `withQueries` marks the newest entry current and prints its query strings;
 *  a filed category has no call in flight, so it passes false. */
function buildSearchLog(searches, { withQueries }) {
  const entries = searches
    .map((search, i) => {
      const objective = String(search?.objective || "").trim();
      const isNewest = withQueries && i === searches.length - 1;
      const queries = isNewest && Array.isArray(search?.queries) ? search.queries : [];
      const queryList = queries.length
        ? `<ul class="search-queries">${queries
            .map((q) => `<li>${escapeHtml(q)}</li>`)
            .join("")}</ul>`
        : "";
      // A call whose objective came through empty still happened, and its
      // queries may not have. Drop the entry entirely rather than render a
      // pair of empty quotes.
      if (!objective && !queryList) return "";
      const objectiveLine = objective
        ? `<p class="search-objective">&ldquo;${escapeHtml(objective)}&rdquo;</p>`
        : "";
      return `<li class="search-entry"${isNewest ? ' data-current="true"' : ""}>${objectiveLine}${queryList}</li>`;
    })
    .join("");
  return entries
    ? `<ol class="search-log" aria-label="Searches this researcher issued">${entries}</ol>`
    : "";
}

function renderSearching(body, data = {}) {
  const searches = Array.isArray(data.searches) ? data.searches : [];
  const log = buildSearchLog(searches, { withQueries: true });
  const tally = searches.length
    ? `<p class="drawer-meta drawer-counts">${plural(searches.length, "search")} landed</p>`
    : "";
  body.innerHTML = `
    <p class="drawer-status">Searching</p>
    ${log}
    ${tally}
  `;
}

/** FILED: a typographic stamp plus whatever tally is honestly known the
 *  moment it lands. "Filed" only — never "verified". See the module header
 *  for why, and for why the stamp stays --ink rather than --aniline.
 *
 *  Two callers, two honest payload shapes — never guess between them by
 *  defaulting a missing number to 0, which would silently turn "not known
 *  yet" into a false "zero":
 *    - The live run (web/app.js) calls this the instant a category's
 *      agent_done event fires. It knows the researcher's `code` and
 *      today's `date` (the stamp itself), and `searchCount` (how many
 *      searches that category ran) — it does NOT know fact/source/question
 *      counts, because findings are not parsed until the room is fetched.
 *    - A filed room (GET /api/rooms/{id}, Task 5) calls this with real
 *      `factCount`/`sourceCount`/`questionCount`.
 *  Presence of any of the three finding counts (even 0 — a category can
 *  legitimately file with zero facts) selects the finding-count line;
 *  otherwise the honest fallback is the search tally, never a fabricated
 *  zero. */
function renderFiled(body, data = {}) {
  const { factCount, sourceCount, questionCount, code, date, searchCount } = data;
  const hasFindingCounts =
    factCount !== undefined || sourceCount !== undefined || questionCount !== undefined;
  const stampDetail =
    code && date
      ? `<span class="stamp-slug">${escapeHtml(code)} &middot; ${escapeHtml(date)}</span>`
      : "";
  const countsLine = hasFindingCounts
    ? `${plural(factCount ?? 0, "fact")} &middot;
       ${plural(sourceCount ?? 0, "source")} &middot;
       ${plural(questionCount ?? 0, "question")}`
    : searchCount !== undefined
      ? `${plural(searchCount, "search")} completed`
      : "";
  // Carried over from the searching state so the card does not empty at the
  // moment it succeeds. Labelled, because a filed room reached from the rail
  // never saw these questions being asked — without the label a bare list of
  // quotes under a FILED stamp reads as findings, which they are not.
  const searches = Array.isArray(data.searches) ? data.searches : [];
  const log = buildSearchLog(searches, { withQueries: false });
  body.innerHTML = `
    <div class="stamp">
      <span class="stamp-word">Filed</span>
      ${stampDetail}
    </div>
    ${countsLine ? `<p class="drawer-meta drawer-counts">${countsLine}</p>` : ""}
    ${log ? `<p class="drawer-legend">What this researcher asked</p>${log}` : ""}
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
