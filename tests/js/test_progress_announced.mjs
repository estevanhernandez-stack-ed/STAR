// Guards the one announcement a run in progress makes.
//
// THE GAP. A grep of all 22 files in web/ for aria-live, role="status",
// role="alert", role="log", aria-busy and aria-atomic returned exactly two live
// regions in the whole app — both on the check surface, neither in
// #progress-panel. So between pressing Build and the room appearing, 146 to
// 420+ seconds later, a screen-reader user was told nothing at all: focus sits
// on <body>, the panel swap is a class toggle that announces nothing, and the
// literal status messages ("Treatment received", "…filed their work") went into
// an inert <ul>. WCAG 4.1.3.
//
// It survived a 67-finding audit and two waves because live-region ABSENCE is
// not machine-checkable — axe and Lighthouse cannot see it, and it appears in
// none of the 17 captures. This file is the check that did not exist.
//
// WHY SOURCE ASSERTIONS. web/app.js takes eleven element references and wires
// listeners at module evaluation, so it does not import against the stub in
// _scriptcheck_module.mjs, and the stub implements no accessibility tree
// regardless. Every assertion below is a statement about source text; whether a
// real screen reader speaks it is a manual check this file cannot make and does
// not claim to.
//
// Run directly: `node tests/js/test_progress_announced.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

const html = read("web/index.html");
const app = stripComments(read("web/app.js"));

/* 1 — the timeline is the region, and it is polite. ---------------------- */

const timeline = html.match(/<ul id="timeline"[^>]*>/);
assert.ok(timeline, "#timeline should still exist");
assert.match(
  timeline[0],
  /aria-live="polite"/,
  "a build's log is the app's only channel for saying what is happening — " +
    "polite, because a run is not an emergency"
);
assert.match(
  timeline[0],
  /aria-relevant="additions"/,
  "additions only: each entry is appended once and never rewritten, and " +
    "resetProgress's clear runs before the panel is revealed"
);

/* 2 — the two things that must NOT be live. ------------------------------ */

const meter = html.match(/<p id="search-meter"[^>]*>/);
assert.ok(meter, "#search-meter should still exist");
assert.doesNotMatch(
  meter[0],
  /aria-live|role="status"|role="alert"/,
  "updateMeter rewrites this on a 1000ms interval — a live region here would " +
    "babble over the timeline and drown the entries that carry the actual news"
);
// The drawer grid is inserted by resetProgress, so assert on the constructor.
const drawer = read("web/drawer.js");
assert.doesNotMatch(
  drawer,
  /aria-live/,
  "the drawer bodies repaint per search event; they are a surface to read, " +
    "not a channel to announce"
);

/* 3 — every terminal branch announces. ----------------------------------- */

for (const [branch, why] of [
  ["complete", "a reader told the department was assembling must be told it finished"],
  ["partial", "already announced before this wave"],
  ["error", "already announced before this wave"],
]) {
  const m = app.match(new RegExp(`ev\\.type === "${branch}"\\) \\{([\\s\\S]*?)\\n {4}\\}`));
  assert.ok(m, `the ${branch} branch should exist`);
  assert.match(m[1], /addEntry\(/, `${branch}: ${why}`);
}

// And the completion line lands BEFORE the stage switches, so the region
// speaking it is still the panel the reader is on.
const complete = app.match(/ev\.type === "complete"\) \{([\s\S]*?)\n {4}\}/)[1];
const entryAt = complete.indexOf("addEntry(");
const switchAt = complete.indexOf("showResults(");
assert.ok(entryAt > -1 && switchAt > -1, "both calls should be present");
assert.ok(
  entryAt < switchAt,
  "announce before switching stage, not after — otherwise the region is " +
    "hidden by the time it speaks"
);

/* 4 — no library was reached for. ---------------------------------------- */

// Invariant 6 is about the ORIGIN, not about having scripts: the app's own
// modules and the two vendored libraries are the point. What must never appear
// is a script fetched from anywhere else.
assert.doesNotMatch(
  html,
  /<script[^>]+src="(?:https?:)?\/\//,
  "invariant 6: the fix is three attributes and one string, not a dependency"
);

/* 5 — the honest limit is written down where it applies. ----------------- */

const addEntryDoc = read("web/app.js").match(/\/\*\*[\s\S]{0,900}?function addEntry\(/);
assert.ok(addEntryDoc, "addEntry should carry a docstring");
assert.match(
  addEntryDoc[0],
  /first/i,
  "the first entry of a build is appended in the same task that reveals the " +
    "panel, and some AT drops it. That limit belongs next to the code, not " +
    "only in a brief"
);

console.log("test_progress_announced.mjs: 12 assertions passed");
