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
     - --aniline is still not used by THIS file, in any state including
       expanded. DIRECTION.md's "signature" stamp (domain, retrieval date,
       researcher's code, in --aniline) is specified at the per-CITATION
       level: it fires "when the ledger check passes" against one Finding's
       citations. No drawer state has a citation to check — a drawer is a
       container for clips, and the check happens inside one. Task 4's
       live-run FILED transition knows even less: `agent_done`
       (star/server.py) carries only the friendly agent label, never a URL
       or a fact. Stamping the DRAWER aniline would claim a verification
       this component cannot see, exactly what research obligation 3 warns
       against — so it stays Task 3's --ink, extended rather than reversed.
       What Task 4 legitimately DOES know at the moment a category files:
       which researcher (the category, encoded as a three-letter code) and
       when (today, genuinely — the render happens as the event arrives).
       Both are on the stamp; no domain is fabricated to fill the third
       slot the citation-level design calls for. Task 5 spends the aniline
       pad where it belongs, in web/clip.js's receipt stamp.
     - Search-progress dots use --pencil (metadata), not --aniline — a
       landed search is not a verified fact.
*/

import {
  countSources,
  escapeHtml,
  plural,
  questionsForCategory,
  renderClips,
  renderFieldNotes,
  renderSceneNeeds,
  renderUncertainty,
} from "/clip.js";

export const DRAWER_LABELS = {
  setting: "Setting & Atmosphere",
  objects_props: "Objects & Props",
  logistics: "Logistics",
  forces_conflicts: "Forces & Conflicts",
};

const VALID_STATES = new Set(["idle", "searching", "filed", "failed", "expanded"]);

/* escapeHtml and plural moved to web/clip.js in Task 5 and are imported above.
 * Both files need them, and clip.js is the leaf (it imports nothing), so
 * putting them there is the only arrangement that shares one implementation
 * without a module cycle. plural's history is worth keeping in view from here:
 * naive "+s" produced "searchs", a bug this file shipped twice. */

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

/** How long ago the newest search landed, as M:SS — the same shape the run
 *  meter uses, so the two clocks on screen read as the same kind of number.
 *  A future or nonsense `since` clamps to 0:00 rather than rendering a
 *  negative age. */
function ageText(since, now) {
  const secs = Math.max(0, Math.floor((now - since) / 1000));
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

/** Re-times every visible search clock under `root`. Called once a second by
 *  the same interval that drives the run meter (web/app.js) rather than by a
 *  timer of its own — one clock source, and it stops when the run stops.
 *
 *  Rewrites one span's text instead of re-rendering the drawer: a full
 *  re-render every second would drop the user's text selection mid-read, and
 *  these cards are full of URLs and quotes worth selecting. The timestamp
 *  lives on the element as a data attribute so it survives whatever the last
 *  render wrote. */
export function tickDrawerClocks(root, now = Date.now()) {
  for (const el of root.querySelectorAll(".search-age[data-since]")) {
    const since = Number(el.dataset.since);
    if (Number.isFinite(since)) {
      el.textContent = ` · last search ${ageText(since, now)} ago`;
    }
  }
}

function renderSearching(body, data = {}) {
  const searches = Array.isArray(data.searches) ? data.searches : [];
  const log = buildSearchLog(searches, { withQueries: true });
  // A stalled researcher and a working one look identical without this: the
  // card sits on "Searching" either way, and nothing resolves it until the
  // run ends and sweepUnfiledDrawers (web/app.js) marks the stragglers.
  //
  // Deliberately a number and not a warning state. We have no honest
  // threshold for "stuck" — a researcher can legitimately go a long while
  // between calls while the model reasons — so this states the fact and
  // lets the reader judge, rather than inventing a cutoff and crying wolf
  // at an agent that was working the whole time. Same discipline as the run
  // meter: it counts up from what already happened and predicts nothing.
  const newest = searches[searches.length - 1];
  const since = Number(newest?.at);
  const age = Number.isFinite(since)
    ? `<span class="search-age" data-since="${since}"> &middot; last search ${ageText(since, Date.now())} ago</span>`
    : "";
  const tally = searches.length
    ? `<p class="drawer-meta drawer-counts">${plural(searches.length, "search")} landed${age}</p>`
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
function buildFiledHead(data = {}) {
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
  return `
    <div class="stamp">
      <span class="stamp-word">Filed</span>
      ${stampDetail}
    </div>
    ${countsLine ? `<p class="drawer-meta drawer-counts">${countsLine}</p>` : ""}
  `;
}

/** The log of what this researcher asked, labelled. A filed or expanded room
 *  reached from the rail never watched these questions being issued, and
 *  without the label a bare list of quotes under a FILED stamp reads as
 *  findings, which they are not. */
function buildLabelledLog(data = {}) {
  const searches = Array.isArray(data.searches) ? data.searches : [];
  const log = buildSearchLog(searches, { withQueries: false });
  return log ? `<p class="drawer-legend">What this researcher asked</p>${log}` : "";
}

function renderFiled(body, data = {}) {
  // The log is carried over from the searching state so the card does not
  // empty at the moment it succeeds.
  body.innerHTML = `
    ${buildFiledHead(data)}
    ${buildLabelledLog(data)}
  `;
}

/** EXPANDED: the reading view. The same filed card, with its clips opened out.
 *
 *  Additive by construction, and that is the whole design of this state: the
 *  stamp, the counts, and the log of what this researcher asked all survive
 *  underneath the clips. Task 4 learned this the expensive way in the other
 *  direction — its first cut of FILED rendered a stamp alone and read on
 *  screen as the drawer throwing away everything it had just shown you.
 *  Opening a drawer must not do that either.
 *
 *  Reading order is an argument, not a layout preference:
 *    1. the stamp and the counts — what this drawer is
 *    2. what the department could not do cleanly — the uncertainty numbers,
 *       BEFORE the findings rather than in a footnote after them. Burying
 *       them under the good news would be the sycophancy the aversion
 *       research names as the actual harm.
 *    3. what these findings are for — the scene needs, so every clip below is
 *       read under the question it was gathered to answer
 *    4. the clips
 *    5. the lines the parser could not file, verbatim
 *    6. the searches that produced all of it
 *
 *  Counts are computed here rather than trusted from the caller, because in
 *  this state they are derivable from the payload and a derived number cannot
 *  drift from what is on screen. `sourceCount` counts DISTINCT resolved URLs
 *  (see clip.js's countSources) — the stored Detroit-1929 room cites one
 *  museum page on five separate logistics findings, and summing citations
 *  would inflate it to five sources.
 *
 *  `date` and `retrieved` are two different factual claims and are two
 *  different fields, deliberately:
 *    - `date` is the FILED stamp's date, which is what buildFiledHead renders.
 *    - `retrieved` is the day these sources actually came back from a search,
 *      which is what clip.js prints as `RET <date>` on every receipt.
 *  They are the same value during a live run and only during a live run: the
 *  render happens as the agent_done event arrives, so web/app.js's client
 *  "now" is genuinely both. They come apart the moment a stored room is opened
 *  from the rail — a room built on 09 AUG and read in September would stamp
 *  every source `RET 09 SEP` if this reused the convenience value. That is a
 *  fabricated provenance claim on the exact element whose whole job is
 *  provenance, so `retrieved` is never defaulted from `date`. A caller that
 *  does not supply it gets a stamp with no RET line, the same way renderFiled
 *  refuses to fabricate a domain for the third slot.
 *
 *  Task 6: the real value is the room document's `created_at`
 *  (star/store.py) — an ISO string, so format it the way web/app.js's
 *  stampDate() does (DD MON YYYY) before passing it. */
function renderExpanded(body, data = {}, category = "") {
  const doc = data.doc || {};
  const findings = Array.isArray(doc.findings) ? doc.findings : [];
  const questions = questionsForCategory(data.plan, category);
  const stamp = { date: data.retrieved, code: data.code };
  // Rendered once and reused, so the empty-clips copy can promise prose only
  // when there is prose. Asking the payload instead of the markup is how the
  // two get to disagree.
  const fieldNotes = renderFieldNotes(doc);
  body.innerHTML = `
    ${buildFiledHead({
      ...data,
      factCount: findings.length,
      sourceCount: countSources(findings),
      questionCount: questions.length,
    })}
    ${renderUncertainty(doc)}
    ${renderSceneNeeds(questions)}
    <p class="drawer-legend">What was found</p>
    ${renderClips(findings, stamp, { hasFieldNotes: Boolean(fieldNotes) })}
    ${fieldNotes}
    ${buildLabelledLog(data)}
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
    <div class="drawer-tab"><span class="drawer-tab-label">${escapeHtml(label)}</span></div>
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
 *  "expanded" takes the same payload shape as the others plus `doc` (one
 *  category's ResearchDoc out of GET /api/rooms/{id}), `plan`
 *  (result.research_plan, or its questions array), and `retrieved` (the day
 *  the sources came back, distinct from the filed `date` — see
 *  renderExpanded). It reads the category off the element rather than the
 *  payload so the per-category scene-need join can never be pointed at the
 *  wrong drawer's questions. */
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
      renderExpanded(body, data, el.dataset.category);
      break;
  }
  return el;
}

/** Open one drawer into its reading view.
 *
 *  Takes the element rather than a category name so it composes with whatever
 *  the mounting task already holds — createDrawerGrid hands back four of these
 *  and web/app.js already keeps them in a Map. `doc` is one entry of the room
 *  payload's `categories`; `plan` is `result.research_plan`. `extra` carries
 *  only the fields a caller genuinely knows:
 *    { code, date, retrieved, searches }
 *  — `date` stamps FILED, `retrieved` stamps RET on each receipt, and they are
 *  not interchangeable. See renderExpanded.
 *
 *  A thin wrapper over setDrawerState on purpose — every state a drawer can
 *  reach goes through one function, so nothing can leave the element's
 *  data-state disagreeing with what its body actually shows. */
export function expandDrawer(el, doc, plan, extra = {}) {
  return setDrawerState(el, "expanded", { ...extra, doc, plan });
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
