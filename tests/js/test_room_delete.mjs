// Guards the web app's half of deleting a room.
//
// It exists at all because of decision 8 in docs/delete-brief.md: shipping
// delete on the agent door first would hand an agent a power the person does
// not have, which is the objection that blocked the feature. So the two doors
// ship together, and this pins the browser one.
//
// TWO PRESSES, and the same arming web/scriptcheck.js's buildFoot already
// argues for a check: a room costs real money and several minutes, one stray
// click should not be able to spend that again, and the warning belongs on the
// page in the department's voice rather than behind a browser dialog.
//
// THE RESTORE LIST IS NOT DECORATION. A deleted room leaves the rail by design.
// If nothing lists it again then the thirty-day window is time a person cannot
// reach, and every sentence promising the room is "recoverable in the web app"
// — including the one the agent door prints — is false. The deleted group is
// what makes that copy true, which is why its absence is a failure here.
//
// Run directly: `node tests/js/test_room_delete.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");
const strip = (s) =>
  s
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !/^\s*\/\//.test(l))
    .join("\n");

const app = strip(read("web/app.js"));
const shell = strip(read("web/shell.js"));
const html = read("web/index.html");

/* 1 — the control is armed, not immediate. ------------------------------- */

const button = html.match(/<button id="room-delete-btn"[^>]*>/);
assert.ok(button, "the room delete control should exist in the docket");
assert.match(button[0], /data-armed="false"/, "it ships disarmed");

const handler = app.match(/roomDeleteBtn\.addEventListener\("click",[\s\S]*?\n {2}\}\);/);
assert.ok(handler, "the control should be wired");
assert.match(
  handler[0],
  /data-armed"\) !== "true"/,
  "the first press arms and returns rather than deleting"
);
assert.match(handler[0], /return;/, "and it returns before any request");
assert.match(
  handler[0],
  /method: "DELETE"/,
  "only the second press sends the request"
);

/* 2 — the first press says what goes, and says it is recoverable. -------- */

// Within one literal: these sentences are split across JS `+`, so a pattern
// spanning the join fails on formatting rather than on meaning.
assert.match(
  handler[0],
  /every check filed/,
  "the warning names the checks that go with the room"
);
assert.match(
  handler[0],
  /put it back/i,
  "and that it is recoverable — this delete is not the check's, which says " +
    "the opposite and means it"
);

/* 3 — arming never carries between rooms. -------------------------------- */

assert.match(
  app,
  /openRoomId = runId;\n\s*\n?\s*(\/\/[^\n]*\n\s*)*\s*disarmRoomDelete\(\);/,
  "opening a room disarms the control, so an armed press cannot land on a " +
    "room the reader only just navigated to"
);

/* 4 — the deleted group exists, and is drawn on BOTH rail exits. --------- */

assert.match(shell, /function renderDeleted\(\)/, "the rail lists deleted rooms");
assert.equal(
  (shell.match(/\n\s*renderDeleted\(\);/g) || []).length,
  2,
  "drawn on both of renderRail's exits — the empty-rail branch returns early, " +
    "and a reader whose only rooms are deleted would otherwise see nothing at " +
    "all and have no way back"
);
assert.match(shell, /method: "POST"/, "and offers a restore");
assert.match(shell, /\/restore/, "against the restore endpoint");

/* 5 — the window is stated, and comes from the server. ------------------- */

assert.match(
  shell,
  /retention_days: retention/,
  "the number comes from the server rather than being typed into the client, " +
    "where it would be a second copy of a value config owns"
);
assert.doesNotMatch(
  shell,
  /Kept for 30 days/,
  "and it is never hardcoded — a client that types the window says something " +
    "false the day config changes it"
);

console.log("test_room_delete.mjs: 14 assertions passed");
