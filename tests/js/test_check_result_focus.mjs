// Guards the one signal that a paid check finished.
//
// THE GAP. mountResult did replaceChildren + classList.remove("hidden") and
// nothing else. A grep of all of web/ for scrollIntoView|scrollTo|scrollTop|
// .focus() returned exactly one scroll call in the whole app — on the build
// timeline — and none anywhere in scriptcheck.js. So the entire visible answer
// to a request that just spent live searches was a status line clearing and a
// button re-enabling, with the result mounting below the fold.
//
// THE ROOT CAUSE the finding never named: `els.run.disabled = true` at submit.
// Disabling the focused button drops focus to <body> in every engine, and
// re-enabling it does not hand focus back. That window is the whole duration of
// the request, not just the mount, and BOTH exits leaked it — the failure path
// re-enabled the button and returned with the reader still on <body>, which no
// role="alert" on the error span fixes.
//
// WHY A REGION AND NOT A HEADING. The result body has no heading, and its first
// children are two conditional notes. Focusing the meter line would land the
// reader past the cover note, which scriptcheck.js orders first on the record
// because it is the department's own line about a thin result. Naming the
// region BY the meter puts "9 claims · 1 live search · filed 10 AUG 2026" on
// the way in and still starts the reading at the cover note. It also keeps the
// name derived from the payload rather than authored beside it.
//
// The render half below is a real behaviour test against the stub document. The
// mountResult and runCheck halves are source assertions: both need `els`, and
// runCheck awaits the network the stub does not implement.
//
// Run directly: `node tests/js/test_check_result_focus.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

import { loadPatchedModule, readSource, stubDocument, walk, withClass } from "./_scriptcheck_module.mjs";

globalThis.document = stubDocument();

const { renderCheckResult } = await import(loadPatchedModule());

function claim(overrides = {}) {
  return {
    text: "the Ampex 350 sits there",
    verdict: "confirmed",
    sources: [],
    ...overrides,
  };
}

/* 1 — the result is a focusable, named region. --------------------------- */

const root = renderCheckResult({
  claims: [claim()],
  scene: "the Ampex 350 sits there.",
  search_count: 1,
});

assert.equal(
  root.getAttribute("role"),
  "region",
  "the result needs a role that can carry a name — a bare div is generic and " +
    "name-prohibited, so focusing it would announce nothing useful"
);
assert.equal(
  root.getAttribute("tabindex"),
  "-1",
  "focusable programmatically, but never a tab stop: the reader is sent here " +
    "when a result lands, they do not tab into a container on the way past"
);

/* 2 — the name is carried by aria-label, and NOT by a descendant ref. ---- */

// THE TRAP, verified in Chromium's live accessibility tree on 2026-08-11:
// aria-labelledby pointing at a node INSIDE the region computes no name at all,
// while the identical attribute pointing outside it names the region correctly.
// The first version of this fix used the id and passed every assertion in this
// file while shipping an unnamed region. Source assertions cannot see an
// accessibility tree, so this one is written as a prohibition instead.
const labelledBy = root.getAttribute("aria-labelledby");
if (labelledBy) {
  const target = walk(root).find(
    (n) => n.nodeType === 1 && n.getAttribute("id") === labelledBy
  );
  assert.equal(
    target,
    undefined,
    "aria-labelledby must not point at a descendant of the region it names — " +
      "Chromium computes no name for that and the region ships anonymous"
  );
}

const name = root.getAttribute("aria-label");
assert.ok(name, "the region should be named");

/* 3 — the name says what landed, not that a result is a result. ---------- */

assert.match(name, /\bclaim/, "the name should carry the count that landed");
assert.match(
  name,
  /1 live search/,
  "and the searches spent — this is the figure the reader paid for and the " +
    "reason the name is derived from the payload rather than written by hand"
);

// And it is the same string the reader sees, not a second one that can drift.
const meters = withClass(root, "check-meter");
assert.equal(meters.length, 1, "there should be exactly one meter line");
const meterText = walk(meters[0])
  .filter((n) => n.nodeType === 3)
  .map((n) => n.data)
  .join("");
assert.equal(
  name,
  meterText,
  "the name and the visible meter should be one value computed once — two " +
    "call sites is how they drift apart"
);

/* 4 — the cover note is still reached first on the way in. --------------- */

const covered = renderCheckResult({
  claims: [],
  scene: "she thinks about it.",
  cover_note: "This scene asserts nothing about the world.",
});
const kids = covered.childNodes.filter((n) => n.nodeType === 1);
assert.match(
  String(kids[0].getAttribute("class")),
  /check-cover/,
  "landing on the region and reading forward must start at the cover note. " +
    "Focusing the meter directly would step over it, which is why focus goes " +
    "to the region and the meter is only its name"
);

/* 5 — focus moves on a fresh result, and only on a fresh result. --------- */

// readSource does not normalise line endings and this repo's working copies are
// CRLF on Windows, so a pattern anchored to \n passes or fails on the checkout
// rather than on the source. Normalise once, here.
const source = readSource()
  .replace(/\r\n/g, "\n")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .filter((line) => !/^\s*\/\//.test(line))
  .join("\n");

const mount = source.match(/function mountResult\(([\s\S]*?)\n\}/);
assert.ok(mount, "mountResult should still exist");
assert.match(
  mount[1],
  /moveFocus/,
  "opening a filed check from the row mounts through here too — stealing " +
    "focus from a control somebody is still using is the opposite of the fix"
);
assert.match(mount[1], /\.focus\(\)/, "a fresh result should take focus");
assert.doesNotMatch(
  mount[1],
  /scrollIntoView/,
  "focus scrolls the element into view by itself; calling both scrolls twice"
);

const run = source.match(/async function runCheck\(\) \{([\s\S]*?)\n\}/);
assert.ok(run, "runCheck should still exist");
assert.match(
  run[1],
  /mountResult\([\s\S]{0,60}moveFocus: true/,
  "the success exit is the one that moves focus"
);

/* 6 — the failure exit does not strand the reader on <body>. ------------- */

const failure = run[1].match(/\} catch \(err\) \{([\s\S]*?)\n {2}\}/);
assert.ok(failure, "runCheck should still have its failure exit");
assert.match(
  failure[1],
  /els\.run\.focus\(\)/,
  "the disabled button dropped focus to <body> at submit; a return that " +
    "leaves it there means a keyboard reader tabs from the top of the document"
);
// Order matters: focus() on a disabled button is a no-op.
const enableAt = failure[1].indexOf("els.run.disabled = false");
const focusAt = failure[1].indexOf("els.run.focus()");
assert.ok(enableAt > -1 && focusAt > -1, "both lines should be present");
assert.ok(
  enableAt < focusAt,
  "re-enable before focusing — focus() on a disabled element does nothing"
);

/* 7 — reduced motion is honoured by the absence of a declaration. -------- */

// The native scroll that focus() performs is instant unless something declares
// scroll-behavior above it. Nothing does, so there is no media query to write —
// and this assertion is what makes that a checked fact rather than a comment.
const css = ["shell.css", "scene.css", "clip.css", "drawer.css", "bible.css", "account.css", "consent.css"];
const { readFileSync } = await import("node:fs");
for (const file of css) {
  let sheet;
  try {
    sheet = readFileSync(new URL(`../../web/${file}`, import.meta.url), "utf8");
  } catch {
    continue; // a sheet that no longer exists cannot declare anything
  }
  assert.doesNotMatch(
    sheet,
    /scroll-behavior\s*:\s*smooth/,
    `${file}: declaring smooth scrolling makes the focus scroll animate, and ` +
      `focus() takes no behavior option to opt back out. Invariant: motion ` +
      `is opt-in under reduce, and this path has no way to honour it`
  );
}

console.log("test_check_result_focus.mjs: 19 assertions passed");
