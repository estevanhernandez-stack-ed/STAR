// Guards the app's most-printed number against claiming more than it knows.
//
// THE DEFECT. The docket and the live meter read "17 cited web searches".
// star/server.py increments run["search_count"] inside the block reading
// `call.args` — the tool CALL, before any response exists — and the ledger is
// written separately from the responses, while the check path increments before
// the HTTP request is sent. So the number counts searches ISSUED. "Cited"
// asserts two further things it cannot know: that the search came back, and
// that a finding leaned on what it returned.
//
// The app already ships a guard for exactly that gap
// (`search_count > 0 and len(ledger) == 0`), web/drawer.js:187 already says
// "issued" with the argument written out, and the docstring directly above the
// offending line argues the same discipline for the number BESIDE it: "sources
// SEEN, not sources cited — worth saying plainly rather than letting '106
// sources' imply 106 footnotes." The file disagreed with itself in eight lines.
//
// Copy rule 3 is usually read as being about the word "verified". It is about
// the claim, and a number carries claims too.
//
// WHAT MUST NOT CHANGE: "cited link" elsewhere. A model really did cite that
// URL — that is what makes its absence from the ledger worth reporting — so
// those strings are accurate and this test pins them in place, because the
// cheapest way to "fix" this finding is a global replace that breaks them.
//
// Run directly: `node tests/js/test_search_count_copy.mjs` (exit 0 = pass).

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

/* 1 — neither reader-facing surface calls a search cited. ---------------- */

assert.doesNotMatch(
  app,
  /cited (web )?search/i,
  "the count is of searches issued, and 'cited' claims both that one came " +
    "back and that a finding used it"
);

// Both surfaces still print the number — the fix is the word, not the fact.
assert.match(
  app,
  /plural\(result\.search_count, "web search"\)/,
  "the docket still reports the tally"
);
assert.match(
  app,
  /\$\{searchCount\} searches so far/,
  "and so does the live meter"
);

/* 2 — the sources half is untouched and still says what it means. -------- */

assert.match(
  app,
  /\$\{plural\(result\.source_count, "source"\)\} returned/,
  "'returned' was already right: the ledger holds what search actually sent " +
    "back, which is a different fact from what was cited"
);

/* 3 — "cited link" is a different claim and survives. -------------------- */

for (const [file, why] of [
  ["web/clip.js", "a drawer reports links a researcher cited that never reached the ledger"],
  ["web/scriptcheck.js", "a check reports the same for a claim's own citations"],
]) {
  assert.match(
    strip(read(file)),
    /plural\((?:unverified|unsourced), "cited link"\)/,
    `${file}: ${why}. A model really did cite that URL — that is the whole ` +
      `point of reporting it. A global replace of "cited" breaks this`
  );
}

/* 4 — the server still counts what this copy now says it counts. --------- */

const server = read("star/server.py");
const at = server.indexOf('run["search_count"] += 1');
assert.ok(at > -1, "the increment should still exist");

// The enclosing block, not a fixed character window: `args = call.args or {}`
// sits ~15 lines above the increment and a 600-char slice does not reach it,
// which is how the first version of this assertion failed against correct code.
const enclosing = server.slice(0, at);
const lastCalls = enclosing.lastIndexOf("get_function_calls");
const lastResponses = enclosing.lastIndexOf("get_function_responses");
assert.ok(
  lastCalls > -1,
  "the increment should still sit under a get_function_calls loop"
);
assert.ok(
  lastCalls > lastResponses,
  "the count is taken off the tool CALL, which is why the copy says 'searches' " +
    "and not 'cited searches'. If it ever moves under get_function_responses " +
    "the copy is understating rather than overstating and should be revisited"
);

console.log("test_search_count_copy.mjs: 10 assertions passed");
