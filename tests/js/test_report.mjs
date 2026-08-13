// The sweep report: what a writer prints and hands over.
//
// WHAT IS AT RISK. This sheet leaves the app. Whoever reads it is usually not
// at the writer's screen and cannot click anything, so every failure mode is
// permanent by the time it is noticed:
//
//   1. A verdict printed without its sources. The sweep surface shipped
//      exactly that once and it was the worst defect of the night — on paper
//      it is worse again, because the screen at least had a link to nowhere.
//   2. The lines to act on buried under the sixty that are fine.
//   3. The scope line missing, so a page of stamps reads as the department
//      vouching for a draft.
//
// NOT A SOURCE TEST. web/report.js is loaded for real with its three imports
// rewritten, against a DOM stub small enough to read.
//
// Run directly: `node tests/js/test_report.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");
const EXCERPT = pathToFileURL(fileURLToPath(new URL("web/excerpt.js", REPO_ROOT)));

const dataUrl = (source) =>
  `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;

// The real clip.js, with only its own browser-root import rewritten: it owns
// the escaping that keeps a writer's draft from reaching the DOM as markup.
const CLIP = dataUrl(
  read("web/clip.js").replace(
    'import { excerptProse } from "/excerpt.js";',
    `import { excerptProse } from ${JSON.stringify(EXCERPT.href)};`
  )
);

const SWEEP = {
  sweep_id: "sw1",
  created_at: "2026-08-12T22:00:00Z",
  room: { title: "Doctor Who: Liverpool and Hamburg", era: "1958-1962" },
  scenes_read: 24,
  claims_raised: 85,
  search_count: 4,
  budget_exhausted: false,
  claims: [
    {
      text: "Kaiserkeller",
      verdict: "confirmed",
      scenes: [13, 17],
      note: "Music venue at 36 Große Freiheit.",
      citations: [
        {
          url: "https://en.wikipedia.org/wiki/Kaiserkeller",
          title: "Kaiserkeller",
          excerpt: "The club opened in 1959 on Große Freiheit.",
        },
      ],
    },
    {
      text: "turning it up to eleven",
      verdict: "anachronism",
      scenes: [19],
      note: "Coined in the 1984 film This Is Spinal Tap.",
      citations: [
        { url: "https://tap.example/eleven", title: "Spinal Tap", excerpt: "Released 1984." },
      ],
    },
    { text: "Ta.", verdict: "unverifiable", scenes: [5], note: "No source named." },
  ],
};

function makeSheet() {
  return { innerHTML: "", listeners: {}, querySelector: () => null };
}

async function renderWith(sweep, { status = 200, url = "?run=r1&sweep=sw1" } = {}) {
  const sheet = makeSheet();
  globalThis.window = { location: { search: url }, print: () => {} };
  globalThis.document = { title: "", getElementById: (id) => (id === "sheet" ? sheet : null) };
  globalThis.__fetch = async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => sweep,
  });

  const patched = read("web/report.js")
    .replace(
      'import { authedFetch } from "/auth.js";',
      "const authedFetch = (...a) => globalThis.__fetch(...a);"
    )
    .replace(
      'import { escapeHtml, isoStamp } from "/clip.js";',
      `import { escapeHtml, isoStamp } from ${JSON.stringify(CLIP)};`
    )
    .replace(
      'import { excerptProse } from "/excerpt.js";',
      `import { excerptProse } from ${JSON.stringify(EXCERPT.href)};`
    );
  assert.doesNotMatch(
    patched,
    /from "\/[a-z]+\.js"/,
    "every browser-root import should be rewritten — update this loader"
  );

  await import(dataUrl(`${patched}\n//${Math.random()}`));
  await new Promise((r) => setTimeout(r, 0));
  return { html: sheet.innerHTML, prose: sheet.innerHTML.replace(/\s+/g, " ") };
}

/* 1 — the sheet names its room and its numbers. -------------------------- */

const printed = await renderWith(SWEEP);

assert.match(printed.html, /Doctor Who: Liverpool and Hamburg/, "which room");
assert.match(printed.html, /1958-1962/, "and which era");
assert.match(printed.html, /12 AUG 2026/, "and when it was swept");
assert.match(printed.prose, /24 scenes read/);
assert.match(printed.prose, /85 claims raised, 3 distinct/, "both numbers");
assert.match(printed.prose, /4 live searches/, "and what it cost");

/* 2 — the lines to act on lead. ------------------------------------------ */

const anachronism = printed.html.indexOf("anachronism");
const confirmed = printed.html.indexOf("confirmed");
assert.ok(
  anachronism > -1 && confirmed > -1 && anachronism < confirmed,
  "ANACHRONISMS FIRST. On a page somebody prints in order to DO something, " +
    "the thing to do leads — a report in the draft's own order buries the two " +
    "lines that need changing under sixty that are fine"
);
assert.match(printed.prose, /turning it up to eleven/);
assert.match(printed.prose, /lines to look at first/, "and says why they lead");

/* 3 — every verdict carries its sources. --------------------------------- */

assert.match(printed.html, /en\.wikipedia\.org\/wiki\/Kaiserkeller/, "the address as text");
assert.match(printed.prose, /opened in 1959/, "and the page's own words");
assert.match(printed.html, /tap\.example\/eleven/, "for the anachronism too");
assert.match(
  printed.prose,
  /No source is filed behind this claim/,
  "and a claim with nothing behind it says so rather than printing an empty space"
);
assert.match(
  printed.prose,
  /reading of the sources printed under it, not a check of the line against the world/,
  "THE SCOPE LINE. A page of stamps without it reads as the department " +
    "vouching for the draft"
);

/* 4 — which pages to open. ----------------------------------------------- */

assert.match(printed.prose, /scene 13, 17/, "a claim names every scene that made it");
assert.match(printed.prose, /scene 19/);

/* 5 — a budget that ran out is on the sheet. ----------------------------- */

const short = await renderWith({ ...SWEEP, budget_exhausted: true });
assert.match(short.prose, /reached its search limit/);
assert.match(
  short.prose,
  /not the same as not being there/,
  "because 'we ran out of searches' and 'we looked and it is not there' are " +
    "answers a writer is owed apart"
);

/* 6 — an unknown verdict still prints. ----------------------------------- */

const odd = await renderWith({
  ...SWEEP,
  claims: [{ text: "something", verdict: "surprising", scenes: [2] }],
});
assert.match(
  odd.prose,
  /something/,
  "a claim dropped for wearing an unexpected stamp is a claim the writer paid " +
    "for and never saw"
);

/* 7 — the failures a reader can act on. ---------------------------------- */

const incomplete = await renderWith(SWEEP, { url: "?run=r1" });
assert.match(incomplete.prose, /incomplete/);
assert.doesNotMatch(incomplete.prose, /Kaiserkeller/, "and renders no report");

const missing = await renderWith(SWEEP, { status: 404 });
assert.match(missing.prose, /not filed under this account/);
assert.doesNotMatch(missing.prose, /404/, "no status codes on a page a stranger may hold");

console.log("ok - the sweep report prints what a writer can hand over");
