/* STAR frontend — build a room, watch it happen, read the bible. */

import { authedFetch, getIdToken } from "/auth.js";

const $ = (id) => document.getElementById(id);

const intakePanel = $("intake-panel");
const progressPanel = $("progress-panel");
const resultsPanel = $("results-panel");
const timeline = $("timeline");

let searchCount = 0;

$("build-btn").addEventListener("click", buildRoom);
$("new-room-btn").addEventListener("click", () => {
  resultsPanel.classList.add("hidden");
  intakePanel.classList.remove("hidden");
  timeline.innerHTML = "";
  searchCount = 0;
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

  intakePanel.classList.add("hidden");
  progressPanel.classList.remove("hidden");
  addEntry("done", "Treatment received. The department is assembling.");

  const source = new EventSource(`/api/rooms/${runId}/events`);
  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.type === "search") {
      searchCount += 1;
      const obj = ev.objective
        ? `<div class="obj">&ldquo;${escapeHtml(truncate(ev.objective, 160))}&rdquo;</div>`
        : "";
      addEntry("search", `<span class="who">${escapeHtml(ev.agent)}</span> is searching the live web${obj}`);
      $("search-meter").textContent = `${searchCount} cited searches so far (Parallel Search API)`;
    } else if (ev.type === "agent_done") {
      addEntry("done", `<span class="who">${escapeHtml(ev.agent)}</span> filed their work.`);
    } else if (ev.type === "complete") {
      source.close();
      showResults(runId, ev.search_count);
    } else if (ev.type === "partial") {
      // The editor ran out of time, but the researchers did not. Their
      // findings and citations are real and already paid for, so show them
      // rather than throwing away a four-minute build.
      source.close();
      addEntry("warn", escapeHtml(ev.message));
      showResults(runId, ev.search_count, ev.message);
    } else if (ev.type === "error") {
      source.close();
      addEntry("error", `Something broke: ${escapeHtml(ev.message)}`);
      $("build-btn").disabled = false;
    }
  };
  source.onerror = () => {
    /* stream closes naturally on completion; ignore */
  };
}

async function showResults(runId, count, partialNote) {
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
    progressPanel.classList.add("hidden");
    intakePanel.classList.remove("hidden");
    $("intake-error").textContent = `Could not load your results: ${detail}`;
    $("build-btn").disabled = false;
    return;
  }
  const { result } = await res.json();

  progressPanel.classList.add("hidden");
  resultsPanel.classList.remove("hidden");
  $("build-btn").disabled = false;

  const profile = result.story_profile || {};
  $("result-title").textContent = profile.title || "Your research room";
  $("result-stats").textContent = `${count ?? result.search_count ?? "?"} cited web searches`;

  // The bible is synthesized from live web content — an adversarial data
  // path. Render it only through DOMPurify; if either library failed to
  // load, fall back to escaped plain text rather than raw HTML.
  const bibleMd =
    result.research_bible ||
    (partialNote
      ? `_${partialNote}_`
      : "_No bible produced._");
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

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
