// Guards the resume path: every run stashed, every finished run unstashed.
//
// THE BUG. `stream_key` is minted server-side and handed back exactly once, at
// creation — EventSource sends no custom headers, so it is the only way the
// progress stream can identify its caller, and no endpoint reissues it. Lose it
// and a 146-420s build becomes unwatchable. The OAuth redirect loses it. So do
// a reload, a crash, and a phone locking. Only the redirect was ever wired: the
// whole machinery — stash, delete-on-read, replay-from-zero, the monotonic
// dedupe guard, and a Cloud Run deploy pinned to one instance so a reconnect
// lands on the same warm process — already shipped, behind one trigger.
//
// THE SECOND HALF, which is not optional. Once every run is stashed,
// delete-on-read is no longer enough: takeStashedRun only runs on a load, and a
// run that finishes while the page stays open never gets one. The stash would
// outlive the run and the NEXT load would resume a room that had already filed,
// opening it for a reader who asked for nothing.
//
// WHY SOURCE ASSERTIONS. sessionStorage, EventSource and an SSE replay are none
// of them things the stub document in _scriptcheck_module.mjs has. The live
// path was verified against two real builds instead — build, reload mid-run,
// resume with no duplicate timeline entries, complete, stash cleared, and a
// final reload landing on the intake rather than the filed room. These
// assertions stop that regressing silently.
//
// Run directly: `node tests/js/test_run_resume.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
// Line endings normalised at the door. This repo's working copies are CRLF on
// Windows, and a stray \r before every \n makes an assertion pass or fail on
// the checkout rather than on the source — which is the opposite of what a
// source assertion is for.
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

const app = stripComments(read("web/app.js"));
const auth = stripComments(read("web/auth.js"));

/* 1 — both halves are exported. ----------------------------------------- */

assert.match(
  auth,
  /export function stashLiveRun\(\)/,
  "stashLiveRun was module-private and wired to beginGoogleLink alone; the " +
    "value it protects is lost the same way by a reload"
);
assert.match(
  auth,
  /export function clearStashedRun\(\)/,
  "a finished run has to be able to forget itself"
);
assert.match(
  auth.match(/export function clearStashedRun\(\)[\s\S]*?\n\}/)[0],
  /removeStash\(RUN_KEY\)/,
  "clearStashedRun should drop the run stash and nothing else"
);

/* 2 — every run is stashed, at the one place a stream opens. ------------ */

const openStream = app.match(/function openStream\(runId, streamKey[\s\S]*?\n\}\n/);
assert.ok(openStream, "openStream should exist");
assert.match(
  openStream[0],
  /stashLiveRun\(\)/,
  "openStream is the single place a run becomes watchable, so it is where the " +
    "run is stashed — both callers (a fresh build and a resume) go through it"
);
// auth.js reads the run back through the provider registered at the foot of
// app.js, so both fields must be set before the stash is written.
const keyAt = openStream[0].indexOf("liveStreamKey = streamKey");
const stashAt = openStream[0].indexOf("stashLiveRun()");
assert.ok(keyAt > -1 && stashAt > -1, "both lines should be present");
assert.ok(
  keyAt < stashAt,
  "liveStreamKey must be assigned before stashLiveRun reads it back through " +
    "the provider — otherwise the stash is written without the one value that " +
    "cannot be recovered"
);

/* 3 — every finished run is unstashed, at the one terminal funnel. ------ */

const endRun = app.match(/function endRun\(source\) \{([\s\S]*?)\n\}/);
assert.ok(endRun, "endRun should exist");
assert.match(
  endRun[1],
  /clearStashedRun\(\)/,
  "every terminal branch passes through endRun. Without this the stash " +
    "outlives the run and the next load resumes a room that already filed"
);

/* 4 — the resume line is true on every path that reaches it. ------------ */

const resume = app.match(/async function resumeStashedRun\(\) \{([\s\S]*?)\n\}/);
assert.ok(resume, "resumeStashedRun should exist");
assert.doesNotMatch(
  resume[1],
  /Back from the sign-in/,
  "the sign-in wording was written when the redirect was the only way in. " +
    "Three of the four ways in are now not the sign-in, and the line was false " +
    "for all three"
);
assert.match(
  resume[1],
  /addEntry\("done", "Picking the run up where it was\."\)/,
  "the resume entry should read true on a reload, a crash and a sign-in alike"
);

/* 5 — a running room the page is not watching offers the one action. ---- */

assert.match(
  app,
  /again\.textContent = "Check again";/,
  "a run this page is not streaming needs something to press. Before this the " +
    "only way to learn a build had finished was reloading on a hunch"
);
assert.match(
  app,
  /again\.addEventListener\("click", \(\) => showResults\(runId\)\)/,
  "and pressing it should re-issue the room fetch"
);
assert.doesNotMatch(
  app,
  /Reconnecting to a live run isn't available yet/,
  "that sentence described the roadmap rather than the reader's next step, " +
    "and this wave made it false"
);

/* 6 — no duration is promised on the resume surfaces. ------------------- */

const runningCopy = app.match(/running: \[\s*"Still in the department",\s*"([^"]*)"/);
assert.ok(runningCopy, "the running copy should still be a literal pair");
assert.doesNotMatch(
  runningCopy[1],
  /minute|second|hour|moment|shortly|soon|about \d/i,
  "invariant 9: show progress, never an ETA. config.py records 146s to 420s+ " +
    "for one fixed treatment"
);

/* 7 — the honest limit is written down where it is implemented. --------- */

const stashDoc = read("web/auth.js").match(/\/\*\*[\s\S]{0,1400}?export function stashLiveRun/);
assert.ok(stashDoc, "stashLiveRun should carry a docstring");
assert.match(
  stashDoc[0],
  /closed or new tab is\s*\*?\s*not|not\b[\s\S]{0,40}closed or new tab/,
  "sessionStorage covers a reload and a same-tab lock, usually survives a " +
    "crash via session restore, and does not cover a closed or new tab. That " +
    "limit belongs next to the code, not only in a commit message"
);

console.log("test_run_resume.mjs: 15 assertions passed");
