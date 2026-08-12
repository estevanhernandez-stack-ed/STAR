// A finding added after the room was built stamps its OWN retrieval date.
//
// THE BUG THIS CLOSES. The drawer carries one retrieval date for every citation
// in it — the room's `created_at`, which is when the build's searches ran and is
// the honest answer for every finding a build filed. `research_question` breaks
// that assumption: it files a finding into a room that already exists, and its
// sources came back when the writer asked, which may be days later. Rendering
// the room's date on it would print a retrieval claim the sources never had, on
// the one element whose entire job is provenance — the exact substitution
// web/drawer.js's `retrieved` note refuses to make for the FILED date.
//
// NOT A SOURCE TEST. web/clip.js has one import (/excerpt.js) and no DOM
// dependency at module scope, so it loads for real here with that import
// rewritten to the real file on disk. Every assertion below is about HTML this
// renderer actually produced, not about text in a file.
//
// Run directly: `node tests/js/test_requisition_stamp.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const SOURCE = new URL("web/clip.js", REPO_ROOT);
const EXCERPT = pathToFileURL(fileURLToPath(new URL("web/excerpt.js", REPO_ROOT)));

const IMPORT_EXCERPT = 'import { excerptProse } from "/excerpt.js";';

const original = readFileSync(SOURCE, "utf8").replace(/\r\n/g, "\n");
assert.equal(
  original.split(IMPORT_EXCERPT).length - 1,
  1,
  "web/clip.js should import /excerpt.js exactly once — update this loader if " +
    "the source changed shape"
);

// The one global web/clip.js reaches for: `window.DOMPurify`, checked before
// use and absent here on purpose. With no sanitiser the renderer takes its
// escaped-text branch, which is the conservative one and is not what these
// assertions are about — every one of them is about the RET line.
globalThis.window = {};

const patched = original.replace(
  IMPORT_EXCERPT,
  `import { excerptProse } from ${JSON.stringify(EXCERPT.href)};`
);
const clip = await import(
  `data:text/javascript;base64,${Buffer.from(patched, "utf8").toString("base64")}`
);

const SOURCED = [{ url: "https://example.org/court", title: "Courts", excerpt: "A quote." }];

/* 1 — a build's finding wears the drawer's date. ------------------------- */

const built = clip.renderClips(
  [{ fact: "Arraignments were slow.", citations: SOURCED, unverified_urls: [] }],
  { date: "09 AUG 2026", code: "LOG" }
);

assert.match(built, /RET 09 AUG 2026/, "the room's date, which is its own searches'");

/* 2 — a requisitioned finding wears its own. ----------------------------- */

const asked = clip.renderClips(
  [
    {
      fact: "Arraignments ran 48 to 72 hours behind.",
      citations: SOURCED,
      unverified_urls: [],
      requisition: "how long did arraignment take",
      retrieved_at: "2026-08-12T05:00:00+00:00",
    },
  ],
  { date: "09 AUG 2026", code: "LOG" }
);

assert.match(asked, /RET 12 AUG 2026/, "the date ITS sources came back");
assert.doesNotMatch(
  asked,
  /RET 09 AUG 2026/,
  "and never the room's, which would be a retrieval claim these sources never " +
    "had — the finding was filed three days after the room was built"
);

/* 3 — both in one drawer, each with its own. ----------------------------- */

const mixed = clip.renderClips(
  [
    { fact: "Built.", citations: SOURCED, unverified_urls: [] },
    {
      fact: "Asked for.",
      citations: SOURCED,
      unverified_urls: [],
      retrieved_at: "2026-08-12T05:00:00+00:00",
    },
  ],
  { date: "09 AUG 2026", code: "LOG" }
);

assert.match(mixed, /RET 09 AUG 2026/, "the built one keeps the room's date");
assert.match(mixed, /RET 12 AUG 2026/, "the asked-for one keeps its own");
assert.ok(
  mixed.indexOf("RET 09 AUG 2026") < mixed.indexOf("RET 12 AUG 2026"),
  "and they stay attached to their own findings, in the order rendered"
);

/* 4 — an unparseable date drops the line rather than inventing one. ------ */

for (const bad of ["not-a-date", "", null, undefined]) {
  const rendered = clip.renderClips(
    [{ fact: "F.", citations: SOURCED, unverified_urls: [], retrieved_at: bad }],
    { code: "LOG" }
  );
  assert.doesNotMatch(
    rendered,
    /RET /,
    `retrieved_at=${JSON.stringify(bad)} with no drawer date should print no ` +
      "RET line at all — the same refusal renderFiled makes rather than " +
      "fabricating a domain for its third slot"
  );
}

/* 5 — a bad own-date falls back to the drawer's, not to nothing. --------- */

const fallback = clip.renderClips(
  [{ fact: "F.", citations: SOURCED, unverified_urls: [], retrieved_at: "not-a-date" }],
  { date: "09 AUG 2026", code: "LOG" }
);
assert.match(
  fallback,
  /RET 09 AUG 2026/,
  "an unreadable per-finding date is not evidence the drawer's date is wrong"
);

console.log("ok - a requisitioned finding stamps the date its own sources came back");
