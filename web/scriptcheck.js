/* THE MORGUE — Script Check: the paste, the marked scene, and the citation rail.

   A check is not a separate place. Its whole value is that it runs against
   THIS room, so it lives in the room's own stage state as a mode toggled from
   the docket's head — the same head the bible is reached from
   (spec.md > The marked scene > Where it lives).

   THE ONE RULE THIS FILE EXISTS TO KEEP, and the reason it reads the way it
   does: NOTHING in this module ever becomes markup. There is no innerHTML, no
   insertAdjacentHTML, no template string that reaches the DOM, and no escaping
   function either — because there is nothing to escape when every string
   becomes a text node. web/anchor.js returns `segments` as DATA
   ({text} and {text, claim}) precisely so the renderer can walk the list with
   document.createTextNode and real <mark> elements, and this is the surface
   where a reader pastes untrusted text ON PURPOSE. Assembling an HTML string
   around scene text here would reopen the H1 XSS through a different door
   (docs/superpowers/specs/2026-08-09-star-gui-design.md:312-318). A pasted
   `<img src=x onerror=alert(1)>` is characters when it arrives, characters
   through the matcher, and characters in the DOM.

   The one place that costs something is a ledger excerpt. `plainExcerpt` below
   strips emphasis to text and decodes the five standard entities, and the
   excerpt lands as one text node. web/clip.js instead runs its copy through
   DOMPurify with a tiny allowlist so the emphasis survives. The highlight is
   real evidence and losing it here is a real cost; it is paid because "no
   string in this module ever becomes markup" is a property a reviewer can
   check with one grep, and on the one surface built around a hostile paste
   that is worth more than four <strong>s.

   WHAT AN EXCERPT ACTUALLY IS, corrected 2026-08-11. This comment used to say
   Parallel Search returns <strong> highlighting and entities like
   `&quot;whiskey sixes,&quot;`, verified against the stored Detroit-1929 room.
   That is no longer what arrives. Measured across all 104 excerpts in the two
   stored rooms: 5 carry <strong>, ZERO carry an HTML entity, and the large
   majority are the page's content as MARKDOWN — headings, table rows, inline
   links, wiki cite markers. Only 4 of 50 in one room even begin with prose.
   Either the API changed its extraction or it varies by source. The decoding
   below is kept rather than deleted because it costs nothing and the Detroit
   evidence was real; what was added is web/excerpt.js, which finds the prose
   before any of this runs.

   COPY DISCIPLINE, which is most of the rest of this file:
     - The word "verified" appears nowhere a reader can see it. The ledger
       proves a URL genuinely came back from a search and that the title and
       excerpt are the page's own words; it proves nothing about whether the
       claim matches the source. Research obligation 3.
     - A VERDICT is the department's reading of the sources shown. Every card
       says so, next to the verdict, because the aversion research is explicit
       that a citation is a trust signal independent of accuracy — a stamp with
       no scope on it is the overclaim.
     - `reason: "budget"` reads as budget and never as not-found. "We ran out of
       searches" and "we looked and it isn't there" are answers the writer is
       owed apart, and star/verdicts.py already writes the distinction into the
       note; this file adds what the note does not say, rather than repeating it.
     - Which of the two answered — the room's own files, or a fresh search — is
       shown per citation. It is computed by star/verdicts.py from two ledgers,
       never asserted by a model about its own behaviour, and it is the closest
       thing this payload has to obligation 7's source TYPE.
     - No duration is ever promised (obligation 6). The working state says the
       department is working and nothing else: no ETA, no bar, no total.
*/

import { anchor } from "/anchor.js";
import { authedFetch } from "/auth.js";
import { excerptProse } from "/excerpt.js";
// The splitter, and nothing else from it. web/fountain.js decides where scenes
// begin; this file decides what to do about it, and the two are kept apart so
// the parsing has tests that never touch a DOM.
import { sceneKey, scenes as fountainScenes } from "/fountain.js";

const VERDICTS = new Set(["confirmed", "anachronism", "unverifiable"]);

/* The filed row a press should be handed back to, or null.
 *
 *  openFiledCheck ends by REBUILDING the filed row rather than patching it, and
 *  the comment there argues why: loadFiledChecks reads aria-current off
 *  currentSceneId, so one code path decides which entry is marked open and
 *  there is no second one to disagree with it. That argument is sound and this
 *  does not touch it — but replaceChildren destroys the button the reader just
 *  pressed, and focus goes to <body> with it. Observed in Chromium, and the
 *  rebuild's own comment never mentioned the cost.
 *
 *  Set only by openFiledCheck, so the row's OTHER caller — the check panel
 *  opening for the first time — cannot pull focus out of whatever the reader
 *  was using. */
let focusFiledAfterLoad = null;

/* Standard English pluralization, sibilants included — "search" takes "+es".
   The third copy of this in the app (web/clip.js exports it, web/app.js keeps
   its own), and recorded as a known duplication rather than an oversight for
   the reason app.js records: importing clip.js for one four-line helper would
   put a second browser-root module in this file's import graph, and this file's
   tests patch that graph by hand. */
function plural(n, word) {
  if (n === 1) return `${n} ${word}`;
  const suffix = /(?:[sxz]|[cs]h)$/i.test(word) ? "es" : "s";
  return `${n} ${word}${suffix}`;
}

/** Parse a candidate as an http(s) URL, or null.
 *
 *  Same guard web/clip.js makes for the same reason: every citation URL in the
 *  payload came out of star/findings.py's `_URL` regex, which only matches
 *  http(s), so in practice this always succeeds — and "in practice" is not a
 *  security property. Checking the scheme here makes the guarantee local, so
 *  nothing this file turns into an href can be a `javascript:` URL whatever an
 *  upstream parser starts accepting later. */
function httpUrl(raw) {
  try {
    const url = new URL(String(raw));
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/** The domain, `www.` dropped because it distinguishes nothing. Used only as
 *  the fallback name for a source the search returned no title for. */
function domainOf(raw) {
  const url = httpUrl(raw);
  return url ? url.hostname.replace(/^www\./i, "") : String(raw);
}

/** A ledger excerpt as plain characters.
 *
 *  Two steps, in this order, and the order matters: strip the emphasis tags
 *  the search API wraps its matched terms in, THEN decode entities. Decoding
 *  first would turn `&lt;strong&gt;` — which is what a page containing the
 *  literal text "<strong>" produces — into a tag this function then removes,
 *  silently editing the source's own words. Stripping first touches only real
 *  tags, and anything the page actually wrote as text survives the decode.
 *
 *  `&amp;` is decoded last for the same reason it is escaped first everywhere
 *  else: doing it earlier would let `&amp;lt;` become `<`.
 *
 *  The result is one string that becomes one text node. Nothing here can
 *  produce an element, which is the whole point. */
function plainExcerpt(raw) {
  // excerptProse first, because it is the step that decides WHAT is quoted;
  // everything below only decides how the characters are spelled. It leaves
  // inline HTML alone, so the tag strip on the next line still has its job.
  return excerptProse(raw)
    .replace(/<\/?(?:strong|em|b|i)>/gi, "")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&apos;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&amp;", "&");
}

/** An element, its class, and its text — the three things every node below
 *  needs and the only three. Text goes through createTextNode, always. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.setAttribute("class", className);
  if (text !== undefined && text !== null && text !== "") {
    node.appendChild(document.createTextNode(String(text)));
  }
  return node;
}

/** The verdict a card, a mark and a stamp all read.
 *
 *  Anything unrecognised lands on `unverifiable`, which is the state that
 *  claims least. Coercing an unknown verdict to `confirmed` would put a stamp
 *  on a line nobody judged; coercing it to `anachronism` would flag one. */
function verdictOf(claim) {
  const verdict = String(claim?.verdict || "").toLowerCase();
  return VERDICTS.has(verdict) ? verdict : "unverifiable";
}

/* ---------------------------------------------------------------------
   The copy. Kept together so the register can be read in one place rather
   than reconstructed from six call sites.
--------------------------------------------------------------------- */

/* The scope on the stamp, as a slug rather than a sentence.
 *
 *  This was three sentences beginning "The department read this line as…",
 *  rendered as a full paragraph directly above the note. Rule 11's own test
 *  condemns them: strike every verb from "The department read this line as
 *  supported by the sources below" and it says exactly the same thing, so it
 *  was a mark all along. It also ranked above the answer, which is rule 10.
 *
 *  WHY "the sources below" IS SAFE HERE, and why this comment exists at all.
 *  The measuring stick's amendment "a mark has no quantifier" was written after
 *  the intake shipped "the source it came from" and had to be killed at
 *  critical severity, because star/findings.py can keep a Finding whose every
 *  cited URL failed the ledger check. A definite plural that a payload can
 *  contradict is exactly that defect.
 *
 *  It cannot happen on these two. star/verdicts.py:275-277 downgrades any
 *  `confirmed` or `anachronism` carrying no citations to `unverifiable` before
 *  the payload is ever written, so those two verdicts always arrive with at
 *  least one source and the phrase asserts nothing the card cannot show. The
 *  third makes no claim about sources at all, which is the one case that can
 *  legitimately have none. The guarantee is a mechanism, not a hope — but it
 *  lives in another file, so it is named here rather than left to be
 *  rediscovered. */
const VERDICT_SLUG = {
  confirmed: "as read from the sources below",
  anachronism: "out of period for the sources below",
  unverifiable: "not settled",
};

/* Two sentences: what a verdict is, and what the reader still has to do
   themselves. The second is the one that cannot be cut — web/clip.js's
   ledgerCheckCopy ends on the same beat, for the same documented reason, and
   the measuring stick's rule 9 records that an earlier attempt to relocate this
   paragraph was rejected for dropping exactly that clause.

   It now renders BELOW the citations rather than above them. Rule 10 is that
   the answer outranks the disclaimer, and once the source quotation is the
   answer — which is what it is, decided 2026-08-11 — a standing paragraph
   above the evidence is that violation restated. "Each source below" became
   "Each source here" for the same reason: the direction word was the only
   thing in it that depended on the position.

   The stamp is still scoped, which is what the file header requires. VERDICT_SLUG
   sits beside it and says the verdict is a reading of the sources, so no card
   renders a stamp with nothing qualifying it. */
const VERDICT_SCOPE =
  "A verdict is the department's reading of the sources shown, not a check of " +
  "the line against the world. Each source here opens where it came from, so " +
  "you can read it and judge for yourself.";

/* An unverifiable with no source at all has nothing to hand the reader, so the
   second sentence above would point at nothing. */
const VERDICT_SCOPE_NO_SOURCES =
  "A verdict is the department's reading of what it had, not a check of the " +
  "line against the world. This one came back with nothing to read.";

const ORIGIN_LABEL = {
  room: "From this room's files",
  search: "From a fresh search for this check",
};

/* What the payload's `reason` adds that the note does not already say.
   star/verdicts.py writes "The check ran out of searches before reaching this
   claim." into the note itself, so repeating it here would be noise. What the
   note does NOT say is that this is a limit on the department rather than a
   result about the line, and that is exactly the conflation the whole
   budget-honesty path exists to prevent. */
const REASON_LINE = {
  budget:
    "The check spent its search budget before it reached this line. That is a " +
    "limit on what the department did, not a finding about the line.",
  unreached:
    "The check came back without a verdict line for this one, so it is filed " +
    "unsettled rather than dropped. Anything the parser could not read is kept " +
    "below, word for word.",
};

/* ---------------------------------------------------------------------
   The scene page: text nodes and real <mark> elements, and nothing else.
--------------------------------------------------------------------- */

/** Build the marked scene.
 *
 *  Walks web/anchor.js's segment list. A segment with no claim becomes a text
 *  node; a segment with one becomes a <mark> holding a text node. Both halves
 *  of that sentence are the security property, and there is no third branch.
 *
 *  Every mark is a control: role="button" because selecting it is what drives
 *  the rail, tabindex so it is reachable by keyboard, aria-pressed so the
 *  selection is a state rather than a colour, and aria-controls pointing at the
 *  rail it changes. Enter and Space are wired by hand because role="button" on
 *  a non-button element gets none of that natively. */
function buildScenePage(scene, claims, select) {
  const page = el("div", "scene-page");
  // A tab stop, a role, and a name, which have to land together — a tab stop
  // with no name is worse than no tab stop, and the name alone does not make
  // the box reachable.
  //
  // THE TAB STOP IS THE FIX. scene.css caps this at 32rem and scrolls it, and
  // the zero-marks state is designed for: server.py writes a dedicated cover
  // note for a scene of pure interior dialogue that asserts nothing about the
  // world, and the rail ships its own copy for it. In that state the scroller
  // holds no focusable child at all, so a keyboard-only reader could not reach
  // their own pasted pages. Safari alone, now: Firefox has made scrollers tab
  // stops since Firefox 4 and Chrome since stable 132.
  //
  // The stop is permanent on purpose. A short scene that never overflows still
  // gets one. Making it conditional means measuring overflow after layout and
  // re-measuring on every reflow, font swap and resize, and a tab stop that
  // comes and goes is worse than one that is always there.
  //
  // THE ROLE IS NOT WHAT NAMES IT. Chromium already exposes this label on the
  // bare div — measured in the live accessibility tree on 2026-08-11, which
  // reported `generic "The scene, with each checked line marked"`. The role
  // makes that conformant rather than tolerated, since `generic` is
  // name-prohibited, and earns the scene a landmark stop on the way past.
  // region over group deliberately: the marked scene is a major perceivable
  // section, which is the case MDN says group should not carry.
  page.setAttribute("role", "region");
  page.setAttribute("tabindex", "0");
  page.setAttribute("aria-label", "The scene, with each checked line marked");
  const { segments, unanchored } = anchor(scene, claims);
  const marks = [];

  for (const segment of segments) {
    if (segment.claim === undefined) {
      page.appendChild(document.createTextNode(segment.text));
      continue;
    }
    const mark = document.createElement("mark");
    mark.setAttribute("class", "mark");
    mark.setAttribute("data-verdict", verdictOf(segment.claim));
    mark.setAttribute("tabindex", "0");
    mark.setAttribute("role", "button");
    mark.setAttribute("aria-pressed", "false");
    mark.setAttribute("aria-controls", "check-rail-body");
    mark.appendChild(document.createTextNode(segment.text));
    mark.addEventListener("click", () => select(segment.claim));
    mark.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") return;
      // Space scrolls the page otherwise, which moves the scene out from under
      // the mark the reader is activating.
      if (event.preventDefault) event.preventDefault();
      select(segment.claim);
    });
    page.appendChild(mark);
    marks.push({ mark, claim: segment.claim });
  }

  return { page, marks, unanchored };
}

/* ---------------------------------------------------------------------
   The rail: one card, following the selected mark.
--------------------------------------------------------------------- */

/** One citation, as a manila fragment: which of the two answered, the source's
 *  own name, its own words where the search returned any, and the link.
 *
 *  target="_blank" rel="noopener noreferrer" is set at construction, which is
 *  the same treatment web/app.js's makeLinksSafe applies after the fact to
 *  markdown it did not author. Set here rather than swept afterwards because
 *  this file authors every anchor it mounts, so there is no window in which one
 *  exists without it. */
function buildCitation(citation, origin) {
  const url = httpUrl(citation?.url);
  if (!url) return null;

  const item = el("li", "rail-citation");
  // Falls back to the neutral line rather than guessing. `origin` is computed
  // server-side from two ledgers; an unrecognised value means this payload was
  // written by something that does not compute it, and inventing "room" would
  // be a provenance claim nobody made.
  item.appendChild(
    el("span", "cite-origin", ORIGIN_LABEL[origin] || "Source behind this verdict")
  );

  const given = String(citation?.title || "").trim();
  // A "title" that is just the URL is not a title — star/verdicts.py hydrates
  // `title=entry.title or entry.url`, so a ledger entry with no title arrives
  // carrying its own address. Fall back to the domain, and never call either
  // one the page's own words.
  const fromPage = Boolean(given) && given !== String(citation.url) && given !== url.href;
  item.appendChild(el("span", "cite-title", fromPage ? given : domainOf(url.href)));

  const excerpt = plainExcerpt(citation?.excerpt || "").trim();
  item.appendChild(
    excerpt
      ? el("blockquote", "cite-excerpt", excerpt)
      : el(
          "p",
          "cite-excerpt cite-excerpt-empty",
          "The search returned this source without an excerpt. There is nothing to quote."
        )
  );

  const link = el("a", "cite-url", url.href);
  link.setAttribute("href", url.href);
  link.setAttribute("target", "_blank");
  link.setAttribute("rel", "noopener noreferrer");
  item.appendChild(link);
  return item;
}

/** The UNSOURCED stamp: the second pad, on a URL neither ledger holds.
 *
 *  Same posture Pipeline A takes on Finding.unverified_urls, down to the
 *  wording: nothing about this link was ever checked, which is a stronger and
 *  more specific statement than uncertainty. Never rendered as an anchor — it
 *  would look like one of the real sources and send a reader to a page nothing
 *  in this system ever saw. */
function buildUnsourced(urls) {
  const block = el("div", "rail-unsourced");
  block.appendChild(el("span", "rail-unsourced-stamp", "Unsourced"));
  block.appendChild(
    el(
      "p",
      "rail-line",
      urls.length === 1
        ? "This link was in neither the room's files nor this check's search " +
            "results, so nothing about it was checked. It is recorded as a " +
            "warning, never as a source."
        : "These links were in neither the room's files nor this check's search " +
            "results, so nothing about them was checked. They are recorded as " +
            "warnings, never as sources."
    )
  );
  const list = el("ul", "rail-unsourced-urls");
  for (const url of urls) list.appendChild(el("li", "rail-unsourced-url", url));
  block.appendChild(list);
  return block;
}

/** The card the rail shows for one claim. */
function buildRailCard(claim) {
  const verdict = verdictOf(claim);
  const card = el("div", "rail-card");
  card.setAttribute("data-verdict", verdict);

  const head = el("p", "rail-head");
  const stamp = el("span", "verdict-stamp", verdict);
  stamp.setAttribute("data-verdict", verdict);
  head.appendChild(stamp);
  // The scope rides with the stamp instead of taking a paragraph above the
  // answer. Between the stamp and the claim type, because it qualifies the
  // stamp and not the type.
  head.appendChild(el("span", "rail-slug", VERDICT_SLUG[verdict]));
  const type = String(claim?.claim_type || "").trim();
  if (type) head.appendChild(el("span", "rail-type", type.replace(/_/g, " ")));
  card.appendChild(head);

  const text = String(claim?.text || "").trim();
  if (text) card.appendChild(el("p", "rail-claim", text));

  // The note, when the verifier wrote one. It is a QUALIFIER and not the
  // answer — star/agents/script_check.py:196-199 instructs that it is optional
  // on confirmed and anachronism, "the year the thing actually arrives or the
  // place it belongs" — and 4 of the 9 claims in the filed Gdansk check carry
  // none. Nothing is invented to fill that gap. The source below answers those.
  const note = String(claim?.note || "").trim();
  if (note) card.appendChild(el("p", "rail-line", note));

  const reason = REASON_LINE[String(claim?.reason || "")];
  if (reason) card.appendChild(el("p", "rail-line", reason));

  const citations = Array.isArray(claim?.citations) ? claim.citations : [];
  const origins = Array.isArray(claim?.citation_sources) ? claim.citation_sources : [];
  const items = citations
    .map((citation, index) => buildCitation(citation, origins[index]))
    .filter(Boolean);

  if (items.length) {
    // The answer, and therefore first of these three. The caveat that used to
    // sit above it now follows it, because it describes what is above it.
    card.appendChild(el("p", "rail-sublegend", "What answered it"));
    const list = el("ul", "rail-citations");
    for (const item of items) list.appendChild(item);
    card.appendChild(list);
    card.appendChild(el("p", "rail-caveat", VERDICT_SCOPE));
  } else {
    // Nothing to rank it below. VERDICT_SCOPE_NO_SOURCES is written for a card
    // with no citation list at all, and moving a paragraph under an absent list
    // would put it nowhere.
    card.appendChild(el("p", "rail-caveat", VERDICT_SCOPE_NO_SOURCES));
  }

  const unsourced = (Array.isArray(claim?.unsourced_urls) ? claim.unsourced_urls : [])
    .map((url) => String(url).trim())
    .filter(Boolean);
  if (unsourced.length) card.appendChild(buildUnsourced(unsourced));

  return card;
}

/* ---------------------------------------------------------------------
   The counts. Research obligation 4 — the real uncertainty data, plainly,
   with every piece dropped rather than defaulted when it is absent.
--------------------------------------------------------------------- */

function meterLine(payload, claims) {
  const parts = [plural(claims.length, "claim")];
  // typeof, not Number(): Number(null) is 0, and a check whose count never
  // reached the client would print a confident "0 live searches" for one that
  // ran six. The rule web/app.js's statsLine already follows.
  if (typeof payload?.search_count === "number") {
    parts.push(plural(payload.search_count, "live search"));
  }
  const filed = filedDate(payload?.created_at);
  if (filed) parts.push(`filed ${filed}`);
  return parts.join(" · ");
}

function uncertaintyLines(payload, claims) {
  const lines = [];
  const rate = Number(payload?.parse_rate);
  // Guarded on there being claims at all: parse_rate is 0.0 when the verifier
  // wrote no bullet lines, and "0% parsed" and "there was nothing to parse" are
  // different statements with only one of them true.
  if (claims.length && Number.isFinite(rate) && rate > 0 && rate < 1) {
    lines.push(
      `${Math.round(rate * 100)}% of the verifier's lines parsed into verdicts. ` +
        "That measures the format it wrote in, not whether its judgments are " +
        "right. Every line the parser could not read is kept below, word for word."
    );
  }
  const unsourced = Number(payload?.unsourced_count);
  if (Number.isFinite(unsourced) && unsourced > 0) {
    lines.push(
      // "appeared in", not "was in": plural() makes the NOUN agree and the verb
      // was hardcoded singular, so at two or more this shipped "2 cited links
      // in this check was in neither…". Fixed with a number-agnostic verb
      // rather than a second conditional, which is how the sibling at
      // web/clip.js:391 has always avoided it ("never appeared in").
      `${plural(unsourced, "cited link")} in this check appeared in neither the room's ` +
        "files nor this check's own search results. Each one is marked on the " +
        "claim that cited it."
    );
  }
  if (payload?.budget_exhausted) {
    lines.push(
      "This check spent its whole search budget. Anything it did not reach says " +
        "so on its own card, and says it as a budget rather than as a result."
    );
  }
  return lines;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** DD MON YYYY, the stamp's slug face — the same format web/app.js's stampDate
 *  produces, from the payload's own timestamp and never from this clock. */
function filedDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const month = d.toLocaleString("en-US", { month: "short" }).toUpperCase();
  return `${pad2(d.getDate())} ${month} ${d.getFullYear()}`;
}

/* ---------------------------------------------------------------------
   The whole result region, assembled.
--------------------------------------------------------------------- */

/** Build one filed check's surface: the cover note, the counts, the marked
 *  scene beside its rail, the parser's residue, and the delete control.
 *
 *  Returns a detached element and wires the mark-to-rail selection inside it,
 *  so the caller mounts one node and the tests can walk one node. `onDelete` is
 *  the caller's — this function knows what the control says and nothing about
 *  the request behind it. */
export function renderCheckResult(payload, { onDelete = null } = {}) {
  const claims = Array.isArray(payload?.claims) ? payload.claims : [];
  const scene = typeof payload?.scene === "string" ? payload.scene : "";
  const root = el("div", "check-result-body");

  // A region, named by its own meter line, and focusable without being a tab
  // stop. mountResult moves focus here when a result lands, which is the only
  // signal that a paid request finished at all.
  //
  // Named by the meter rather than a written heading for two reasons. The name
  // then says what actually landed — "9 claims · 1 live search · filed 10 AUG
  // 2026" — instead of a label that says a result is a result. And the values
  // come from the payload, so it is a mark derived from data, not authored
  // beside it.
  //
  // NOT aria-labelledby at the meter's id, which is the obvious way to write
  // this and does not work. Chromium computes NO NAME for a region whose
  // labelledby points at its own descendant; the same attribute pointing at a
  // node outside the region names it correctly. Verified both ways in the live
  // accessibility tree on 2026-08-11 — the id version passed every source
  // assertion while shipping an unnamed region, which is the failure mode this
  // comment exists to stop someone repeating.
  const meterText = meterLine(payload, claims);
  root.setAttribute("role", "region");
  root.setAttribute("tabindex", "-1");
  root.setAttribute("aria-label", meterText);

  // The department's own line about a thin result, first, before the counts
  // that would otherwise read as an empty tally. star/models.py writes it for
  // exactly two cases and neither is a failure.
  const cover = String(payload?.cover_note || "").trim();
  if (cover) root.appendChild(el("p", "check-cover", cover));

  // What the check did NOT examine, next to the count of what it did.
  //
  // A row of stamps is read as a verdict on the page, not on the claims that
  // happened to be extracted from it — which is how a scene salted with three
  // procedural errors came back looking clean on 2026-08-11. Every stamp there
  // was honest. The summary was not, and this is the sentence that makes it so.
  const scope = String(payload?.scope_note || "").trim();
  if (scope) root.appendChild(el("p", "check-scope", scope));

  // Same string as the region's name above, deliberately: the name is what the
  // reader hears on the way in, this is what they read once they are there.
  root.appendChild(el("p", "check-meter", meterText));
  for (const line of uncertaintyLines(payload, claims)) {
    root.appendChild(el("p", "check-uncertainty", line));
  }

  const columns = el("div", "check-columns");
  const rail = el("aside", "check-rail");
  rail.setAttribute("aria-label", "The sources behind the selected line");

  const railBody = el("div", "check-rail-body");
  railBody.setAttribute("id", "check-rail-body");
  // Polite rather than assertive: selecting a mark is the reader's own action,
  // so the card that answers it should be announced without interrupting them.
  railBody.setAttribute("aria-live", "polite");

  const { page, marks, unanchored } = buildScenePage(scene, claims, select);

  function select(claim) {
    for (const entry of marks) {
      entry.mark.setAttribute("aria-pressed", entry.claim === claim ? "true" : "false");
    }
    for (const button of unplacedButtons) {
      button.node.setAttribute("aria-pressed", button.claim === claim ? "true" : "false");
    }
    railBody.replaceChildren(buildRailCard(claim));
  }

  const unplacedButtons = [];

  columns.appendChild(page);
  rail.appendChild(el("p", "rail-legend", "The selected line"));
  rail.appendChild(railBody);

  // A verdict is never lost because the matcher could not place its quote
  // (prd.md > Script Check — The Marked Scene). These are listed as controls
  // under the rail so a claim with no mark reaches exactly the same card a
  // mark opens.
  if (unanchored.length) {
    rail.appendChild(
      el(
        "p",
        "rail-sublegend",
        `${plural(unanchored.length, "line")} the department checked but could not place`
      )
    );
    rail.appendChild(
      el(
        "p",
        "rail-caveat",
        "The verifier quotes the scene back, and these quotes are not in it word " +
          "for word. The verdicts stand; only the place on the page is missing."
      )
    );
    const list = el("ul", "rail-unplaced-list");
    for (const claim of unanchored) {
      const item = el("li", null);
      const button = el("button", "rail-unplaced-btn");
      button.setAttribute("type", "button");
      button.setAttribute("data-verdict", verdictOf(claim));
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-controls", "check-rail-body");
      button.appendChild(el("span", "rail-unplaced-verdict", verdictOf(claim)));
      button.appendChild(document.createTextNode(String(claim?.text || "").trim()));
      button.addEventListener("click", () => select(claim));
      unplacedButtons.push({ node: button, claim });
      item.appendChild(button);
      list.appendChild(item);
    }
    rail.appendChild(list);
  }

  columns.appendChild(rail);
  root.appendChild(columns);

  // Open on something rather than on an instruction. A mark first, because the
  // scene is what the reader is looking at; an unplaced claim second, because
  // it is still a verdict; a plain line last, when there is genuinely nothing —
  // and then the cover note above has already said why.
  if (marks.length) {
    select(marks[0].claim);
  } else if (unanchored.length) {
    select(unanchored[0]);
  } else {
    railBody.appendChild(
      el(
        "p",
        "rail-line",
        "Nothing in this scene came back with a verdict, so there is nothing to " +
          "read here."
      )
    );
  }

  const notes = String(payload?.field_notes || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (notes.length) {
    const block = el("div", "check-field-notes");
    block.appendChild(el("p", "rail-legend", "Lines the parser could not read as verdicts"));
    block.appendChild(
      el(
        "p",
        "check-uncertainty",
        "Not verdicts, and not dropped. A line lands here when it is not a " +
          "verdict the grammar could read, or when it answers a quote this scene " +
          "does not make. Shown word for word."
      )
    );
    for (const note of notes) block.appendChild(el("p", "check-field-note", note));
    root.appendChild(block);
  }

  root.appendChild(buildFoot(payload, onDelete));
  return root;
}

/** The foot: what this check is, and the control that removes it.
 *
 *  Two clicks, not one. The first arms and says exactly what goes; the second
 *  does it. A check spends real searches to produce and the scene it holds is
 *  the reader's own pages — one stray click should not be able to spend the
 *  first or lose the second. Nothing is hidden behind a browser dialog: the
 *  warning is on the page, in the department's own voice. */
function buildFoot(payload, onDelete) {
  const foot = el("div", "check-foot");
  const filed = filedDate(payload?.created_at);
  if (filed) foot.appendChild(el("span", "check-filed-slug", `FILED ${filed}`));
  if (!onDelete) return foot;

  const note = el("span", "check-delete-note");
  const button = el("button", "check-delete-btn", "Delete this check");
  button.setAttribute("type", "button");
  button.setAttribute("data-armed", "false");

  button.addEventListener("click", () => {
    if (button.getAttribute("data-armed") !== "true") {
      button.setAttribute("data-armed", "true");
      button.replaceChildren(document.createTextNode("Delete it for good"));
      note.replaceChildren(
        document.createTextNode(
          "This removes the check and the scene text stored with it. It cannot " +
            "be undone, and re-running it spends searches again."
        )
      );
      return;
    }
    button.disabled = true;
    onDelete();
  });

  foot.appendChild(button);
  foot.appendChild(note);
  return foot;
}

/* ---------------------------------------------------------------------
   The surface's own wiring: the paste box, the request, the filed list.

   Everything below touches index.html by id and is inert until
   initScriptCheck() runs, so importing this module in Node costs nothing and
   reaches no DOM. That is what lets tests/js/test_scriptcheck.mjs exercise the
   renderer above against a stubbed document.
--------------------------------------------------------------------- */

let els = null;
let roomId = null;
// The parsed draft currently in the box, and the keys of every scene this room
// has a filed check for. Both are this module's, not the server's: the keys
// arrive with the filed list (star/store.py's scene_summary) and the parse is
// redone whenever the box changes.
let draftScenes = [];
let checkedKeys = new Set();
let currentSceneId = null;
let loadedFiledFor = null;

const $ = (id) => document.getElementById(id);

export function initScriptCheck() {
  els = {
    panel: $("check-panel"),
    input: $("scene"),
    run: $("check-run-btn"),
    status: $("check-status"),
    error: $("check-error"),
    result: $("check-result"),
    filedRow: $("check-filed-row"),
    filedList: $("check-filed-list"),
    draft: $("check-draft"),
    draftCount: $("check-draft-count"),
    draftDone: $("check-draft-done"),
    draftScenes: $("check-draft-scenes"),
    sweep: $("check-sweep-btn"),
    sweepNote: $("check-sweep-note"),
    sweepResult: $("check-sweep-result"),
    sweptRow: $("check-swept-row"),
    sweptList: $("check-swept-list"),
  };
  els.run.addEventListener("click", runCheck);
  els.sweep.addEventListener("click", runSweep);
  // `input` rather than `paste`: a paste event fires before the value lands,
  // and a writer may also drag a file in or type. This runs a regex over the
  // box on every keystroke, which is cheap next to what the box costs to
  // render at ninety pages.
  els.input.addEventListener("input", showDraft);
}

/** The draft strip: what a paste turns out to be, when it is a screenplay.
 *
 *  THE PROBLEM IT SOLVES. `check_scene` takes one scene, so a writer with a
 *  finished draft found their first scene in their editor, selected it,
 *  pasted, waited, went back for the second, and did that fifty times. The
 *  check was always the thing they came for; the intake was shaped for a demo.
 *
 *  It appears only when a paste holds MORE THAN ONE heading. One scene pasted
 *  into a scene box is the case this surface was built for and needs no strip
 *  telling it so, and text with no headings at all — a paragraph, a treatment
 *  fragment — is a legitimate thing to check that web/fountain.js correctly
 *  declines to split. In both cases the box behaves exactly as it did.
 *
 *  Nothing here submits anything. Pressing a scene loads it into the box the
 *  writer already knows, and the check runs from the button it already ran
 *  from — so a draft of ninety pages cannot cost ninety checks by accident,
 *  and every spend is still one deliberate press. */
function showDraft() {
  if (!els) return;
  const parsed = fountainScenes(els.input.value);
  if (parsed.length > 1) {
    // A draft arrived, or the one in the box changed. Remember it.
    draftScenes = parsed;
  } else if (draftScenes.length) {
    // ONE scene in the box while a draft is remembered, which is the ordinary
    // state after pressing a scene — and the list must survive it, or picking
    // a scene destroys the list the writer is working through.
    //
    // Kept only when the box holds one of THIS draft's own scenes. A writer
    // who has moved on and pasted something unrelated should not be looking at
    // a stale list of a screenplay they are no longer in; comparing by key is
    // the same comparison that decides which scenes are already checked, so
    // there is one definition of "the same scene" and not two.
    const key = sceneKey(els.input.value.trim());
    if (!draftScenes.some((s) => sceneKey(s.text) === key)) draftScenes = [];
  }
  renderDraft();
}

function renderDraft() {
  if (!els) return;
  if (!draftScenes.length) {
    els.draft.classList.add("hidden");
    els.draftScenes.replaceChildren();
    els.draftCount.replaceChildren();
    els.draftDone.replaceChildren();
    els.sweepNote.replaceChildren();
    return;
  }

  const done = draftScenes.filter((scene) => checkedKeys.has(sceneKey(scene.text))).length;
  els.draft.classList.remove("hidden");
  els.draftCount.replaceChildren(
    document.createTextNode(
      `This looks like a screenplay — ${plural(draftScenes.length, "scene")}. ` +
        "Pick one to load it into the box below."
    )
  );
  els.draftDone.replaceChildren(
    document.createTextNode(done ? `${done} already checked against this room.` : "")
  );

  els.draftScenes.replaceChildren();
  for (const scene of draftScenes) {
    const checked = checkedKeys.has(sceneKey(scene.text));
    const btn = el("button", "check-draft-scene");
    btn.type = "button";
    if (checked) btn.dataset.checked = "true";
    // Text nodes, never markup, for the reason at the top of this file: a
    // scene heading is writer-supplied text and this is the surface built
    // around a hostile paste.
    btn.appendChild(el("span", "check-draft-index", String(scene.index)));
    btn.appendChild(el("span", "check-draft-slug", scene.heading));
    if (checked) {
      btn.appendChild(el("span", "check-draft-tick", "checked"));
    }
    btn.addEventListener("click", () => {
      els.input.value = scene.text;
      els.input.focus();
      // Not submitted. See showDraft: every spend stays one deliberate press
      // of the button the writer already knows.
      els.error.replaceChildren();
    });
    els.draftScenes.appendChild(btn);
  }

  // What the sweep will cost, before it is pressed. This is the one control on
  // the surface that spends without a scene being chosen, so a reader must not
  // have to press it to find out what it does.
  els.sweepNote.replaceChildren(
    document.createTextNode(
      `Reads all ${plural(draftScenes.length, "scene")}, collects what the ` +
        "draft claims about the world, and checks the distinct set against " +
        "this room in one pass. One search budget for the draft, and one " +
        "check against your hourly limit."
    )
  );
}

/** Every claim a draft makes, asked once.
 *
 *  The other thing to do with a pasted draft, and the reason the strip is not
 *  just a convenience. A scene check answers "is this scene right"; a sweep
 *  answers "does this draft contradict itself about the world", which is a
 *  question no number of scene checks adds up to — an object that is fine in
 *  1958 and wrong in 1960 is wrong in neither scene alone.
 *
 *  Deliberately NOT wired to the scene list's own buttons. Those load a scene
 *  and spend nothing; this spends, so it is its own control with its own words
 *  on it. */
async function runSweep() {
  if (!roomId || !draftScenes.length) return;
  els.error.replaceChildren();
  els.sweepResult.replaceChildren();
  els.sweepResult.classList.add("hidden");
  els.sweep.disabled = true;
  working(
    `The department is reading all ${plural(draftScenes.length, "scene")} and ` +
      "checking what they claim against this room"
  );

  let payload;
  try {
    const res = await authedFetch(`/api/rooms/${encodeURIComponent(roomId)}/sweep`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenes: draftScenes.map((scene) => ({
          index: scene.index,
          heading: scene.heading,
          text: scene.text,
        })),
      }),
    });
    if (!res.ok) throw new Error(await failureDetail(res));
    payload = await res.json();
  } catch (err) {
    els.status.replaceChildren();
    els.sweep.disabled = false;
    els.error.replaceChildren(document.createTextNode(err.message));
    els.sweep.focus();
    return;
  }

  els.status.replaceChildren();
  els.sweep.disabled = false;
  renderSweep(payload);
  // The sweep that just ran is now filed, so the row has to learn about it.
  // Same shape as a finished check refreshing the filed row above.
  loadFiledSweeps();
}

/** Every sweep filed on this room, newest first.
 *
 *  Fetched when the check mode opens rather than on every room paint, for the
 *  reason the filed checks are: it costs a request and a reader who never
 *  opens this mode should not pay for one. */
async function loadFiledSweeps() {
  const room = roomId;
  let sweeps = [];
  try {
    const res = await authedFetch(`/api/rooms/${encodeURIComponent(room)}/sweeps`);
    if (!res.ok) return;
    const body = await res.json();
    sweeps = Array.isArray(body?.sweeps) ? body.sweeps : [];
  } catch {
    // Silent, and the row stays hidden. A list that cannot be read is not an
    // error worth a banner when the surface's actual job still works.
    return;
  }
  if (room !== roomId || !sweeps.length) return;

  els.sweptList.replaceChildren();
  for (const summary of sweeps) {
    const id = String(summary?.sweep_id || "");
    if (!id) continue;
    // WHAT was swept, then when. Two sweeps of the same draft on the same day
    // are told apart by their counts — a rewrite changes what a draft claims,
    // which is the whole reason somebody sweeps it twice.
    const label = [
      `${plural(Number(summary?.scenes_read) || 0, "scene")}`,
      `${plural(Number(summary?.claim_count) || 0, "claim")}`,
      filedDate(summary?.created_at) || "",
    ]
      .filter(Boolean)
      .join(" · ");
    const button = el("button", "check-filed-btn", label);
    button.setAttribute("type", "button");
    button.addEventListener("click", () => openFiledSweep(id));
    els.sweptList.appendChild(button);
  }
  els.sweptRow.classList.remove("hidden");
}

async function openFiledSweep(sweepId) {
  if (!roomId) return;
  els.error.replaceChildren();
  working("Pulling the filed sweep");
  let payload;
  try {
    const res = await authedFetch(
      `/api/rooms/${encodeURIComponent(roomId)}/sweeps/${encodeURIComponent(sweepId)}`
    );
    if (!res.ok) throw new Error(await failureDetail(res));
    payload = await res.json();
  } catch (err) {
    els.status.replaceChildren();
    els.error.replaceChildren(document.createTextNode(err.message));
    return;
  }
  els.status.replaceChildren();
  renderSweep(payload);
}

function renderSweep(payload) {
  const claims = Array.isArray(payload?.claims) ? payload.claims : [];
  const body = el("div", "sweep");
  body.setAttribute("tabindex", "-1");

  const raised = Number(payload?.claims_raised) || 0;
  const read = Number(payload?.scenes_read) || 0;
  const searches = Number(payload?.search_count) || 0;

  // Both numbers. The gap between what a draft RAISED and what was distinct is
  // the whole reason this costs less than the same scenes one at a time, and a
  // reader cannot work it out from either number alone.
  body.appendChild(
    el(
      "p",
      "sweep-count",
      `${plural(read, "scene")} read. ${plural(raised, "claim")} raised, ` +
        `${claims.length} distinct, checked against this room for ` +
        `${plural(searches, "live search")}.`
    )
  );
  if (payload?.scope_note) body.appendChild(el("p", "sweep-scope", payload.scope_note));
  // The same scope a filed check carries, for the same reason: a verdict is
  // the department's reading of the sources shown, not a check of the claim
  // against the world. A page of stamps without this sentence reads as the
  // department vouching for a draft.
  body.appendChild(
    el(
      "p",
      "sweep-scope",
      "A verdict is the department's reading of the sources under it, not a " +
        "check of the line against the world. Every source opens where it came " +
        "from, so you can read it and judge for yourself."
    )
  );
  if (payload?.budget_exhausted) {
    body.appendChild(
      el(
        "p",
        "sweep-budget",
        "The sweep reached its search limit before the end of the draft. What " +
          "is below is what it managed; a claim marked unverifiable for budget " +
          "was not looked for, which is not the same as not being there."
      )
    );
  }

  if (!claims.length) {
    body.appendChild(
      el(
        "p",
        "sweep-scope",
        "Nothing in this draft made a checkable claim about the world. That is " +
          "a result rather than a failure — a stretch of pure dialogue asserts " +
          "very little a department can look up."
      )
    );
  }

  const list = el("ul", "sweep-list");
  for (const claim of claims) {
    const item = el("li", "sweep-claim");
    item.dataset.verdict = String(claim?.verdict || "unverifiable");
    item.appendChild(el("span", "sweep-verdict", String(claim?.verdict || "unverifiable")));
    item.appendChild(el("span", "sweep-text", String(claim?.text || "")));
    const scenes = Array.isArray(claim?.scenes) ? claim.scenes : [];
    // Which pages to open. The one thing a sweep can say that a scene check
    // cannot, and it is the reason the answer is worth reading top to bottom.
    item.appendChild(
      el(
        "span",
        "sweep-scenes",
        scenes.length ? `scene ${scenes.join(", ")}` : "scene not recorded"
      )
    );
    if (claim?.note) item.appendChild(el("p", "sweep-note", String(claim.note)));

    // THE RECEIPTS. A verdict printed without them is the overclaim this whole
    // project is built against — and the first sweep of a real draft returned
    // forty-five confirmations with nothing on screen behind any of them.
    // star/verdicts.py already guarantees a confirmed claim holds at least one
    // hydrated citation (it downgrades to unverifiable otherwise), so the
    // sources were always there; this surface simply did not print them, which
    // asked a reader to take the stamp on trust. That is the one thing a
    // citation is supposed to make unnecessary.
    const citations = Array.isArray(claim?.citations) ? claim.citations : [];
    if (citations.length) {
      const sources = el("ul", "sweep-sources");
      for (const citation of citations) {
        const url = httpUrl(citation?.url);
        const source = el("li", "sweep-source");
        const link = el("a", "sweep-source-link", String(citation?.title || domainOf(citation?.url)));
        if (url) {
          link.setAttribute("href", url.href);
          link.setAttribute("rel", "noopener noreferrer");
          link.setAttribute("target", "_blank");
        }
        source.appendChild(link);
        source.appendChild(el("span", "sweep-source-domain", domainOf(citation?.url)));
        const excerpt = plainExcerpt(citation?.excerpt);
        if (excerpt) source.appendChild(el("p", "sweep-excerpt", excerpt));
        sources.appendChild(source);
      }
      item.appendChild(sources);
    }
    list.appendChild(item);
  }
  if (claims.length) body.appendChild(list);

  // The way out of the app. A sweep answers a whole draft and the person who
  // asks "are you sure" is usually not at the writer's screen, so the report
  // is a page of its own that prints — the arrangement the defence card
  // already proved. Only for a FILED sweep: a live result has no id yet, and a
  // link to a report that cannot be fetched is worse than no link.
  if (payload?.sweep_id) {
    const out = el("p", "sweep-report");
    const link = el("a", "sweep-report-link", "Open the printable report");
    link.setAttribute(
      "href",
      `/report.html?run=${encodeURIComponent(roomId)}&sweep=${encodeURIComponent(payload.sweep_id)}`
    );
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener");
    out.appendChild(link);
    body.appendChild(out);
  }

  els.sweepResult.replaceChildren(body);
  els.sweepResult.classList.remove("hidden");
  body.focus();
}

/** Point the surface at a room. Called every time a room is painted, so a
 *  reader moving between rooms in the rail never sees the previous room's
 *  scene sitting in the box under a new room's title. */
export function setCheckRoom(runId) {
  if (runId === roomId) return;
  roomId = runId;
  loadedFiledFor = null;
  // Guarded the same way resetCheck is. initScriptCheck() runs at web/app.js's
  // module load and every caller of this function is downstream of that today,
  // so the guard is for the order changing rather than for the order now — and
  // a room change that threw here would take the whole room render with it.
  if (els) clearCheck({ keepScene: false });
}

/** Everything this surface is holding, let go of. Called on a room change and
 *  from web/app.js's resetRoomView, which runs before a room load is even
 *  issued — the same placement that fixed the cross-room leak in the drawers.
 *
 *  `nextRunId` is the room about to be painted. Passing it keeps an
 *  unsubmitted scene alive when the reader re-enters the room they are already
 *  in — which is the way back from Your card, since that surface reaches this
 *  one only through the rail. Without it, that click destroyed pages of typed
 *  text that live nowhere else: nothing in web/ stores #scene, and an in-page
 *  `.value = ""` with no navigation is outside browser form restore.
 *
 *  The comparison happens HERE rather than in the caller because `roomId` is
 *  this module's state and the caller no longer has the old room to compare
 *  against — shell.js's loadRoom marks the NEW room active before app.js's
 *  resetRoomView runs.
 *
 *  Called with no argument it behaves exactly as it did: a full let-go. */
export function resetCheck(nextRunId) {
  const sameRoom = nextRunId != null && nextRunId === roomId;
  // Held across a same-room reset so setCheckRoom's `if (runId === roomId)`
  // guard can actually fire. Nulling it unconditionally is what disarmed that
  // guard — it can never match a roomId this function just erased, so the
  // room paint that follows called clearCheck a second time and wiped the
  // scene this reset had just been careful to keep.
  if (!sameRoom) roomId = null;
  // Both branches. clearCheck empties the filed row below, so the list has to
  // be re-fetched the next time the mode is opened, same room or not.
  loadedFiledFor = null;
  if (els) clearCheck({ keepScene: sameRoom });
}

function clearCheck({ keepScene }) {
  currentSceneId = null;
  els.result.replaceChildren();
  els.result.classList.add("hidden");
  els.error.replaceChildren();
  els.status.replaceChildren();
  els.run.disabled = false;
  els.filedRow.classList.add("hidden");
  els.filedList.replaceChildren();
  // The sweep goes with everything else. It is a whole draft's worth of
  // answers about ONE room, and leaving it standing under a different room's
  // title is the cross-room leak the drawers were fixed for.
  els.sweep.disabled = false;
  els.sweepResult.replaceChildren();
  els.sweepResult.classList.add("hidden");
  els.sweptRow.classList.add("hidden");
  els.sweptList.replaceChildren();
  if (!keepScene) els.input.value = "";
}

/** Called when the reader opens the check mode. The filed list is fetched
 *  here rather than on every room paint: it costs a request, and a reader who
 *  never opens this mode should not pay for one. */
export function openedCheck() {
  if (!roomId || loadedFiledFor === roomId) return;
  loadedFiledFor = roomId;
  loadFiledChecks();
  loadFiledSweeps();
}

/** The working state, and the whole of what obligation 6 permits: that the
 *  department is working. No ETA, no bar implying a known total, no "about a
 *  minute". `.ellipsis` is web/shell.css's, which already carries its own
 *  reduced-motion path. */
function working(message) {
  els.status.replaceChildren(document.createTextNode(message));
  els.status.appendChild(el("span", "ellipsis"));
}

/** Read a failed response the way web/app.js's buildRoom does.
 *
 *  An unguarded res.json() surfaces the PARSE failure instead of the request
 *  failure: a Cloud Run 429 or 503 with an HTML body puts `Unexpected token
 *  '<'` on screen as the department's own message. */
async function failureDetail(res) {
  try {
    return (await res.json()).detail || res.statusText;
  } catch {
    return res.statusText;
  }
}

async function runCheck() {
  const scene = els.input.value.trim();
  els.error.replaceChildren();
  if (!roomId) return;
  if (!scene) {
    els.error.replaceChildren(
      document.createTextNode("Paste a scene for the department to check.")
    );
    return;
  }
  // The whole draft is still in the box. Caught HERE rather than at the
  // server, which answers "send the department a scene, not the script" — a
  // sentence that was right until this surface started asking for the script.
  // The strip above invites the paste and then the refusal scolded the reader
  // for accepting the invitation, which is the app disagreeing with itself in
  // front of somebody who did exactly what it said.
  //
  // The server's wording stays as it is. The agent door has no strip and no
  // list to pick from, so there "send a scene, not the script" is still the
  // whole of the advice.
  // Parsed from the BOX, not read off `draftScenes`. That variable is the
  // remembered draft and it deliberately survives picking a scene out of it —
  // so testing it here refused the very scene the reader had just loaded,
  // told them to pick one from a list they had already picked from, and left
  // no way forward at all. Setting `.value` from code fires no `input` event,
  // which is why the stale read looked correct in every test that never
  // pressed a button.
  const inBox = fountainScenes(scene);
  if (inBox.length > 1) {
    els.error.replaceChildren(
      document.createTextNode(
        `That is the whole draft — ${plural(inBox.length, "scene")}. ` +
          "Pick one from the list above and it will load here, then check that."
      )
    );
    els.input.focus();
    return;
  }

  // Disabling the focused button drops focus to <body> in every engine, and
  // re-enabling it does not give focus back. So from here until one of the two
  // exits below puts focus somewhere deliberate, a keyboard reader who presses
  // Tab restarts at the top of the document. Both exits are accounted for.
  //
  // The button stays genuinely disabled rather than aria-disabled: it blocks a
  // second submit at the platform level, which is worth more than the focus it
  // costs now that the focus is handed back.
  els.run.disabled = true;
  working("The department is pulling the claims and checking them against this room");

  let payload;
  try {
    const res = await authedFetch(`/api/rooms/${encodeURIComponent(roomId)}/scenes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The label that lets a draft split tomorrow know this scene was
      // checked today. web/fountain.js owns what it means; the server
      // stores it without looking at it.
      body: JSON.stringify({ scene, scene_key: sceneKey(scene) }),
    });
    if (!res.ok) throw new Error(await failureDetail(res));
    try {
      payload = await res.json();
    } catch {
      throw new Error("The department answered, but not in a shape this page understands.");
    }
  } catch (err) {
    els.status.replaceChildren();
    els.run.disabled = false;
    els.error.replaceChildren(document.createTextNode(err.message));
    // Failure exit: back to the control they pressed. There is no result to
    // land in, and the message they need is this button's own neighbour.
    // Re-enable first — focus() on a disabled button does nothing.
    els.run.focus();
    return;
  }

  els.status.replaceChildren();
  els.run.disabled = false;
  // The POST response carries the claims but not the scene — the server returns
  // the ScriptCheckResult, and the scene is the text this page just sent. Hand
  // it back in so the marked scene has characters to mark.
  //
  // Success exit: into the result. This is the only thing that tells anyone the
  // request finished — a status line clearing and a button re-enabling is not a
  // signal, and the result mounts below the fold.
  mountResult({ ...payload, scene }, { moveFocus: true });
  // Marked now rather than after the filed list comes back. The refetch below
  // is what makes it survive a reload; this is what makes the strip agree with
  // what the reader just watched happen.
  checkedKeys.add(sceneKey(scene));
  renderDraft();
  loadedFiledFor = null;
  openedCheck();
}

function mountResult(payload, { moveFocus = false } = {}) {
  currentSceneId = String(payload?.scene_id || "");
  const body = renderCheckResult(payload, { onDelete: currentSceneId ? deleteCheck : null });
  els.result.replaceChildren(body);
  els.result.classList.remove("hidden");

  // Only when the reader asked for this result just now. Opening a filed check
  // from the row mounts through here too, and stealing focus from a control
  // somebody is still using is the opposite of the fix.
  //
  // No scrollIntoView beside this: focus scrolls the element into view on its
  // own, and calling both scrolls twice. That native scroll is instant, since
  // the app declares scroll-behavior nowhere, so it honours reduced motion
  // without a media query. Add `scroll-behavior: smooth` anywhere above this
  // and that stops being true.
  if (moveFocus) body.focus();
}

async function deleteCheck() {
  const sceneId = currentSceneId;
  if (!roomId || !sceneId) return;
  els.error.replaceChildren();
  working("Removing the check and the scene stored with it");
  try {
    const res = await authedFetch(
      `/api/rooms/${encodeURIComponent(roomId)}/scenes/${encodeURIComponent(sceneId)}`,
      { method: "DELETE" }
    );
    if (!res.ok) throw new Error(await failureDetail(res));
  } catch (err) {
    els.status.replaceChildren();
    els.error.replaceChildren(document.createTextNode(err.message));
    return;
  }
  clearCheck({ keepScene: false });
  els.status.replaceChildren(
    document.createTextNode("The check is gone, and the scene text stored with it.")
  );
  loadedFiledFor = null;
  openedCheck();
}

/** The room's other filed checks. A check that was paid for once opens again
 *  without paying for it twice — star/store.py's document_to_scene returns the
 *  same shape the run returned, scene text included, for exactly this. */
async function loadFiledChecks() {
  const room = roomId;
  let scenes = [];
  try {
    const res = await authedFetch(`/api/rooms/${encodeURIComponent(room)}/scenes`);
    if (!res.ok) return;
    const body = await res.json();
    scenes = Array.isArray(body?.scenes) ? body.scenes : [];
  } catch {
    // A rail that cannot be read is not an error worth a banner: the paste box
    // above it is the surface's actual job and it still works. Silent, and the
    // row stays hidden.
    return;
  }
  // The room may have changed while this was in flight.
  if (room !== roomId || !scenes.length) return;

  // The keys of every scene this room has a check filed for, so a draft split
  // in the box above can say which of its scenes are already done. This is
  // what makes the strip survive a reload — `runCheck` marks the scene it just
  // ran, and this is where that becomes durable.
  checkedKeys = new Set(
    scenes.map((summary) => String(summary?.scene_key || "")).filter(Boolean)
  );
  renderDraft();

  els.filedList.replaceChildren();
  for (const summary of scenes) {
    const id = String(summary?.scene_id || "");
    if (!id) continue;
    // WHICH SCENE first, the date second. Every check filed in one sitting
    // carries the same day, so a column reading "12 AUG 2026 · 3 claims" over
    // "12 AUG 2026 · 5 claims" asks a writer to remember which was which — and
    // the one thing they actually know about a check is the scene they ran it
    // on. The date stays, because on a room worked over weeks it is the thing
    // that separates two checks of the SAME scene.
    //
    // star/store.py derives the label from the scene's first non-empty line.
    // A room checked before that field existed has none, and falls back to
    // what the row said before.
    const scene = String(summary?.scene_label || "").trim();
    const label = [
      scene || filedDate(summary?.created_at) || "Filed",
      plural(Number(summary?.claim_count) || 0, "claim"),
      scene ? filedDate(summary?.created_at) : "",
    ]
      .filter(Boolean)
      .join(" · ");
    const button = el("button", "check-filed-btn", label);
    button.setAttribute("type", "button");
    button.setAttribute("aria-current", id === currentSceneId ? "true" : "false");
    button.addEventListener("click", () => openFiledCheck(id));
    els.filedList.appendChild(button);
    // The same row, rebuilt. Hand the press back to it.
    if (focusFiledAfterLoad === id) button.focus();
  }
  focusFiledAfterLoad = null;
  els.filedRow.classList.remove("hidden");
}

async function openFiledCheck(sceneId) {
  els.error.replaceChildren();
  working("Opening the filed check");
  let payload;
  try {
    const res = await authedFetch(
      `/api/rooms/${encodeURIComponent(roomId)}/scenes/${encodeURIComponent(sceneId)}`
    );
    if (!res.ok) throw new Error(await failureDetail(res));
    payload = await res.json();
  } catch (err) {
    els.status.replaceChildren();
    els.error.replaceChildren(document.createTextNode(err.message));
    return;
  }
  els.status.replaceChildren();
  // The stored scene goes back in the box, so re-running or editing starts from
  // what was actually checked rather than from an empty field.
  els.input.value = typeof payload?.scene === "string" ? payload.scene : "";
  mountResult(payload);
  // The filed row is rebuilt rather than patched in place: loadFiledChecks
  // reads aria-current off currentSceneId, which mountResult has just set, so
  // one code path decides which entry is marked open and there is no second
  // one to disagree with it.
  loadedFiledFor = null;
  focusFiledAfterLoad = sceneId;
  openedCheck();
}
