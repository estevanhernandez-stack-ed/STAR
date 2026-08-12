// Guards the progress panel's terminal-failure state.
//
// THE BUG. Nothing in this app ever wrote #progress-panel's heading. So a run
// that failed — after spending real search budget — went on saying "The
// department is working" under a pulsing ellipsis, while sweepUnfiledDrawers
// filled all four drawers with "Did not file". The screen contradicted itself
// on the one surface where a reader finds out they paid for nothing.
//
// WHY THIS IS A SOURCE TEST. The state is reachable only from an SSE `error`
// event, and forcing one means paying for a failed build against a shared
// budget. web/app.js also takes eleven element references at module evaluation
// and wires listeners at import, so it does not load against the tiny stub in
// _scriptcheck_module.mjs. Every assertion below is therefore a statement about
// source text, and the live browser checkpoint still owns whether the block
// actually renders where it should.
//
// What this file proves:
//   1. The heading is addressable and the error branch rewrites it.
//   2. The failure block exists in the markup, ships hidden, and sits ABOVE the
//      point where resetProgress inserts the drawer grid.
//   3. resetProgress puts both back, so the next run does not start under the
//      last one's failure.
//   4. The recovery control does NOT clear the treatment — the one line that
//      made the rail's "New room" a poor recovery path from a failed build.
//   5. No duration is promised anywhere in the added copy.
//
// Run directly: `node tests/js/test_progress_failure.mjs` (exit 0 = pass).

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

/* 1 — the heading is addressable and the error branch rewrites it. ------ */

assert.match(
  html,
  /<h2 id="progress-heading">/,
  "the progress heading needs an id — nothing could write it before this wave"
);

const errorBranch = app.match(/else if \(ev\.type === "error"\) \{([\s\S]*?)\n {4}\}/);
assert.ok(errorBranch, "the SSE error branch should still be a distinct branch");
assert.match(
  errorBranch[1],
  /markRunFailed\(ev\.message\)/,
  "a terminal error should put the panel into its failure state"
);

const markRunFailed = app.match(/function markRunFailed\(message\) \{([\s\S]*?)\n\}/);
assert.ok(markRunFailed, "markRunFailed should exist");
assert.match(
  markRunFailed[1],
  /\$\("progress-heading"\)[\s\S]*?replaceChildren/,
  "the failure state should replace the heading's children — textContent would " +
    "leave the .ellipsis span, and the pulse is the half a reader sees first"
);

/* 2 — the block ships hidden, above the drawer grid's insertion point. -- */

assert.match(
  html,
  /<div id="progress-failure" class="progress-failure hidden"><\/div>/,
  "the failure block should ship empty and hidden"
);

const headingAt = html.indexOf('id="progress-heading"');
const failureAt = html.indexOf('id="progress-failure"');
const timelineAt = html.indexOf('id="timeline"');
assert.ok(headingAt > -1 && failureAt > -1 && timelineAt > -1, "all three ids should exist");
assert.ok(
  headingAt < failureAt && failureAt < timelineAt,
  "the failure block must sit between the heading and #timeline. resetProgress " +
    "inserts the drawer grid before #timeline, so anything after that point is " +
    "below four cards at their 260px floor — which is where the reason already was"
);

/* 3 — resetProgress puts the panel back. -------------------------------- */

const resetProgress = app.match(/function resetProgress\(\) \{([\s\S]*?)\n\}/);
assert.ok(resetProgress, "resetProgress should exist");
assert.match(
  resetProgress[1],
  /WORKING_HEADING/,
  "resetProgress should restore the working heading, or the next build starts " +
    "under the last one's failure"
);
assert.match(
  resetProgress[1],
  /"ellipsis"/,
  "restoring the heading should restore its ellipsis too"
);
assert.match(
  resetProgress[1],
  /progress-failure[\s\S]*?classList\.add\("hidden"\)/,
  "resetProgress should hide the failure block again"
);

/* 4 — the recovery control preserves the treatment. --------------------- */

assert.doesNotMatch(
  markRunFailed[1],
  /\$\("treatment"\)\.value\s*=/,
  "the recovery control must NOT clear the treatment. That single line is what " +
    "makes the rail's New room a poor recovery path from a build that just " +
    "failed, and it is the only write to that field in the app"
);
assert.match(
  markRunFailed[1],
  /showIntake\(\);[\s\S]*?resetProgress\(\);/,
  "the recovery control should do what New room does, minus the wipe"
);

// The rail's own button keeps its wipe — that control means "start fresh",
// and this test would otherwise pass by breaking it.
assert.match(
  app,
  /new-room-btn"\)\.addEventListener[\s\S]*?\$\("treatment"\)\.value = "";/,
  "the rail's New room should still clear the treatment"
);

/* 5 — no duration promised. --------------------------------------------- */

const FAILURE_COPY = app.match(/const (WORKING_HEADING|FAILED_HEADING|START_OVER) = "[^"]*";/g);
assert.ok(FAILURE_COPY && FAILURE_COPY.length === 3, "the three headings should be constants");
for (const line of FAILURE_COPY) {
  assert.doesNotMatch(
    line,
    /minute|second|hour|about \d|~\d|\d+\s*(m|s)\b|shorter|faster|longer/i,
    `invariant 9: copy never promises a duration — ${line}`
  );
}

/* 6 — the failure slip reuses a measured pair, and joined the paper list. */

assert.match(
  css,
  /\.progress-failure \{[\s\S]*?background: var\(--onionskin\);[\s\S]*?color: var\(--oxide\);/,
  "the slip should be oxide on onionskin — 4.75:1, already measured, rather " +
    "than oxide on the cabinet's dark ground at 2.79:1"
);
// \r? throughout: this repo's working copies are CRLF on Windows, and a test
// that only matches LF passes or fails on the checkout rather than the CSS.
assert.match(
  css,
  /\.bible,\r?\n\.banner,\r?\n\.progress-failure \{/,
  "the slip mounts a focusable control on onionskin, so it must join the " +
    "paper-surface list or that control takes the global --pencil ring at 2.76:1"
);
assert.match(
  css,
  /EIGHT elements are the whole set of paper surfaces/,
  "the paper-surface comment states its own count — a list that grew without " +
    "the count growing is the exact drift that block exists to stop"
);

console.log("test_progress_failure.mjs: 17 assertions passed");
