// The defence card renders one fact's provenance, and nothing it cannot show.
//
// WHAT THIS FILE IS FOR. The card is the sheet a writer hands to whoever is
// challenging a detail, so its failure mode is not a broken layout — it is
// printing something that reads as more than the department can honestly say.
// Three properties matter and all three are asserted against rendered HTML:
//
//   1. The narrow claim survives. Every card carries the sentence that scopes
//      what a citation proves, because a cited answer is trusted MORE even when
//      it is wrong, and a sheet of sources with no scope line reads as an
//      endorsement of the fact above them.
//   2. A url the ledger never returned is printed as unsourced, in its own
//      block, told not to cite. The one place it must not quietly vanish is
//      the sheet somebody is about to cite from.
//   3. Nothing on the sheet is a guess. No excerpt invented where the ledger
//      held none, no title fabricated from a url, no retrieval date defaulted.
//
// NOT A SOURCE TEST. web/defend.js is loaded for real with its two imports
// rewritten — /auth.js to a stub this file owns, /clip.js to the real module —
// against a DOM stub small enough to read.
//
// Run directly: `node tests/js/test_defence_card.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");
const EXCERPT = pathToFileURL(fileURLToPath(new URL("web/excerpt.js", REPO_ROOT)));

const IMPORT_AUTH = 'import { authedFetch } from "/auth.js";';
const IMPORT_CLIP = 'import { escapeHtml, isoStamp } from "/clip.js";';
const IMPORT_EXCERPT = 'import { excerptProse } from "/excerpt.js";';

const dataUrl = (source) =>
  `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;

// web/clip.js is loaded FOR REAL, with only its own browser-root import
// rewritten. escapeHtml and isoStamp are what the card escapes and formats
// with, and a stand-in would prove nothing about either — the escaping is what
// keeps a source title from reaching the sheet as markup, and the formatting
// is the retrieval-date rule this card is most exposed to.
const clipSource = read("web/clip.js");
assert.equal(
  clipSource.split(IMPORT_EXCERPT).length - 1,
  1,
  "web/clip.js should import /excerpt.js exactly once — update this loader"
);
const CLIP = dataUrl(
  clipSource.replace(
    IMPORT_EXCERPT,
    `import { excerptProse } from ${JSON.stringify(EXCERPT.href)};`
  )
);

// The card, as star/defence.py builds it. Keys here mirror that function; a
// drift between the two shows up as an assertion below going quiet rather
// than red, which is why every assertion checks for PRESENCE of real text.
const CARD = {
  run_id: "abc123",
  room: { title: "BROWNOUT", era: "Summer 1977", genre: "Crime" },
  category: "logistics",
  fact: "Night court sat until 4 AM during the blackout.",
  retrieved_at: "2026-08-09T12:00:00Z",
  filed_by: "build",
  requisition: "",
  sources: [
    {
      url: "https://example.org/court",
      title: "Night Court Records",
      excerpt: "The court sat until four in the morning.",
    },
  ],
  unsourced_urls: [],
};

/* A DOM stub that does exactly what web/defend.js touches and no more. ---- */

function makeElement() {
  const el = {
    innerHTML: "",
    listeners: {},
    querySelector() {
      // One control, and only after render() has written it. Returning a live
      // object regardless would let a test pass against a card that never drew
      // the print button.
      return el.innerHTML.includes("defence-print")
        ? { addEventListener: (type, fn) => (el.listeners[type] = fn) }
        : null;
    },
  };
  return el;
}

async function renderWith(card, { status = 200, url = "?run=abc123&fact=Night%20court" } = {}) {
  const sheet = makeElement();
  let printed = false;

  globalThis.window = {
    location: { search: url },
    print: () => (printed = true),
  };
  globalThis.document = {
    title: "",
    getElementById: (id) => (id === "sheet" ? sheet : null),
  };
  globalThis.__fetch = async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => card,
  });

  const patched = read("web/defend.js")
    .replace(IMPORT_AUTH, "const authedFetch = (...a) => globalThis.__fetch(...a);")
    .replace(IMPORT_CLIP, `import { escapeHtml, isoStamp } from ${JSON.stringify(CLIP)};`);
  assert.ok(
    !patched.includes('"/auth.js"') && !patched.includes('"/clip.js"'),
    "both imports should have been rewritten — update this loader if the source changed"
  );

  // Cache-busted so each scenario re-evaluates the module: web/defend.js runs
  // main() at import, and a cached module would render the first card forever.
  await import(dataUrl(`${patched}\n//${Math.random()}`));
  await new Promise((r) => setTimeout(r, 0));
  // `prose` is the sheet with every run of whitespace collapsed. The card is
  // built from template literals wrapped for reading, so its rendered text
  // carries newlines and indentation mid-sentence; a literal-space pattern
  // then passes or fails on where a line happened to break, which is a fact
  // about this source file and not about what the sheet says. `html` stays for
  // the assertions that are genuinely about markup.
  return {
    html: sheet.innerHTML,
    prose: sheet.innerHTML.replace(/\s+/g, " "),
    sheet,
    printed: () => printed,
  };
}

/* 1 — the fact, its source, and the scope of what that proves. ------------ */

const built = await renderWith(CARD);

assert.match(built.html, /Night court sat until 4 AM/, "the fact being argued about");
assert.match(built.html, /example\.org\/court/, "the address, as text a printed page keeps");
assert.match(built.html, /four in the morning/, "the page's own words");
assert.match(built.html, /RET|retrieved 09 AUG 2026|09 AUG 2026/, "when the source came back");
assert.match(
  built.prose,
  /judgement it does not make on your behalf/,
  "THE SCOPE LINE. A sheet of sources without it reads as the department " +
    "endorsing the fact, which is the failure the aversion research documents"
);
assert.match(built.prose, /none of them were written by a model/, "the narrow claim, stated");
assert.match(built.html, /defence-print/, "and the control the whole page exists for");

/* 2 — a requisitioned fact says so, and dates itself. --------------------- */

const asked = await renderWith({
  ...CARD,
  filed_by: "requisition",
  requisition: "how long did arraignment take",
  retrieved_at: "2026-08-12T05:00:00Z",
});

assert.match(asked.html, /Researched on request/, "how this fact got into the room");
assert.match(asked.html, /how long did arraignment take/, "and what was asked");
assert.match(asked.html, /12 AUG 2026/, "dated when ITS sources came back");
assert.doesNotMatch(asked.html, /09 AUG 2026/, "never the room's build date");
assert.match(asked.prose, /after this room was built/, "said plainly, not left to the date");

/* 3 — an unsourced url is printed and warned about. ----------------------- */

const flagged = await renderWith({
  ...CARD,
  unsourced_urls: ["https://example.org/never-returned"],
});

assert.match(flagged.html, /do not cite/i, "the instruction, on the sheet being cited from");
assert.match(flagged.html, /never-returned/, "and the address itself, not just a count");
assert.match(flagged.prose, /never appeared in a search result/, "why it is flagged");

/* 4 — nothing is invented where the ledger held nothing. ------------------ */

const bare = await renderWith({
  ...CARD,
  sources: [{ url: "https://example.org/court", title: "https://example.org/court", excerpt: "" }],
});

assert.match(bare.prose, /ledger holds no quotation/, "says there is no quote");
assert.doesNotMatch(bare.html, /defence-excerpt/, "rather than printing empty quote marks");
// The url appears twice by design — once as the href, once as the link's own
// text, so a printed sheet carries the address as words. What must NOT appear
// is a title line: star/findings.py falls back to the url when the ledger held
// no title, and printing that as the source's name would present our fallback
// as the page's own words.
assert.doesNotMatch(
  bare.html,
  /defence-source-title/,
  "a title identical to the url is not a title, and is not printed as one"
);

/* 5 — a fact with nothing behind it is named as such. --------------------- */

const nothing = await renderWith({ ...CARD, sources: [] });

assert.match(nothing.prose, /Nothing is filed behind this fact/);
assert.match(
  nothing.prose,
  /should not go in front of anyone who might ask/,
  "the warning is the product here — a card with no sources is the one a " +
    "writer most needs stopping over"
);

/* 6 — a card that cannot be fetched says which failure it was. ------------ */

const missing = await renderWith(CARD, { status: 404 });
assert.match(missing.prose, /not filed under this account|No finding in this room/);
assert.doesNotMatch(missing.html, /404/, "no status codes on a page a stranger may hold");

const incomplete = await renderWith(CARD, { url: "?run=abc123" });
assert.match(incomplete.html, /incomplete/, "a hand-built link says so");
assert.doesNotMatch(incomplete.html, /Night court/, "and renders no card");

/* 7 — the link that reaches this card at all. ---------------------------- */
//
// The sheet is unreachable from the app without it, and a card nobody can open
// is not a feature. Asserted here rather than in the clip's own tests because
// this is the only file that knows what the link is FOR.

const clip = await import(CLIP);
const FINDING = {
  fact: "Night court sat until 4 AM during the blackout.",
  citations: [{ url: "https://example.org/court", title: "Courts", excerpt: "A quote." }],
  unverified_urls: [],
};

const linked = clip.renderClips([FINDING], { date: "09 AUG 2026" }, { runId: "abc123" });
assert.match(linked, /clip-defend-link/, "every filed fact offers its own card");
assert.match(linked, /\/defend\.html\?run=abc123/, "pointed at the room it came from");
assert.match(
  linked,
  /fact=Night%20court%20sat/,
  "and carrying the fact, which is how star/defence.py finds it again — no " +
    "index into a drawer that a later requisition would shift"
);

// A live run has findings on screen before the room has an id. A link built on
// an empty run id would 404 on a fact the reader is looking at.
const live = clip.renderClips([FINDING], { date: "09 AUG 2026" }, {});
assert.doesNotMatch(live, /clip-defend/, "and no link before there is a room to point at");

console.log("ok - the defence card shows one fact's provenance and nothing it cannot show");
