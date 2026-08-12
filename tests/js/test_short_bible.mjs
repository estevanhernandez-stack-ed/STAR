// A bible that stops early says so above itself, in the reader's own view.
//
// THE BUG. A room reports "complete" when the pipeline reached its end, which
// is not the same claim as "the bible is whole". Seven of the fourteen rooms
// stored on 2026-08-11 carried a bible missing at least one section, most of
// them stopping mid-word inside section one. The web app rendered whatever text
// there was under an unqualified "The research bible" heading, so a reader
// found out by scrolling to a sentence that just ends, with no way to tell a
// short bible from a short subject.
//
// WHY THIS IS A SOURCE TEST. Same reason as the other app.js guards: the file
// takes its element references at module evaluation and wires listeners at
// import, so it does not load against the stub in _scriptcheck_module.mjs.
//
// What this file proves:
//   1. The note is rendered above the document, not after it.
//   2. The COUNT IS THE SERVER'S. star/bible.py measures coverage once and
//      ships it in the payload; this file reads `result.bible_coverage` and
//      never recomputes it. A second implementation of one fact in a second
//      language is exactly how web/consent.js came to say "four calls" on the
//      day a fifth tool shipped, and that defect is the reason this rule is
//      worth a test rather than a comment.
//   3. A whole bible renders exactly as it always did — no note, no wrapper.
//   4. The section names in this repo's two languages agree. web/drawer.js
//      names the four drawers, star/models.py names the four bible sections,
//      and the check that a section is missing is meaningless if the two lists
//      drift apart.
//   5. Section names reach the DOM escaped, like every other server string.
//
// Run directly: `node tests/js/test_short_bible.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8");

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const app = stripComments(read("web/app.js"));
const css = read("web/bible.css");

/* 1 — the note is above the document. ----------------------------------- */

const renderBible = app.match(/function renderBible\(result, status\) \{([\s\S]*?)\n\}/);
assert.ok(renderBible, "renderBible should exist");

const notedAt = renderBible[1].indexOf("shortBibleNote(result)");
const bodyAt = renderBible[1].indexOf("bibleHtml(markdown)");
assert.ok(notedAt > -1, "the filed-bible branch should render the short-bible note");
assert.ok(
  notedAt < bodyAt,
  "the note belongs above the document — its whole purpose is that a reader " +
    "learns the bible stops early before reading it, not after"
);

/* 2 — the count comes from the server, and is not recomputed here. ------ */

const note = app.match(/function shortBibleNote\(result\) \{([\s\S]*?)\n\}/);
assert.ok(note, "shortBibleNote should exist");

assert.match(
  note[1],
  /result\.bible_coverage/,
  "the count should be read off the payload star/bible.py already measured"
);
assert.doesNotMatch(
  note[1],
  /research_bible|categories|match\(|split\(/,
  "this function must not re-measure the bible — one fact, one implementation"
);
assert.doesNotMatch(
  note[1],
  /\b(?:four|4) drawers\b/,
  "and must not type a count it was handed"
);

// Quiet when there is nothing to say, and that is now two conditions rather
// than one: no measurement at all, and a bible with every section that also
// finished cleanly. An empty paragraph above a healthy document is worse than
// no note, because a reader takes any note as a warning.
assert.match(
  note[1],
  /if \(!counts \|\| !counts\.missing\) return "";/,
  "a room with no measurement should render nothing"
);
assert.match(
  note[1],
  /if \(!counts\.truncated\) return "";/,
  "and so should a whole bible that finished — the zero-missing branch has to " +
    "stay quiet unless the run itself reported being cut off"
);

// The third case, which counting sections cannot see: every section present
// and the document still stopped mid-sentence. Only rooms built since the
// editor's finish reason started being recorded can report it.
assert.match(
  note[1],
  /counts\.truncated[\s\S]*?stopped before it finished/,
  "a bible that reached every section and still got cut off should say so"
);
assert.doesNotMatch(
  note[1].split("counts.missing.length === 0")[1]?.split("}")[0] || "",
  /is short/,
  "and must not call it short — nothing is missing, so the reader has no list " +
    "to be given and 'short' would send them looking for absent sections"
);

/* 3 — the escaping every server string in this file already gets. ------- */

assert.match(
  note[1],
  /counts\.missing\.map\(escapeHtml\)/,
  "section names are server strings and go through escapeHtml like the rest"
);

/* 3b — the seam: the key this file reads is the key the server writes. --- */
//
// This assertion exists because its absence shipped. The server attached the
// measurement at the TOP LEVEL of the response, this file read it off the
// room, and both source tests passed — the Python test asserted
// `body["bible_coverage"]`, this one asserted `result.bible_coverage`, and
// neither could see the other's path. The live page rendered no note at all.
// Two green suites either side of a contract neither one crosses is not
// coverage, so the crossing is checked here, in the file that has to read
// both languages anyway.

const serverPy = read("star/server.py");
assert.match(
  serverPy,
  /result\["bible_coverage"\] = counts/,
  "the server must attach the measurement INSIDE the room payload — that is " +
    "the object renderBible receives, and putting it beside the room instead " +
    "is invisible to every source test on both sides of the wire"
);

/* 4 — the two languages name the same four sections. -------------------- */

const drawerLabels = read("web/drawer.js").match(
  /export const DRAWER_LABELS = \{([\s\S]*?)\};/
);
assert.ok(drawerLabels, "web/drawer.js should still export DRAWER_LABELS");

const sectionTitles = read("star/models.py").match(
  /SECTION_TITLES: dict\[Category, str\] = \{([\s\S]*?)\}/
);
assert.ok(sectionTitles, "star/models.py should still define SECTION_TITLES");

const jsNames = [...drawerLabels[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
const pyNames = [...sectionTitles[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();

assert.deepEqual(
  jsNames,
  pyNames,
  "the drawer labels and the bible section titles must be the same four " +
    "strings — a section is judged missing by matching these names against " +
    "the document, so a rename on one side alone marks every healthy room short"
);

/* 5 — the note is styled as copy, off a measured pair. ------------------ */

assert.match(
  css,
  /\.bible-note,\n\.bible-short \{/,
  "the short-bible note shares .bible-note's rule: one measured contrast pair " +
    "for the two notes, and neither can drift into looking like a different " +
    "kind of statement"
);
assert.match(
  css,
  /8\.45:1 {2}\.bible-note,\n {54}\.bible-short/,
  "and the contrast table names it, because a header documenting values the " +
    "file does not ship is the defect this stylesheet was written against"
);

console.log("ok - a short bible says so, once, in one language");
