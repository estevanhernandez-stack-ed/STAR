// Guards the one signal that a filed room's run did not finish.
//
// THE GAP. An 8px dot was the whole of it, and it failed on both counts. Raw
// --oxide is 2.79:1 on the rail's --drawer-shadow ground and 2.37:1 once
// .rail-room.active repaints the row to --cabinet — under the 3:1 floor a
// non-text indicator has to meet, and the active row is the one the reader is
// most likely looking at. The dot is aria-hidden and .rail-room-meta rendered
// only `era · date`, so the state was carried by colour alone and reached no
// screen reader at all. WCAG 1.4.11 and 1.4.1.
//
// WHY THE RATIOS ARE COMPUTED HERE. A contrast figure in a comment is a claim
// about two tokens, and tokens move. This file reads --oxide, --manila,
// --cabinet and --drawer-shadow out of tokens.css, performs the same
// color-mix() the stylesheet asks the browser for, and computes the ratios from
// the result. Repaint a token and this fails with the real number rather than
// leaving a stale figure sitting in a comment vouching for a colour it no
// longer describes. Invariant 5 is "measured, not eyeballed", and a measurement
// that only ever ran once is closer to eyeballed than it looks.
//
// The rail half is a real render against the stage stub. The stub parses no
// HTML, so the assertions read the recorded innerHTML string — which is exactly
// what renderRail writes.
//
// Run directly: `node tests/js/test_flagged_room.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

import { loadShellModule, readShellSource, stubStageDocument } from "./_account_module.mjs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

/* ---- contrast, from the tokens themselves ------------------------------ */

const tokens = read("web/tokens.css");
function token(name) {
  const m = tokens.match(new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`));
  assert.ok(m, `--${name} should be a six-digit hex in tokens.css`);
  return m[1];
}

function luminance(hex) {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((v) =>
    v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// color-mix(in srgb, A p%, B) — sRGB is not linearised for this, so the browser
// weights the 8-bit channels directly. Same arithmetic here.
function mix(a, b, p) {
  const ch = (i) => Math.round(parseInt(a.slice(i, i + 2), 16) * p + parseInt(b.slice(i, i + 2), 16) * (1 - p));
  return "#" + [1, 3, 5].map((i) => ch(i).toString(16).padStart(2, "0").toUpperCase()).join("");
}

const OXIDE = token("oxide");
const MANILA = token("manila");
const CABINET = token("cabinet");
const SHADOW = token("drawer-shadow");
const MARKER = mix(OXIDE, MANILA, 0.7);

// The finding, still true: this is why the raw token cannot be used here.
assert.ok(
  ratio(OXIDE, SHADOW) < 3,
  `raw --oxide clears 3:1 on the rail ground now (${ratio(OXIDE, SHADOW).toFixed(2)}:1) — ` +
    `if a token moved, re-derive this fix rather than keeping a mix that is no longer needed`
);

for (const [ground, name] of [
  [SHADOW, "--drawer-shadow, the rail's own ground"],
  [CABINET, "--cabinet, the ground once .rail-room.active repaints the row"],
]) {
  const r = ratio(MARKER, ground);
  assert.ok(
    r >= 3,
    `the flagged marker is ${r.toFixed(2)}:1 on ${name}, under the 3:1 floor a ` +
      `non-text indicator has to meet`
  );
}

/* ---- the stylesheet asks for that mix, and only for .flagged ----------- */

const shellCss = read("web/shell.css");
const flagged = shellCss.match(/\.rail-room\.flagged \.rail-room-marker \{([\s\S]*?)\}/);
assert.ok(flagged, ".rail-room.flagged .rail-room-marker should still exist");
assert.match(
  flagged[1],
  /color-mix\(in srgb, var\(--oxide\) 70%, var\(--manila\)\)/,
  "the flagged dot takes the mixed shade #timeline li.error::before already uses"
);
assert.doesNotMatch(
  flagged[1],
  /background:\s*var\(--oxide\)\s*;/,
  "raw --oxide is 2.79:1 and 2.37:1 on the two grounds this dot sits on"
);

// Scoped. The other two marker states already pass on this ground —
// --manila-edge at 6.73:1 and --pencil at 4.80:1 — and repainting them would
// change two things that were never the problem.
//
// Asserted as an ABSENCE of oxide, not merely the presence of the right token.
// A second `background` prepended into either rule leaves the original
// declaration sitting there while the later one wins, so "contains
// --manila-edge" passes on a rule that no longer paints manila-edge.
for (const [selector, expected] of [
  ["\\n\\.rail-room-marker", "--manila-edge"],
  ["\\.rail-room\\.running \\.rail-room-marker", "--pencil"],
]) {
  const rule = shellCss.match(new RegExp(`${selector} \\{([\\s\\S]*?)\\}`));
  assert.ok(rule, `${selector} should still exist`);
  assert.match(rule[1], new RegExp(`background: var\\(${expected}\\)`), `${selector} keeps its token`);
  assert.doesNotMatch(
    rule[1],
    /--oxide/,
    `${selector} must not take the flagged repaint: it already clears 3:1, and ` +
      `a state that was never wrong does not get recoloured to fix another one`
  );
}
// Exactly one rule in the file paints a marker with oxide, and it is the
// flagged one. A count catches a fourth state added later without a ratio.
assert.equal(
  (shellCss.match(/\.rail-room[^{]*\.rail-room-marker \{[^}]*--oxide/g) || []).length,
  1,
  "one marker rule may use oxide, and only the one whose ratio is recorded above"
);

/* ---- and the fact is in the text, not only in the colour --------------- */

const stage = stubStageDocument();
globalThis.document = stage.document;
globalThis.__starAuth = { authedFetch: async () => ({ ok: true, json: async () => ({ rooms: [] }) }) };

const shell = await import(loadShellModule());

const ROOMS = [
  { run_id: "r-ok", title: "Filed Room", era: "1929", created_at: "2026-08-09T12:00:00+00:00", status: "complete" },
  { run_id: "r-err", title: "Broken Room", era: "1974", created_at: "2026-08-09T12:00:00+00:00", status: "error" },
  { run_id: "r-int", title: "Lost Room", era: "1978", created_at: "2026-08-09T12:00:00+00:00", status: "interrupted" },
  { run_id: "r-run", title: "Live Room", era: "", created_at: "2026-08-09T12:00:00+00:00", status: "running" },
];

shell.renderRail(ROOMS, null);

// The stub records innerHTML separately from appended children, and renderRail
// appends one button per room. Read the rows, not the container.
const rows = new Map(
  JSON.parse(stage.byId.get("rail-list").snapshot()).children.map((child) => [
    child.dataset.runId,
    child,
  ])
);
assert.equal(rows.size, 4, "one row per room");

// The two states are not synonyms: error is a run that raised, interrupted is
// store.py:241 finding a document still marked running with nothing running it.
assert.match(rows.get("r-err").innerHTML, /Stopped/, "an errored run says so in words");
assert.match(
  rows.get("r-int").innerHTML,
  /Interrupted/,
  "and an interrupted one says the other thing, because it is a different thing"
);
assert.doesNotMatch(
  rows.get("r-err").innerHTML,
  /Interrupted/,
  "one word per state — not a label applied to every flagged row"
);

// A room that filed normally says nothing extra. Without this the fix would
// read as passing while labelling every row in the rail.
assert.doesNotMatch(
  rows.get("r-ok").innerHTML,
  /Stopped|Interrupted/,
  "a room that filed says nothing extra"
);

// The status REPLACES the era rather than joining it, which the close-out
// measured as necessary: three segments wrap to a second line in a 300px rail
// at some era lengths, making a flagged row taller than its neighbours. Two
// segments on a flagged row, exactly as many as an ordinary one.
assert.doesNotMatch(
  rows.get("r-err").innerHTML,
  /1974/,
  "a flagged row drops the era: it is the weakest of the three facts, and a " +
    "run that raised may never have written a story_profile to take it from"
);
assert.match(rows.get("r-err").innerHTML, /Stopped &middot; /, "status first, then the date");
assert.equal(
  (rows.get("r-err").innerHTML.match(/&middot;/g) || []).length,
  (rows.get("r-ok").innerHTML.match(/&middot;/g) || []).length,
  "a flagged row carries the same number of segments as a filed one, so it " +
    "cannot wrap where the other does not"
);
// The era still shows on a room that filed normally.
assert.match(rows.get("r-ok").innerHTML, /1929/, "an ordinary row keeps its era");
assert.doesNotMatch(
  rows.get("r-run").innerHTML,
  /Stopped|Interrupted/,
  "and a run still going has not stopped — the flag is for finished rooms"
);

// The class and the word have to agree, or the colour and the text are
// describing different rows.
for (const [id, flagged] of [["r-ok", false], ["r-err", true], ["r-int", true], ["r-run", false]]) {
  // className, not classList: renderRail builds the whole string in one
  // assignment, which the stub records separately from classList.
  assert.equal(
    String(rows.get(id).className).split(/\s+/).includes("flagged"),
    flagged,
    `${id}: the .flagged class drives the repainted dot, and it must mark ` +
      `exactly the rows the status word marks`
  );
}

// The dot stays hidden. It repeats what the line now says, and a decoration
// that duplicates its own label is noise.
assert.match(
  rows.get("r-err").innerHTML,
  /class="rail-room-marker" aria-hidden="true"/,
  "the marker stays aria-hidden — the fix moves the fact into the text rather " +
    "than announcing a dot twice"
);

// And the flagged class is still what drives the colour, so the CSS above and
// the text here are describing the same rows.
assert.match(readShellSource(), /isFlagged \? " flagged" : ""/, "the class still marks them");

console.log("test_flagged_room.mjs: 30 assertions passed");
