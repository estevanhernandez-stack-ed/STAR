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
const IMPORT_EXCERPT_IN_CLIP = 'import { excerptProse } from "/excerpt.js";';
const IMPORT_EXCERPT_IN_CARD = 'import { excerptProse } from "/excerpt.js";';
const IMPORT_DRAWER = 'import { DRAWER_LABELS } from "/drawer.js";';

const dataUrl = (source) =>
  `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;

/** One browser module, loadable in Node, with its `/`-absolute imports pointed
 *  at the modules this file has already built.
 *
 *  Every module in the chain is the REAL one. The card's job is to show a
 *  source's own words without inventing any, and the three modules under it
 *  are what decide that: web/excerpt.js finds the prose inside a raw ledger
 *  entry, web/clip.js escapes what reaches the DOM, web/drawer.js names the
 *  four categories. A stand-in for any of them would leave this file asserting
 *  against its own fixtures — and every bug the first printed card actually
 *  had lived in exactly those three seams. */
function browserModule(path, rewrites) {
  let source = read(path);
  for (const [importLine, replacement] of rewrites) {
    assert.equal(
      source.split(importLine).length - 1,
      1,
      `${path} should contain ${JSON.stringify(importLine)} exactly once — ` +
        "update this loader if the source changed shape"
    );
    source = source.replace(importLine, replacement);
  }
  return dataUrl(source);
}

const CLIP = browserModule("web/clip.js", [
  [
    IMPORT_EXCERPT_IN_CLIP,
    `import { excerptProse } from ${JSON.stringify(EXCERPT.href)};`,
  ],
]);
const DRAWER = browserModule("web/drawer.js", [
  ['from "/clip.js";', `from ${JSON.stringify(CLIP)};`],
]);

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
    .replace(IMPORT_CLIP, `import { escapeHtml, isoStamp } from ${JSON.stringify(CLIP)};`)
    .replace(
      IMPORT_EXCERPT_IN_CARD,
      `import { excerptProse } from ${JSON.stringify(EXCERPT.href)};`
    )
    .replace(IMPORT_DRAWER, `import { DRAWER_LABELS } from ${JSON.stringify(DRAWER)};`);
  // Checked by absence rather than by counting replacements: a new
  // browser-root import added to the card later would otherwise sail through
  // this loader and fail as a module-resolution error two frames deep.
  assert.doesNotMatch(
    patched,
    /from "\/[a-z]+\.js"/,
    "every browser-root import should have been rewritten — update this loader"
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

/* 8 — the three things the first printed card got wrong. ----------------- */
//
// A real card off the Substitute Sync room, printed to PDF, carried all three:
// a raw category key across its masthead, nine hundred words of forum thread
// where a quotation should be, and `&#x27;` in the middle of a sentence. None
// of them were reachable from a fixture — the card was assembled correctly
// from data nobody had looked at through this surface.

const messy = await renderWith({
  ...CARD,
  category: "objects_props",
  sources: [
    {
      url: "https://www.beatlesbible.com/forum/yesterday-and-today/beatle-boots/",
      title: "Beatle Boots | Fab Forum",
      // The shape a scraped forum page actually arrives in: a markdown
      // heading, then the sentence worth quoting, then the thread's furniture.
      excerpt:
        "# Beatle Boots | Fab Forum | The Beatles Bible\n\n" +
        "Their boots were custom made by Anello & Davide, who still make them " +
        "but only sell custom products, nothing ready to wear.\n\n" +
        "The following people thank Pablo Ramon for this post: " +
        "SgtPeppersBulldog, WeepingAtlasCedars, Leppo 7 February 2017 11.04am\n" +
        "[sp_Permalink](https://www.beatlesbible.com/forum/beatle-boots/)",
    },
    {
      url: "https://www.bonhams.com/auction/19801/lot/304/",
      title: "Bonhams : George Harrison / The Beatles",
      excerpt: "Following the group&#x27;s phenomenal rise to stardom in 1963.",
    },
  ],
});

assert.match(messy.prose, /Objects &amp; Props drawer/, "the drawer's name, not its key");
assert.doesNotMatch(messy.html, /objects_props/i, "a storage key never reaches the sheet");

assert.match(
  messy.prose,
  /custom made by Anello &amp; Davide/,
  "the sentence worth quoting survives"
);
assert.doesNotMatch(
  messy.html,
  /sp_Permalink|SgtPeppersBulldog|The following people thank/,
  "and the thread's furniture does not — web/excerpt.js finds where the prose " +
    "starts, which is the whole reason it exists"
);
assert.doesNotMatch(messy.html, /^#|\n#/, "no markdown heading on a printed sheet");

assert.match(
  messy.prose,
  /group's phenomenal rise/,
  "an entity in the source is a character on the sheet"
);
assert.doesNotMatch(
  messy.html,
  /&amp;#x27;/,
  "and never the entity itself, printed as text on a page handed to somebody"
);

console.log("ok - the defence card shows one fact's provenance and nothing it cannot show");
