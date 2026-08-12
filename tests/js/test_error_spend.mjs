// A failed build has to say what it cost, on both browser surfaces.
//
// THE BUG. A build that fails has already spent live searches and one of the
// department's daily builds, and neither comes back. The screen said only that
// it failed: the progress panel put "Start a new room" directly under a line
// with no price on it, and the reopen path said "This run hit an error before
// anything could be filed" — which reads like it cost nothing. A writer who
// pressed the button three times spent three days' builds learning otherwise.
//
// WHY THIS IS A SOURCE TEST. Same reason as tests/js/test_progress_failure.mjs:
// the failure state is reachable only from an SSE `error` event, and forcing
// one means paying for a failed build against a shared budget. web/app.js takes
// its element references at module evaluation, so it does not load against the
// stub module either. Every assertion below is a statement about source text.
//
// What this file proves:
//   1. The progress panel's failure state names the spend, from the live count
//      the panel is already keeping, and only when there is one.
//   2. The reopen path names it too, from the STORED count, so the fact is
//      still there tomorrow when the run is long out of memory.
//   3. Neither says it for a run still going. A running build has spent
//      searches, but "before it stopped" is false and the reader has not been
//      asked to pay again.
//   4. Neither number is authored. Both are read off state the app already
//      holds — the running total for the live panel, the document's own
//      `search_count` for the reopen. A count typed into copy is the defect
//      web/consent.js shipped when it said "four calls" in a language that
//      cannot see the Python list.
//   5. The sentence carries the two facts that make it worth printing: that
//      the searches are not refunded, and that a daily build went with them.
//
// Run directly: `node tests/js/test_error_spend.mjs` (exit 0 = pass).

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
const css = read("web/shell.css");

/* 1 — the live failure panel names the spend. --------------------------- */

const markRunFailed = app.match(/function markRunFailed\(message\) \{([\s\S]*?)\n\}/);
assert.ok(markRunFailed, "markRunFailed should exist");
const failure = markRunFailed[1];

assert.match(
  failure,
  /searchCount/,
  "the failure panel should say what the run spent — the panel is already " +
    "counting searches for its own progress line, so the number is right there"
);
assert.match(
  failure,
  /if \(searchCount > 0\)/,
  "and only when it spent something: `It spent 0 live searches` is noise on a " +
    "run that failed before it cost anything"
);

// The count is READ, never written. A literal in this sentence would be a
// number the app asserts rather than one it knows.
const spentText = failure.match(/spent\.textContent =([\s\S]*?);\n/);
assert.ok(spentText, "the spend line should set its own text");
assert.doesNotMatch(
  spentText[1],
  /\b\d+ live search/,
  "the count must be interpolated, not typed into the string"
);
assert.match(spentText[1], /\$\{searchCount\}/, "it should interpolate the running count");

/* 2 — the reopen path names it from the stored document. ---------------- */

const noProfileBranch = app.match(/if \(!hasProfile\) \{([\s\S]*?)\n {4}return;/);
assert.ok(noProfileBranch, "the no-profile branch should still be a distinct branch");
const reopen = noProfileBranch[0];

assert.match(
  reopen,
  /result && result\.search_count/,
  "the reopen path should read the spend off the stored room, which is the " +
    "only place it still exists once the run is out of memory"
);
assert.match(
  reopen,
  /status !== "running"/,
  "a room still being built has not stopped, and must not be told it has"
);

/* 2b — and it says WHY, from the room's own stored account. -------------- */
//
// The spend told a reader what a failed run cost. It could not tell them what
// happened: the specific explanation — ran past its time limit, hit an
// unexpected problem — was pushed down the SSE stream as the run died, and the
// stream is gone with the tab that was watching it. What persisted was
// `status: "error"`, so every failed room reopened to the same generic
// sentence, and a timeout was indistinguishable from a crash to the one person
// who needed to know a shorter treatment would work.
//
// star/store.py now keeps that sentence on the document as `note`. This holds
// the browser to reading it rather than printing its own.

assert.match(
  reopen,
  /result && result\.note/,
  "the reopen path should read the room's own account of why it stopped, for " +
    "the same reason it reads the spend: it is the only place either fact " +
    "still exists once the run is out of memory"
);

const docketWrite = reopen.match(/docketBody\.innerHTML =([\s\S]*?);\n/);
assert.ok(docketWrite, "the reopen path should still write the docket body");
assert.match(
  docketWrite[1],
  /filedNote \|\| copy\[1\]/,
  "the stored note should REPLACE the generic sentence rather than join it — " +
    "both say the run failed, and printing the pair says it twice"
);
assert.doesNotMatch(
  docketWrite[1],
  /ran past|unexpected problem|time limit/,
  "and no failure copy is authored here: the sentence a reader sees is the " +
    "one the server already wrote for them, not a second version of it that " +
    "can drift from the first"
);

/* 3 — both sentences carry the two facts worth printing. ---------------- */

for (const [name, block] of [["failure panel", failure], ["reopen path", reopen]]) {
  assert.match(
    block,
    /not refunded/,
    `${name}: the reader has to be told the searches do not come back`
  );
  assert.match(
    block,
    /daily builds/,
    `${name}: and that a slot of the shared daily budget went with them`
  );
  assert.doesNotMatch(
    block,
    /minute|second|hour/,
    `${name}: no duration is promised anywhere in this copy`
  );
}

/* 4 — one search is one search. ----------------------------------------- */

for (const [name, block] of [["failure panel", failure], ["reopen path", reopen]]) {
  assert.match(
    block,
    /=== 1 \? "" : "es"/,
    `${name}: "1 live searches" is the app failing to read its own number`
  );
}

/* 5 — the live panel's sentence has a rule to render by. ---------------- */

assert.match(
  css,
  /\.progress-failure-spent \{/,
  "the failure panel's spend line needs its own rule; the reopen path reuses " +
    ".docket-note deliberately, and adding a class with no rule would be a " +
    "styling hook that styles nothing"
);
assert.doesNotMatch(
  app.match(/spent\.className = "([^"]*)"/g)?.join(" ") || "",
  /docket-note-spent/,
  "no unstyled modifier classes"
);

console.log("ok - a failed build says what it cost, on both surfaces");
