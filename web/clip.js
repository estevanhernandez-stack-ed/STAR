/* THE MORGUE — the clip: one fact, its receipts, and what was actually checked.

   A clip is the unit of the product (docs/design/DIRECTION.md): one parsed
   Finding, the ledger entries behind it, and — where the ledger check failed —
   the URL that never came back from a search, kept on screen rather than
   quietly dropped.

   Dependency direction is one-way: drawer.js imports this file, never the
   reverse. escapeHtml and plural therefore live HERE, as the leaf module, and
   drawer.js imports them. They were drawer.js's before this task; moving them
   down rather than copying them is the only way two modules can share them
   without a cycle in a no-build ES-module app.

   Copy discipline, which is most of this file's reason for existing:
     - The word "verified" never appears in anything a user reads. The ledger
       check proves a URL genuinely came back from a live search and that the
       title and excerpt are the page's own words (star/findings.py hydrates
       both from SourceLedger, so no model ever authors them). It proves
       NOTHING about whether the fact matches the source. Every sentence below
       is scoped to that narrow claim — research obligation 3.
     - parse_rate is findings over BULLET LINES (star/findings.py). It measures
       how much of the researcher's own output FORMAT the parser could read.
       Saying or implying it measures the researcher's accuracy would be a
       false claim of exactly the kind this phase exists to prevent.
     - field_notes is not a curated uncertainty section. star/models.py: "Lines
       that did not parse as findings, kept rather than dropped." In the real
       Detroit-1929 run it held one genuine researcher hedge (setting) and
       nothing at all in the other three categories, so it is surfaced — but
       labelled as what it is, not as calibrated confidence.
     - The scene-need join (ResearchQuestion.why) is per CATEGORY, never per
       finding: a category carries several questions and there is no honest way
       to attach one to a specific fact. It is presented at the drawer level
       for that reason, and renderClip takes no sceneNeed argument.

   Color discipline:
     - --aniline is the FILED pad and this is the first file entitled to use
       it: DIRECTION.md specifies the signature stamp (domain, retrieval date,
       researcher's code) at the per-CITATION level, "when the ledger check
       passes", and a resolved Citation is exactly that. See clip.css for why
       the stamp's letterforms are a color-mix shade of it rather than the raw
       token (contrast), and its rule is the raw token.
     - --oxide is the FLAGGED pad, on the unsourced URL and nowhere else.
*/

export function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/* Naive "+s" breaks on "search" ("searchs") — a real bug drawer.js shipped
 * twice (Task 3's aria-label on the dot row, then Task 4's "N searches
 * completed" stamp line). Standard English pluralization for words ending in
 * a sibilant sound takes "+es", not "+s". Moved here from drawer.js so this
 * file and that one share one implementation rather than two that can drift. */
export function plural(n, word) {
  if (n === 1) return `${n} ${word}`;
  const suffix = /(?:[sxz]|[cs]h)$/i.test(word) ? "es" : "s";
  return `${n} ${word}${suffix}`;
}

/** The exact claim the ledger check supports, and no more. Three sentences:
 *  what happened, where the words came from, and what the reader still has to
 *  do themselves. Cutting the third would leave a citation reading as an
 *  endorsement of the fact above it, which is the precise failure the aversion
 *  research documents — people trust a cited answer more even when it is wrong.
 *
 *  The MIDDLE sentence is branched, because it makes a claim about specific
 *  things on screen and both of them can be absent:
 *    - No excerpt. `_best_excerpt` (star/findings.py) returns "" for a ledger
 *      entry that carries no excerpts, and renderReceipt already has a branch
 *      that says so out loud — so the fixed copy sat directly under "There is
 *      nothing to quote" and asserted "the excerpt above" anyway.
 *    - No title from the page. star/findings.py falls back to `entry.url` when
 *      the ledger has no title, and this file falls back to the domain; either
 *      way what is on the stamp is our derivation, not the page's own words.
 *  Copy that is true in three branches and false in the fourth is not precise
 *  copy, and precision here is the whole of obligation 3. */
function ledgerCheckCopy({ hasExcerpt, titleFromPage }) {
  const opening = "This source came back from a live search during this build.";
  // "it", not "they" — the subject is the source itself, which is the one
  // thing every branch below still has to talk about.
  const closing = "Whether it supports the fact is yours to judge.";
  let middle;
  if (titleFromPage && hasExcerpt) {
    middle =
      "Its title and the excerpt above are the page's own words as the search " +
      "returned them, not the researcher's.";
  } else if (titleFromPage) {
    middle =
      "Its title is the page's own words as the search returned it, not the " +
      "researcher's.";
  } else if (hasExcerpt) {
    middle =
      "The excerpt above is the page's own words as the search returned it, " +
      "not the researcher's. The search returned no title for it, so the line " +
      "on the stamp is this link's own address.";
  } else {
    middle =
      "The search returned neither a title nor an excerpt for it, so nothing " +
      "here is in the page's own words.";
  }
  return `${opening} ${middle} ${closing}`;
}

/** The failure, in the same register. Never softened to "could not be
 *  confirmed": the ledger knows something stronger and more specific than
 *  uncertainty — this URL was not in the set of results the researcher was
 *  handed, so nothing about it was ever checked at all. */
function unsourcedCopy(count) {
  return count === 1
    ? "This link was not among the sources the search returned to this " +
        "researcher. It is recorded here as a warning, never as a source."
    : "These links were not among the sources the search returned to this " +
        "researcher. They are recorded here as warnings, never as sources.";
}

/** Parse a candidate as an http(s) URL, or null.
 *
 *  Every citation URL in the payload came out of star/findings.py's `_URL`
 *  regex, which only matches http(s), so in practice this always succeeds —
 *  but "in practice" is not a security property. Checking the scheme here
 *  makes the guarantee local: nothing this file turns into an `href` can be a
 *  `javascript:` URL, whatever an upstream parser starts accepting later. */
function httpUrl(raw) {
  try {
    const url = new URL(String(raw));
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/** The domain on the stamp's face, per DIRECTION.md: "Domain, not full URL, on
 *  the face; the full URL is the link target." A domain is also the one piece
 *  of source-TYPE information available without reading anything — obligation
 *  7's "source type beats source count", as far as this payload supports it.
 *  `www.` is dropped because it distinguishes nothing. */
function domainOf(raw) {
  const url = httpUrl(raw);
  if (!url) return String(raw);
  return url.hostname.replace(/^www\./i, "");
}

/** Ledger excerpts arrive with the search API's own `<strong>` match
 *  highlighting and HTML entities already in them (verified against the stored
 *  Detroit-1929 room: `&quot;whiskey sixes,&quot;` and `<strong>rum runners
 *  would actually drive across…</strong>`). Escaping the whole string would
 *  print `<strong>` and `&quot;` as literal characters — technically verbatim,
 *  visibly broken, and it would hide which terms actually matched, which is
 *  real evidence about why this source was returned.
 *
 *  So it goes through DOMPurify with a deliberately tiny allowlist: emphasis
 *  only, no attributes, no links. This is untrusted third-party web content
 *  and it gets no more surface than it needs to render as a quotation. If
 *  DOMPurify failed to load, fall back to escaped text rather than raw HTML. */
function renderExcerpt(text) {
  if (window.DOMPurify) {
    return window.DOMPurify.sanitize(String(text), {
      ALLOWED_TAGS: ["strong", "em", "b", "i"],
      ALLOWED_ATTR: [],
    });
  }
  return escapeHtml(text);
}

/** One receipt: a manila fragment carrying the ledger's own record of a source.
 *
 *  Built on <details>/<summary> rather than a button plus hand-wired ARIA.
 *  Research obligation 2 says a citation that cannot be clicked through to its
 *  real excerpt is worse than no citation, and "clicked through" has to include
 *  a keyboard: <summary> is focusable, toggles on Enter and Space, exposes its
 *  own expanded state to assistive tech, and takes a :focus-visible outline —
 *  all of it native, none of it something a later edit can silently break. The
 *  outline needs a manila-surface override rather than shell.css's global one;
 *  clip.css says why.
 *
 *  `index` drives the stack offset in clip.css. It is our own loop counter, not
 *  payload data. */
function renderReceipt(citation, index, { date, code }) {
  const url = httpUrl(citation?.url);
  if (!url) return "";
  const raw = String(citation.url);
  const givenTitle = String(citation?.title || "").trim();
  // A "title" that is just the URL is not a title. star/findings.py hydrates
  // `title=entry.title or entry.url`, so a ledger entry with no title arrives
  // here carrying its own address in the title field; this file then falls
  // back to the domain. Both are our derivations, and the check copy below has
  // to know that rather than calling either one the page's own words.
  const titleFromPage = Boolean(givenTitle) && givenTitle !== raw && givenTitle !== url.href;
  const title = givenTitle || domainOf(raw);
  const excerpt = String(citation?.excerpt || "").trim();

  // Only what is actually known reaches the stamp. Task 4 established this
  // discipline for the drawer's FILED stamp — no domain was invented to fill
  // the third slot the design calls for — and the same rule holds here: a
  // caller that cannot supply the retrieval date gets a stamp with two lines,
  // not a guessed date.
  const stampLines = [`<span class="receipt-source">${escapeHtml(domainOf(raw))}</span>`];
  if (date) stampLines.push(`<span>RET ${escapeHtml(date)}</span>`);
  if (code) stampLines.push(`<span>FILED BY ${escapeHtml(code)}</span>`);
  // Joined on a newline, not concatenated. The three lines are flex items in a
  // column so a whitespace-only text node between them renders as nothing, but
  // without it the summary's accessible name comes out as one run-on string —
  // "staxmuseum.orgRET 09 AUG 2026FILED BY SET" — which is what a screen reader
  // would actually say. Caught in a browser, not by reading the template.

  return `
    <details class="receipt" style="--stack-index:${index}">
      <summary class="receipt-face">
        <span class="receipt-stamp">${stampLines.join("\n")}</span>
        <span class="receipt-title">${escapeHtml(title)}</span>
        <span class="receipt-cue">Excerpt</span>
      </summary>
      <div class="receipt-body">
        ${
          excerpt
            ? `<blockquote class="receipt-excerpt">${renderExcerpt(excerpt)}</blockquote>`
            : `<p class="receipt-excerpt receipt-excerpt-empty">The search returned this source without an excerpt. There is nothing to quote.</p>`
        }
        <p class="receipt-check">${ledgerCheckCopy({ hasExcerpt: Boolean(excerpt), titleFromPage })}</p>
        <a class="receipt-url" href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url.href)}</a>
      </div>
    </details>`;
}

/** The second pad. Oxide, angled, typographic — and the clip stays on screen.
 *
 *  Placed on the offending link rather than across the whole clip, which is a
 *  correction to the shorthand ("a finding with unverified_urls gets the second
 *  pad") and a return to what DIRECTION.md actually specifies: "A CITATION that
 *  failed the ledger check gets the other pad." The distinction is not
 *  pedantry. In the stored Detroit-1929 room the single unsourced URL in the
 *  whole build sits on a finding that ALSO carries two genuine ledger-backed
 *  citations. Stamping that clip UNSOURCED would be a false claim in the
 *  opposite direction from "verified", and this file has no licence to make
 *  either. The clip is marked (see data-unsourced in renderClip) so it is
 *  findable at a glance; the stamp names the link it belongs to. */
function renderUnsourced(urls) {
  if (!urls.length) return "";
  const items = urls
    .map((u) => `<li class="unsourced-url">${escapeHtml(String(u))}</li>`)
    .join("");
  return `
    <div class="clip-unsourced">
      <span class="clip-stamp">Unsourced</span>
      <p class="clip-stamp-note">${unsourcedCopy(urls.length)}</p>
      <ul class="unsourced-urls">${items}</ul>
    </div>`;
}

/** One clip: the fact, then its receipts.
 *
 *  No sceneNeed parameter, deliberately — see this file's header. The join the
 *  brief asks for exists only at the category level and renderSceneNeeds owns
 *  it; accepting a per-finding argument here would invite a caller to invent
 *  the link we do not have.
 *
 *  `stamp` carries { date, code } when the caller genuinely knows them. */
export function renderClip(finding, stamp = {}) {
  const fact = String(finding?.fact || "").trim();
  if (!fact) return "";
  const citations = Array.isArray(finding?.citations) ? finding.citations : [];
  const unverified = (
    Array.isArray(finding?.unverified_urls) ? finding.unverified_urls : []
  )
    .map((u) => String(u).trim())
    .filter(Boolean);

  const receipts = citations
    .map((c, i) => renderReceipt(c, i, stamp))
    .filter(Boolean)
    .join("");

  return `
    <li class="clip"${unverified.length ? ' data-unsourced="true"' : ""}>
      <p class="clip-fact">${escapeHtml(fact)}</p>
      ${receipts ? `<div class="clip-receipts">${receipts}</div>` : ""}
      ${renderUnsourced(unverified)}
    </li>`;
}

/** Every clip in one category, or an honest empty state.
 *
 *  A category with zero parsed findings is a real outcome, not an error: the
 *  researcher may have written prose the parser could not file. Saying so, and
 *  pointing at where that prose went, beats an empty panel.
 *
 *  `hasFieldNotes` exists because the pointer can be a lie. "Whatever they did
 *  write is kept below" is only true when there is something below, and there
 *  is a reachable path where there is not: star/server.py's `_build_categories`
 *  calls `parse_findings(state.get(f"findings_{c.value}"), …)`, and `.get`
 *  returns None for a category whose researcher never wrote its output_key.
 *  parse_findings(None) yields findings=[] AND field_notes="", so renderFieldNotes
 *  renders nothing and the promise points at blank card. The caller passes what
 *  it is actually about to render, not what the payload contains, so the two
 *  cannot drift. */
export function renderClips(findings, stamp = {}, { hasFieldNotes = false } = {}) {
  const list = Array.isArray(findings) ? findings : [];
  const clips = list
    .map((f) => renderClip(f, stamp))
    .filter(Boolean)
    .join("");
  if (!clips) {
    return hasFieldNotes
      ? `<p class="clip-empty">Nothing from this researcher parsed into a clip. Whatever they did write is kept below, word for word.</p>`
      : `<p class="clip-empty">Nothing from this researcher parsed into a clip, and there is no unparsed prose to show either — this category produced nothing the department could file.</p>`;
  }
  return `<ul class="clip-list">${clips}</ul>`;
}

/** Research obligation 1, and the highest-value line in the phase: the scene
 *  each question was asked for, from ResearchQuestion.why — "What scene-writing
 *  need this answers" in our own model, currently buried behind two clicks in
 *  the third tab.
 *
 *  Presented per CATEGORY because that is the only join the data supports. A
 *  category carries two to four questions and a finding carries no question id,
 *  so any per-finding line would be a guess dressed as a link. The label says
 *  what the block is; nothing here claims a specific clip answers a specific
 *  question. */
export function renderSceneNeeds(questions) {
  const items = (Array.isArray(questions) ? questions : [])
    .map((q) => {
      const question = String(q?.question || "").trim();
      const why = String(q?.why || "").trim();
      if (!question && !why) return "";
      return `
        <li class="scene-need">
          ${question ? `<p class="scene-need-question">${escapeHtml(question)}</p>` : ""}
          ${
            why
              ? // The space after the tag is load-bearing: the tag's
                // margin-right separates it visually, but with the two text
                // nodes touching, the line reads out as "For the
                // sceneEstablishes environmental realism…". Visual spacing is
                // not spacing.
                `<p class="scene-need-why"><span class="scene-need-tag">For the scene</span> ${escapeHtml(why)}</p>`
              : ""
          }
        </li>`;
    })
    .filter(Boolean)
    .join("");
  if (!items) return "";
  return `
    <div class="scene-needs">
      <p class="drawer-legend">What these findings are for</p>
      <ul class="scene-need-list">${items}</ul>
    </div>`;
}

/** Research obligation 4: show the real uncertainty data, plainly, without
 *  alarm. The differentiator is that these numbers are falsifiable — they come
 *  out of star/findings.py, not out of a confidence estimate.
 *
 *  Both lines are written to survive a hostile reading:
 *    - parse_rate's denominator is bullet lines, so it is a statement about the
 *      researcher's output FORMAT. The sentence says so out loud, because the
 *      obvious misreading ("the department is 92% accurate") is a claim we
 *      cannot support and would be caught making.
 *    - unverified_count is a count of cited links absent from the ledger. It is
 *      stated as a fact about links, not about facts.
 *  Nothing renders when there is nothing to say: a clean category should not
 *  carry a reassurance block, which would be its own kind of claim. */
export function renderUncertainty(doc) {
  const findings = Array.isArray(doc?.findings) ? doc.findings : [];
  const rate = Number(doc?.parse_rate);
  const unverified = Number(doc?.unverified_count);
  const lines = [];

  // Guarded on findings.length because parse_rate defaults to 0.0 when there
  // were no bullet lines at all (star/findings.py). "0% parsed" and "there was
  // nothing to parse" are different statements and only one of them is true.
  if (findings.length && Number.isFinite(rate) && rate > 0 && rate < 1) {
    lines.push(
      `${Math.round(rate * 100)}% of this researcher's bulleted lines parsed into clips. ` +
        "That measures the format they wrote in, not whether the facts are right. " +
        "Every line it could not read is kept below, word for word."
    );
  }
  if (Number.isFinite(unverified) && unverified > 0) {
    lines.push(
      `${plural(unverified, "cited link")} in this drawer never appeared in the ` +
        "search results this researcher received. Each one is marked on its own clip."
    );
  }
  if (!lines.length) return "";
  return `
    <div class="uncertainty">
      <p class="drawer-legend">What the department could not do cleanly</p>
      ${lines.map((l) => `<p class="uncertainty-line">${l}</p>`).join("")}
    </div>`;
}

/** field_notes, labelled as what star/models.py says it is.
 *
 *  The brief called this "the researchers' own 'verify before writing' notes".
 *  It is not that, or not only that: parse_findings puts every non-bullet line
 *  AND every bullet it could not parse into this field. Against the real
 *  Detroit-1929 room it held one genuine researcher hedge (setting: ice
 *  thickness varies by current and cannot be pinned to a date) and was empty
 *  for the other three categories — so it earns its place, but calling parser
 *  debris "calibrated uncertainty" would be the same overclaim as calling a
 *  ledger hit "verified". The label states the mechanism and lets the content
 *  be whatever it is.
 *
 *  Rendered as escaped text, not markdown: these are raw lines from a
 *  researcher's prose, and running them through a markdown parser would let a
 *  stray `#` or `[link](…)` restyle itself into something it was never meant
 *  to be. Verbatim means verbatim. */
export function renderFieldNotes(doc) {
  const notes = String(doc?.field_notes || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (!notes.length) return "";
  return `
    <div class="field-notes">
      <p class="drawer-legend">Lines the parser could not file as findings</p>
      <p class="field-notes-note">Not findings, and not dropped. A line lands here when it is not a bulleted fact carrying at least one source — a closing note on what could not be pinned down, or a line whose sources did not parse. Shown word for word.</p>
      ${notes.map((n) => `<p class="field-note">${escapeHtml(n)}</p>`).join("")}
    </div>`;
}

/** Distinct source URLs behind a category's findings.
 *
 *  Distinct, not summed: the stored Detroit-1929 room cites
 *  nmgl.org/rumrunning-detroit-river-fall-1997 on five separate logistics
 *  findings, and counting it five times would inflate "sources" into a number
 *  that flatters the run — exactly the count-over-substance move DIRECTION.md
 *  rejects. Only ledger-resolved citations count; an unverified URL is not a
 *  source and is never added here. */
export function countSources(findings) {
  const urls = new Set();
  for (const finding of Array.isArray(findings) ? findings : []) {
    for (const citation of Array.isArray(finding?.citations) ? finding.citations : []) {
      const url = httpUrl(citation?.url);
      if (url) urls.add(url.href);
    }
  }
  return urls.size;
}

/** The questions from a research plan belonging to one category.
 *
 *  Accepts either the plan object or its `questions` array, because both shapes
 *  are one property access apart at every call site and guessing wrong is a
 *  silent empty block rather than an error. Category values are the raw enum
 *  strings ("setting", "objects_props", …) on both sides of the wire — Category
 *  is a str Enum and jsonable_encoder emits its value, confirmed against the
 *  stored room. */
export function questionsForCategory(plan, category) {
  const questions = Array.isArray(plan) ? plan : plan?.questions;
  if (!Array.isArray(questions) || !category) return [];
  return questions.filter((q) => String(q?.category) === category);
}
