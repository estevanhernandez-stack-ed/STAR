// Guards the wiring that keeps an unsubmitted scene alive when the reader
// re-enters the room they are already in.
//
// WHY THIS IS A SOURCE TEST AND NOT A BEHAVIOUR TEST. The thing being guarded
// lives in web/scriptcheck.js's `els`, which is populated only by
// initScriptCheck() reaching eleven element ids. The stub in
// _scriptcheck_module.mjs implements createElement and createTextNode and
// nothing else, and its header argues at length for staying that small — a
// stub that grows a getElementById is a stub that can do more than the test
// needs and less than a browser does. So this file asserts the SHAPE of the
// wiring rather than driving it, and says so plainly.
//
// What this file proves:
//   1. resetCheck takes the next room's id and compares it to the room it is
//      currently pointed at, rather than nulling that id unconditionally.
//   2. clearCheck is called with keepScene set from that comparison, not with
//      a literal false.
//   3. web/app.js forwards the id down both hops — showResults into
//      resetRoomView, resetRoomView into resetCheck.
//
// What it does NOT prove, and what the browser checkpoint still has to: that
// the textarea actually holds its value across the click. Every assertion here
// is a statement about source text.
//
// The bug this exists against: clicking the room already open — the way back
// from Your card, which had no exit of its own — ran a full room re-render and
// wiped pages of typed scene text that live nowhere else. The guard that
// should have caught it (`if (runId === roomId) return` in setCheckRoom) could
// never fire, because resetCheck had already erased the roomId it compares.
//
// Run directly: `node tests/js/test_check_scene_retention.mjs` (exit 0 = pass).
// Wired into pytest via tests/test_js_auth.py so pytest stays the entry point.

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) =>
  // Normalised at read: working copies are CRLF and CI is not, so a pattern
  // anchored to a newline passes on one checkout and fails on another. This
  // file shipped without it and went red the first time git handed the
  // source back with CRLF.
  readFileSync(new URL(path, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

/** Source with its comments removed, so every assertion below is about what
 *  ships rather than about what is explained. Same treatment
 *  test_scriptcheck.mjs applies, and for the same reason: a file that explains
 *  itself well should not be able to pass a test on the strength of the
 *  explanation. */
function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const scriptcheck = stripComments(read("web/scriptcheck.js"));
const app = stripComments(read("web/app.js"));

/* 1 — resetCheck takes the next room and compares it. ------------------- */

const resetCheckBody = scriptcheck.match(
  /export function resetCheck\(([^)]*)\)\s*\{([\s\S]*?)\n\}/
);
assert.ok(resetCheckBody, "resetCheck should still be an exported function declaration");

const [, resetCheckParams, resetCheckSource] = resetCheckBody;

assert.ok(
  resetCheckParams.trim().length > 0,
  "resetCheck takes no parameter, so it cannot tell a room change from a re-entry — " +
    "this is the exact shape that made an unsubmitted scene disposable"
);

assert.match(
  resetCheckSource,
  /===\s*roomId|roomId\s*===/,
  "resetCheck should compare the incoming room id against the room it is pointed at"
);

/* 2 — roomId survives a same-room reset, so setCheckRoom's guard can fire. */

assert.doesNotMatch(
  resetCheckSource,
  /^\s*roomId\s*=\s*null;/m,
  "resetCheck nulls roomId unconditionally. That is what disarms setCheckRoom's " +
    "`if (runId === roomId) return` — the guard cannot match an id this function " +
    "just erased, so the room paint that follows clears the scene a second time"
);

assert.match(
  resetCheckSource,
  /if\s*\(!\s*sameRoom\)\s*roomId\s*=\s*null;/,
  "roomId should be released only when the room actually changed"
);

/* 3 — keepScene is computed, never a literal on this path. --------------- */

assert.match(
  resetCheckSource,
  /clearCheck\(\{\s*keepScene:\s*sameRoom\s*\}\)/,
  "resetCheck should hand clearCheck the comparison result, not a literal"
);

// The cross-room leak fix this function was written for must survive. A
// different room still lets go of everything — that is the whole reason
// resetCheck runs before a room load is even issued.
assert.match(
  scriptcheck,
  /export function setCheckRoom\(runId\)\s*\{\s*if\s*\(runId === roomId\) return;/,
  "setCheckRoom's same-room guard should still be the first thing it does"
);
assert.match(
  scriptcheck,
  /clearCheck\(\{ keepScene: false \}\)/,
  "a genuine room change should still clear the scene"
);

/* 4 — app.js forwards the id down both hops. ---------------------------- */

assert.match(
  app,
  /function resetRoomView\(\s*nextRunId\s*\)/,
  "resetRoomView should take the room about to be painted"
);
assert.match(
  app,
  /resetCheck\(nextRunId\)/,
  "resetRoomView should pass that room down to resetCheck"
);
assert.match(
  app,
  /resetRoomView\(runId\)/,
  "showResults should tell resetRoomView which room it is about to paint — " +
    "without this the parameter above is always undefined and the fix is inert"
);

/* 5 — the card has a way out that is not a room re-render. --------------- */

const shell = stripComments(read("web/shell.js"));
const account = stripComments(read("web/account.js"));

assert.match(
  shell,
  /export function showPreviousStage\(\)/,
  "the card needs an exit that is a panel swap, not a loadRoom"
);
assert.doesNotMatch(
  shell.match(/export function showPreviousStage\(\)[\s\S]*?\n\}/)[0],
  /loadRoom|_renderRoom|authedFetch/,
  "backing out of the card must not re-fetch or re-render a room — that is the " +
    "path that cost the scene in the first place"
);
assert.match(
  account,
  /onBack\(\)\s*\{\s*showPreviousStage\(\);/,
  "the account card should wire its back control to the stage swap"
);

console.log("test_check_scene_retention.mjs: 12 assertions passed");
