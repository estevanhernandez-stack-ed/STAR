/* THE DEFENCE CARD, fetched and drawn.
 *
 *  Reads `?run=<run_id>&fact=<the sentence>` off its own URL, asks the server
 *  for the card, and renders it. That is the whole of this file.
 *
 *  IT DOES NOT DECIDE WHICH FINDING WAS MEANT. star/defence.py does, and the
 *  MCP `defend_claim` tool calls the same function — so the sheet a writer
 *  prints and the card an agent returns cannot disagree about what the room
 *  says. Matching here would be a second implementation of that rule, and the
 *  place it would surface as a contradiction is in front of the one person in
 *  the process who is already sceptical.
 *
 *  Every string that reaches the DOM goes through escapeHtml or a text node.
 *  The fact and the excerpts are the page's own words as a search returned
 *  them — quoted source material, never markup, and never trusted because a
 *  ledger recorded it. */

import { authedFetch } from "/auth.js";
import { escapeHtml, isoStamp } from "/clip.js";
// The same reducer the room's own clips quote through. Without it this sheet
// printed the ledger entry raw, and the first card off a real room came back
// as nine hundred words of forum thread — usernames, timestamps, "The
// following people thank Pablo Ramon for this post", a markdown permalink —
// around one sentence about Chelsea boots. The clips have never had that
// problem because they have always run this; the card was the surface that
// forgot to.
import { excerptProse } from "/excerpt.js";
// The drawer's own names for the four categories. `objects_props` is a key,
// not a label, and the first printed card carried "OBJECTS_PROPS DRAWER"
// across its masthead. One definition, in the module that owns it.
import { DRAWER_LABELS } from "/drawer.js";

const sheet = document.getElementById("sheet");

/** What the reader is told when there is no card to draw.
 *
 *  Plain language, and never our vocabulary: this page is reachable by URL and
 *  the person holding it may not be the person who built the room. A status
 *  code on screen tells them nothing they can act on. */
function problem(message) {
  sheet.innerHTML = `<p class="defence-problem">${escapeHtml(message)}</p>`;
}

function sourceHtml(source) {
  const url = String(source?.url || "");
  const title = String(source?.title || "").trim();
  // Reduced, not truncated. web/excerpt.js finds where the prose starts —
  // only 4 of the 50 excerpts it was measured against begin with a sentence,
  // the rest open on a heading or a table row — so a character cap applied to
  // the raw string caps a table cell most of the time.
  const excerpt = excerptProse(String(source?.excerpt || "")).trim();
  // The title, when the page had one. star/findings.py falls back to the url
  // when the ledger holds no title, so a "title" identical to the address is
  // not a title and the line is dropped rather than printed twice.
  const heading =
    title && title !== url
      ? `<p class="defence-source-title">${escapeHtml(title)}</p>`
      : "";
  // The url as its own text, inside the link rather than behind it. On paper a
  // link is just words, and these words have to be the address.
  const address = `<p class="defence-source-url"><a href="${escapeHtml(url)}"
      rel="noopener noreferrer">${escapeHtml(url)}</a></p>`;
  const quote = excerpt
    ? `<p class="defence-excerpt">${escapeHtml(excerpt)}</p>`
    : `<p class="defence-noquote">The ledger holds no quotation from this page.
        The address above is what came back from the search; what it says is
        for you to read there.</p>`;
  return `<li class="defence-source">${heading}${address}${quote}</li>`;
}

function render(card) {
  const room = card.room || {};
  const sources = Array.isArray(card.sources) ? card.sources : [];
  const unsourced = Array.isArray(card.unsourced_urls) ? card.unsourced_urls : [];
  const retrieved = isoStamp(card.retrieved_at);

  const drawer = DRAWER_LABELS[card.category] || "";
  const masthead = [room.title, room.era, drawer && `${drawer} drawer`]
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .map(escapeHtml)
    .join(" &middot; ");

  // How this fact got into the room, and when its sources came back. The
  // requisition case says both, because "a writer asked for this on the 12th"
  // is itself provenance — it says the room was interrogated on this exact
  // point rather than having happened to cover it.
  const provenance =
    card.filed_by === "requisition"
      ? `<p class="defence-provenance">Researched on request, in answer to:
          <strong>${escapeHtml(card.requisition || "")}</strong>.
          ${retrieved ? `Its sources were retrieved ${escapeHtml(retrieved)},
          after this room was built.` : ""}</p>`
      : `<p class="defence-provenance">Filed when the room was built${
          retrieved ? `, sources retrieved ${escapeHtml(retrieved)}` : ""
        }.</p>`;

  const sourceBlock = sources.length
    ? `<p class="defence-legend">${sources.length === 1 ? "The source" : "The sources"}</p>
       <ul class="defence-sources">${sources.map(sourceHtml).join("")}</ul>`
    : `<p class="defence-legend">No source</p>
       <p class="defence-provenance">Nothing is filed behind this fact. The
        department will not assemble a defence out of nothing, and a claim in
        this state should not go in front of anyone who might ask.</p>`;

  const unsourcedBlock = unsourced.length
    ? `<div class="defence-unsourced">
         <p class="defence-unsourced-label">Unsourced — do not cite</p>
         <p>The researcher named ${unsourced.length === 1 ? "this address" : "these addresses"},
          and ${unsourced.length === 1 ? "it" : "they"} never appeared in a
          search result. The department cannot put ${unsourced.length === 1 ? "it" : "them"}
          behind anything.</p>
         <ul>${unsourced.map((u) => `<li>${escapeHtml(String(u))}</li>`).join("")}</ul>
       </div>`
    : "";

  sheet.innerHTML = `
    <p class="defence-room">${masthead}</p>
    <p class="defence-fact">${escapeHtml(card.fact || "")}</p>
    ${provenance}
    ${sourceBlock}
    ${unsourcedBlock}
    <p class="defence-scope">Every address above came back from a live web
      search and was recorded before this fact was written, so the titles and
      quotations are the pages' own words and none of them were written by a
      model. That is what the department can tell you. Whether a source
      supports the claim is a judgement it does not make on your behalf — the
      quotations are here so you can make it.</p>
    <button type="button" class="defence-print">Print this sheet</button>
  `;
  sheet
    .querySelector(".defence-print")
    ?.addEventListener("click", () => window.print());
  // The tab's name, once there is something to name it. A writer with four of
  // these open is choosing between them by title, and "STAR — Where this
  // detail came from" four times is not a choice.
  if (card.fact) {
    document.title = `${String(card.fact).slice(0, 60)} — STAR`;
  }
}

async function main() {
  const params = new URLSearchParams(window.location.search);
  const runId = (params.get("run") || "").trim();
  const fact = (params.get("fact") || "").trim();

  if (!runId || !fact) {
    problem(
      "This link is incomplete — it needs both a room and the fact to defend. " +
        "Open it from the finding in the room rather than by hand."
    );
    return;
  }

  let response;
  try {
    response = await authedFetch(
      `/api/rooms/${encodeURIComponent(runId)}/defence?fact=${encodeURIComponent(fact)}`
    );
  } catch {
    // authedFetch throws when there is no usable account on this device, which
    // is the ordinary case for a link opened somewhere else — the rooms are
    // per-account and this browser has none.
    problem(
      "This browser is not signed in to the account that holds this room. " +
        "Open the room in STAR first, then open this card from the finding."
    );
    return;
  }

  if (response.status === 401) {
    problem(
      "This browser is not signed in to the account that holds this room. " +
        "Open the room in STAR first, then open this card from the finding."
    );
    return;
  }
  if (response.status === 404) {
    // The server refuses to build a card around a near match, and says so in
    // its own words. Preferred over anything written here: it knows whether
    // the room was missing or the fact was.
    let detail = "";
    try {
      detail = (await response.json())?.detail || "";
    } catch {
      detail = "";
    }
    problem(
      detail ||
        "That room, or that fact, is not filed under this account."
    );
    return;
  }
  if (!response.ok) {
    problem("The department could not pull this file. Try again in a moment.");
    return;
  }

  try {
    render(await response.json());
  } catch {
    problem("The department could not pull this file. Try again in a moment.");
  }
}

main();
