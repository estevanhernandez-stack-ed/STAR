/* THE SWEEP REPORT, fetched and drawn.
 *
 *  Reads `?run=<run_id>&sweep=<sweep_id>` off its own URL, asks the server for
 *  the filed sweep, and lays it out as one printable sheet.
 *
 *  ANACHRONISMS FIRST. On a page somebody prints in order to DO something, the
 *  thing to do leads. A report sorted the way the draft happens to raise its
 *  claims buries the two lines a writer has to change under sixty that are
 *  fine. Within each group the draft's own order is kept, because that is the
 *  order the pages come in.
 *
 *  EVERY VERDICT CARRIES ITS SOURCES. The sweep surface shipped once without
 *  them and it was the worst defect of the night — a page of stamps a reader
 *  had to take on trust, which is the one thing a citation exists to make
 *  unnecessary. A printed sheet is worse again: the screen at least had a link
 *  to nowhere, paper has nothing.
 *
 *  Every string reaching the DOM goes through escapeHtml. The claims are exact
 *  quotations from a writer's draft and the excerpts are pages off the open
 *  web; neither is trusted because a ledger recorded it. */

import { authedFetch } from "/auth.js";
import { escapeHtml, isoStamp } from "/clip.js";
import { excerptProse } from "/excerpt.js";

const sheet = document.getElementById("sheet");

/** Plain language, never our vocabulary: this page is reachable by URL and the
 *  person holding it may not be the person who ran the sweep. */
function problem(message) {
  sheet.innerHTML = `<p class="report-problem">${escapeHtml(message)}</p>`;
}

const VERDICT_ORDER = ["anachronism", "unverifiable", "confirmed"];

const VERDICT_LEAD = {
  anachronism:
    "The department reads these as wrong for the period. Each one is its " +
    "reading of the sources under it, not a check of the line against the " +
    "world — but these are the lines to look at first.",
  unverifiable:
    "Nothing the department could settle. A claim here was either not looked " +
    "for or not found, and those are different: where the sweep ran out of " +
    "searches it says so in the note.",
  confirmed:
    "The sources under these agree with the line as written. That is what the " +
    "department can tell you; whether the source is the right authority for " +
    "your scene is a judgement it does not make on your behalf.",
};

function sourceHtml(source) {
  const url = String(source?.url || "");
  const title = String(source?.title || "").trim();
  // A "title" that is only the url is not a title — star/findings.py falls
  // back to the address when the ledger holds none — so the line is dropped
  // rather than printed twice.
  const heading =
    title && title !== url ? `<p class="report-source-title">${escapeHtml(title)}</p>` : "";
  // The url as its own text inside the link. On paper a link is just words,
  // and these words have to be the address.
  const address = `<p class="report-source-url"><a href="${escapeHtml(url)}"
      rel="noopener noreferrer">${escapeHtml(url)}</a></p>`;
  const excerpt = excerptProse(String(source?.excerpt || "")).trim();
  const quote = excerpt ? `<p class="report-excerpt">${escapeHtml(excerpt)}</p>` : "";
  return `<li class="report-source">${heading}${address}${quote}</li>`;
}

function claimHtml(claim) {
  const scenes = Array.isArray(claim?.scenes) ? claim.scenes : [];
  const sources = Array.isArray(claim?.citations) ? claim.citations : [];
  const note = String(claim?.note || "").trim();
  return `
    <li class="report-claim" data-verdict="${escapeHtml(String(claim?.verdict || ""))}">
      <p class="report-claim-head">
        <span class="report-claim-text">${escapeHtml(String(claim?.text || ""))}</span>
        <span class="report-claim-scenes">${
          scenes.length ? `scene ${escapeHtml(scenes.join(", "))}` : "scene not recorded"
        }</span>
      </p>
      ${note ? `<p class="report-note">${escapeHtml(note)}</p>` : ""}
      ${
        sources.length
          ? `<ul class="report-sources">${sources.map(sourceHtml).join("")}</ul>`
          : `<p class="report-nosource">No source is filed behind this claim.</p>`
      }
    </li>`;
}

function render(sweep) {
  const room = sweep?.room || {};
  const claims = Array.isArray(sweep?.claims) ? sweep.claims : [];
  const swept = isoStamp(sweep?.created_at);

  const masthead = [room.title, room.era, swept && `swept ${swept}`]
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .map(escapeHtml)
    .join(" &middot; ");

  const groups = VERDICT_ORDER.map((verdict) => ({
    verdict,
    // Document order inside a group: that is the order the pages come in.
    claims: claims.filter((c) => String(c?.verdict || "") === verdict),
  })).filter((group) => group.claims.length);

  // Anything with a verdict this page does not know about still prints. A
  // claim dropped for having an unexpected stamp is a claim a writer paid for
  // and never saw.
  const known = new Set(VERDICT_ORDER);
  const other = claims.filter((c) => !known.has(String(c?.verdict || "")));
  if (other.length) groups.push({ verdict: "", claims: other });

  sheet.innerHTML = `
    <p class="report-room">${masthead}</p>
    <h1 class="report-title">What this draft claims about the world</h1>
    <p class="report-counts">
      ${escapeHtml(String(sweep?.scenes_read || 0))} scenes read.
      ${escapeHtml(String(sweep?.claims_raised || 0))} claims raised,
      ${claims.length} distinct, checked for
      ${escapeHtml(String(sweep?.search_count || 0))} live searches.
    </p>
    ${
      sweep?.budget_exhausted
        ? `<p class="report-budget">This sweep reached its search limit before
            the end of the draft. A claim below marked unverifiable for budget
            was not looked for, which is not the same as not being there.</p>`
        : ""
    }
    ${sweep?.scope_note ? `<p class="report-scope">${escapeHtml(sweep.scope_note)}</p>` : ""}
    <p class="report-scope">A verdict is the department's reading of the sources
      printed under it, not a check of the line against the world. Every source
      names where it came from so you can read it and judge for yourself.</p>
    ${
      claims.length
        ? groups
            .map(
              (group) => `
                <section class="report-group">
                  <h2 class="report-group-head">${escapeHtml(
                    group.verdict || "Other"
                  )} &middot; ${group.claims.length}</h2>
                  ${
                    VERDICT_LEAD[group.verdict]
                      ? `<p class="report-group-lead">${escapeHtml(
                          VERDICT_LEAD[group.verdict]
                        )}</p>`
                      : ""
                  }
                  <ul class="report-claims">${group.claims.map(claimHtml).join("")}</ul>
                </section>`
            )
            .join("")
        : `<p class="report-scope">Nothing in this draft made a checkable claim
            about the world. That is a result rather than a failure.</p>`
    }
    <button type="button" class="report-print">Print this report</button>
  `;
  sheet.querySelector(".report-print")?.addEventListener("click", () => window.print());
  if (room.title) {
    document.title = `${String(room.title).slice(0, 60)} — what the draft claims`;
  }
}

async function main() {
  const params = new URLSearchParams(window.location.search);
  const runId = (params.get("run") || "").trim();
  const sweepId = (params.get("sweep") || "").trim();

  if (!runId || !sweepId) {
    problem(
      "This link is incomplete — it needs both a room and a filed sweep. Open " +
        "it from the sweep in the room rather than by hand."
    );
    return;
  }

  let response;
  try {
    response = await authedFetch(
      `/api/rooms/${encodeURIComponent(runId)}/sweeps/${encodeURIComponent(sweepId)}`
    );
  } catch {
    problem(
      "This browser is not signed in to the account that holds this room. " +
        "Open the room in STAR first, then open the report from the sweep."
    );
    return;
  }

  if (response.status === 401) {
    problem(
      "This browser is not signed in to the account that holds this room. " +
        "Open the room in STAR first, then open the report from the sweep."
    );
    return;
  }
  if (response.status === 404) {
    problem("That sweep is not filed under this account.");
    return;
  }
  if (!response.ok) {
    problem("The department could not pull this sweep. Try again in a moment.");
    return;
  }

  try {
    render(await response.json());
  } catch {
    problem("The department could not pull this sweep. Try again in a moment.");
  }
}

main();
