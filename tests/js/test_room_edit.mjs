// Naming a room, and saying which room it follows.
//
// THE BUG. "Untitled room" was a permanent fate. star/store.py wrote it and no
// rename path existed anywhere, so a build whose intake found no title produced
// a room that could never be called anything else. The judge's round-two review
// filed it under room hygiene: three Untitled rooms and an errored husk, with
// no way to clean any of it up over either door.
//
// WHY THIS IS A SOURCE TEST. web/app.js takes eleven element references at
// module evaluation and wires listeners at import, so it does not load against
// the stub in _scriptcheck_module.mjs. Every assertion below is a statement
// about source text, and the live-DOM checkpoint owns whether the panel
// actually renders and saves.
//
// What this file proves:
//   1. The panel exists in the markup, ships hidden, and its control says so
//      through aria-expanded as well as through its own label.
//   2. The title cap is READ FROM THE SERVER, never typed here.
//   3. The heading is written from what came back, not from what was typed.
//   4. A refusal shows the server's own sentence rather than a generic one.
//   5. The panel closes when the reader opens a different room.
//   6. A parent no longer in the rail is SAID, not silently cleared.
//   7. The seam: the keys this file sends are the keys the endpoint reads.
//
// Run directly: `node tests/js/test_room_edit.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) =>
  // Normalised at read: working copies are CRLF and CI is not, so a pattern
  // anchored to a newline passes on one checkout and fails on another. This
  // file shipped without it and went red the first time git handed the
  // source back with CRLF.
  readFileSync(new URL(path, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const app = stripComments(read("web/app.js"));
const html = read("web/index.html");
const css = read("web/shell.css");
const serverPy = read("star/server.py");

/* 1 — the panel ships hidden, and the control announces its state. --------- */

assert.match(
  html,
  /<div id="room-edit" class="room-edit hidden">/,
  "the edit panel should ship hidden — a room already named right should not " +
    "carry an open form about naming"
);
assert.match(
  html,
  /id="room-edit-btn"[\s\S]{0,120}aria-expanded="false"[\s\S]{0,120}aria-controls="room-edit"/,
  "the control should name the panel it opens and start collapsed"
);
assert.match(
  app,
  /roomEditBtn\.setAttribute\("aria-expanded"/,
  "and should keep aria-expanded true to what the panel is actually doing — a " +
    "control whose only feedback is an ARIA attribute nobody updates is worse " +
    "than one with none"
);

/* 2 — the cap comes from the server. -------------------------------------- */

assert.match(
  app,
  /input\.maxLength = LIMITS\.roomTitleChars;/,
  "the title cap should be read from the served config"
);
assert.doesNotMatch(
  app,
  /maxLength = \d+/,
  "and never typed here: a cap duplicated across two languages is two sources " +
    "of truth, and only one of them ever moves"
);

/* 3 — the heading shows what the room now carries. ------------------------- */

const save = app.match(/roomEditSave\.addEventListener\("click",[\s\S]*?\n {2}\}\);/);
assert.ok(save, "the save handler should exist");

assert.match(
  save[0],
  /const saved = await response\.json\(\);[\s\S]{0,200}\$\("result-title"\)\.textContent = saved\.title/,
  "the heading should be written from the reply, not the input — an empty name " +
    "restores the derived one, so the two differ, and printing what was typed " +
    "would leave the heading disagreeing with the rail"
);

/* 4 — a refusal keeps the server's own words. ------------------------------ */

assert.match(
  save[0],
  /\(await response\.json\(\)\)\.detail/,
  "a refusal should show the server's sentence; each one names what failed and " +
    "what to do next, and replacing them with a generic line throws away the " +
    "only part a reader can act on"
);

/* 5 — the panel does not follow the reader between rooms. ------------------ */

const showResults = app.match(/async function showResults\(runId\) \{([\s\S]*?)\n\}/);
assert.ok(showResults, "showResults should exist");
assert.match(
  showResults[1],
  /closeRoomEdit\(\);/,
  "opening a room should close the panel — a half-typed name for one room " +
    "sitting over another room's heading is the app losing track of the reader"
);

/* 6 — a parent that is gone is said, not silently dropped. ----------------- */

const fill = app.match(/function fillRoomEdit\(result\) \{([\s\S]*?)\n\}/);
assert.ok(fill, "fillRoomEdit should exist");
assert.match(
  fill[1],
  /no longer filed/,
  "a link whose room has been purged should say so rather than reset to " +
    "nothing — dropping a link a writer drew, without telling them, is the app " +
    "editing their work on their behalf"
);
assert.match(
  fill[1],
  /if \(room\.run_id === openRoomId\) continue;/,
  "and the list should not offer this room as its own parent: the server " +
    "refuses it by name, and a control that offers what the server will reject " +
    "is a control that invites the refusal"
);

/* 7 — the seam. ------------------------------------------------------------ */
//
// This assertion exists because its absence shipped once today. The server
// attached a measurement beside the room while the browser read it off the
// room, both source suites stayed green, and the live page rendered nothing.
// Two green suites either side of a contract that neither crosses is not
// coverage, so the crossing is checked here, in the file that reads both.

assert.match(
  save[0],
  /body: JSON\.stringify\(\{\s*title:[\s\S]{0,120}continues:/,
  "the save should send both keys in one request"
);
// The READ, not merely the key name. An earlier version of this asserted that
// `"continues" in body` appeared in server.py, and mutation testing walked
// through it: that phrase occurs twice, so corrupting one left the other to
// satisfy the match. What has to hold is that the handler actually pulls each
// key out of the body, which is one place per key.
for (const key of ["title", "continues"]) {
  assert.ok(
    new RegExp(`body\\.get\\("${key}"\\)`).test(serverPy),
    `star/server.py's update_room must read "${key}" out of the body — this ` +
      `file sends it, and neither side's own suite can see the other's key names`
  );
}

/* 8 — styled as the docket's own copy, off a pair already measured. -------- */

assert.match(
  css,
  /\.room-edit \{/,
  "the panel needs a rule; a class with no rule is a styling hook that styles " +
    "nothing"
);

console.log("ok - a room can be named and placed, in one language");
