// Guards the rail's knowledge of a run in flight, and the control that can
// walk away from one.
//
// THE BUG, and it is a money bug rather than a cosmetic one. Nothing called
// refreshRail between the POST that starts a build and the event that ends it,
// so web/shell.js's `isRunning` marker branch was unreachable on the build path
// and the rail printed "Nothing filed yet" beside four drawers actively
// searching (docs/ui-evidence/06-progress-running--default.png). With no row,
// showRunning() had two callers and neither was a control — so a reader who
// opened Your card mid-build had no way back to their own run.
//
// And pressing "New room" from there closed the stream while the run carried
// on spending: star/server.py's stream_events is a bare `while True` with no
// request.is_disconnected() check, and the pipeline is a separate task held by
// a strong ref in _runs[run_id]["task"]. Ending the SSE response ends the
// generator, not the work.
//
// WHY SOURCE ASSERTIONS. web/app.js takes eleven element references and wires
// listeners at module evaluation, so it does not import against the stub in
// _scriptcheck_module.mjs; web/shell.js does, but the behaviour that matters
// here is a POST-to-rail sequence and an EventSource, neither of which the stub
// has. The live path was verified against a real build instead — see the wave's
// process notes. These assertions stop it regressing silently.
//
// Run directly: `node tests/js/test_live_run_rail.mjs` (exit 0 = pass).

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
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

const app = stripComments(read("web/app.js"));
const shell = stripComments(read("web/shell.js"));
const html = read("web/index.html");

/* 1 — the build path tells the rail a run exists. ----------------------- */

const buildRoom = app.match(/async function buildRoom\(\) \{([\s\S]*?)\n\}/);
assert.ok(buildRoom, "buildRoom should still be a function declaration");
assert.match(
  buildRoom[1],
  /refreshRail\(runId\)/,
  "buildRoom must refresh the rail once the POST succeeds — without it the " +
    "running-marker branch in shell.js is unreachable and a live build shows " +
    "'Nothing filed yet' beside four searching drawers"
);
// Order: the stream is what the reader is waiting on and must not queue behind
// a list fetch.
const openAt = buildRoom[1].indexOf("openStream(runId, streamKey)");
const railAt = buildRoom[1].indexOf("refreshRail(runId)");
assert.ok(openAt > -1 && railAt > -1, "both calls should be present");
assert.ok(openAt < railAt, "openStream should come before refreshRail");

/* 2 — the live run id is set and cleared at exactly one place each. ------ */

assert.match(
  app.match(/function openStream\([\s\S]*?\n\}/)[0],
  /setLiveRun\(runId\)/,
  "opening a stream should tell the rail which run is live"
);
const endRun = app.match(/function endRun\(source\) \{([\s\S]*?)\n\}/);
assert.ok(endRun, "endRun should exist");
assert.match(
  endRun[1],
  /setLiveRun\(null\)/,
  "every terminal branch passes through endRun, so the live-run id is cleared " +
    "there — a stale one would send a reader to a progress panel for a run " +
    "that has already filed"
);

// THE ABANDON PATH, and this file used to assert the opposite. It said the
// live-run id was "set and cleared at exactly one place each", which was the
// sentence that let the defect through: endRun is the TERMINAL funnel, and
// walking away from a run is not terminal. Pressing "New room" twice during a
// build reaches resetProgress and nothing else, so _liveRunId survived in
// shell.js pointing at the abandoned run — its rail row routed to
// showRunning() and opened the panel resetProgress had just emptied, for a run
// that was still spending. The stash survived the same press, so a reload
// resumed the run the reader pressed twice to leave.
const resetProgress = app.match(/function resetProgress\(\) \{([\s\S]*?)\n\}/);
assert.ok(resetProgress, "resetProgress should exist");
assert.match(
  resetProgress[1],
  /setLiveRun\(null\)/,
  "resetProgress is the only thing the abandon path reaches — it must let go " +
    "of the run, not just of the panel"
);
assert.match(
  resetProgress[1],
  /clearStashedRun\(\)/,
  "and drop the stash, or a reload resumes the run the reader just abandoned"
);

/* 3 — a running row goes to the live surface, not to loadRoom. ---------- */

assert.match(
  shell,
  /if \(_liveRunId !== null && room\.run_id === _liveRunId\) \{\s*showRunning\(\);/,
  "a row for the streaming run should reveal the progress panel. loadRoom " +
    "would fetch a room with no story_profile yet and paint the placeholder " +
    "over a stream still writing into that panel"
);
assert.match(shell, /export function setLiveRun\(runId\)/, "shell should expose the setter");

/* 4 — a running row does not claim facts the department has not found. -- */

assert.match(
  shell,
  /isRunning \? "In the department" : room\.title \|\| "Untitled room"/,
  "a run in flight is not an 'Untitled room' — store.py writes the document " +
    "off an empty story_profile at creation, so that label claims the " +
    "department read the treatment and found no title"
);
assert.match(
  shell,
  /isRunning\s*\?\s*"Researching now"/,
  "and it has not found no era either — it has not looked yet"
);

/* 5 — New room arms while a run is live, and only then. ----------------- */

assert.match(
  html,
  /id="new-room-btn"[^>]*data-armed="false"/,
  "the control should ship in its resting state"
);
assert.match(html, /id="new-room-notice"/, "the first press needs somewhere to say what it means");

const handler = app.match(/\$\("new-room-btn"\)\.addEventListener\("click", \(\) => \{([\s\S]*?)\n\}\);/);
assert.ok(handler, "the New room listener should exist");
assert.match(
  handler[1],
  /if \(liveRunId !== null && btn\.getAttribute\("data-armed"\) !== "true"\)/,
  "arming is conditional on a run being live — with none there is nothing to " +
    "warn about and the control must behave exactly as it did"
);
assert.match(
  handler[1],
  /return;/,
  "the first press must return before resetProgress, or it closes the stream " +
    "it is warning about"
);
assert.match(
  endRun[1],
  /disarmNewRoom\(\)/,
  "a run ending should disarm the control, or a build that finishes while it " +
    "is armed leaves a warning about spending that has already stopped"
);

/* 6 — the warning says what continues, never when it ends. -------------- */

const notice = app.match(/const NEW_ROOM_NOTICE =\n?([\s\S]*?);/);
assert.ok(notice, "the notice should be a named constant");
assert.doesNotMatch(
  notice[1],
  /minute|second|hour|about \d|~\d|soon|shortly|almost/i,
  "invariant 9: copy never promises a duration. config.py records 146s to " +
    "420s+ for one fixed treatment, so any number here is a guess"
);
assert.match(
  notice[1],
  /keeps spending/,
  "the whole reason this control arms is that the run keeps costing money — " +
    "say so"
);

console.log("test_live_run_rail.mjs: 17 assertions passed");
