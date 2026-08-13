// A toggle's label lives in one place, and it is the markup.
//
// THE BUG. The check panel learned to take a whole draft and sweep it.
// index.html was updated to say so; the button that OPENS the panel went on
// saying "Check a scene", because web/app.js held its own copy of the string
// and restored it on every close. A reader looking for the sweep had no reason
// to open the one place it lives, and the feature was invisible to exactly the
// people it was built for.
//
// The string was written twice and drifted the moment the surface grew. That
// is not a copy mistake, it is a structure that guarantees one — so this
// asserts the structure rather than the words: app.js reads what the markup
// says once, and holds no second copy to disagree with it.
//
// Run directly: `node tests/js/test_toggle_labels.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

const html = read("web/index.html");
const app = read("web/app.js");
const bare = app.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* 1 — the markup holds the labels. -------------------------------------- */

const labelOf = (id) => {
  const found = html.match(new RegExp(`id="${id}"[\\s\\S]*?>([^<]+)</button>`));
  assert.ok(found, `#${id} should be a button in index.html`);
  return found[1].trim();
};

const check = labelOf("check-btn");
const bible = labelOf("bible-btn");

assert.ok(check.length > 3, "the check toggle carries a label");
assert.ok(bible.length > 3, "and so does the bible toggle");

/* 2 — and app.js reads them rather than restating them. ------------------ */

assert.match(
  bare,
  /const CLOSED_LABEL = \{\s*bible: bibleBtn\.textContent\.trim\(\),\s*check: checkBtn\.textContent\.trim\(\),/,
  "the closed label is read off the markup once, so there is nothing here to " +
    "drift away from what the page actually says"
);
assert.match(bare, /checkBtn\.textContent = mode === "check" \? "Back to the drawers" : CLOSED_LABEL\.check/);
assert.match(bare, /bibleBtn\.textContent = mode === "bible" \? "Back to the drawers" : CLOSED_LABEL\.bible/);

for (const label of [check, bible]) {
  assert.ok(
    !bare.includes(`"${label}"`),
    `web/app.js must not hold its own copy of ${JSON.stringify(label)} — that ` +
      "second copy is what kept the button saying 'Check a scene' after the " +
      "panel learned to sweep a draft"
  );
}

/* 3 — the panel says what it now actually takes. ------------------------- */
//
// Not a style note. The strip that explains the sweep only appears AFTER a
// draft is pasted, so every word before that point is the entire discoverable
// surface of the feature.

assert.match(check, /script/i, "the door names the script, not one scene");
assert.match(
  html,
  /<h3 id="check-heading"[^>]*>[^<]*script[^<]*<\/h3>/i,
  "and so does the panel's own heading"
);
assert.match(
  html,
  /for="scene">[^<]*draft[^<]*<\/label>/i,
  "and the box says a whole draft is welcome in it"
);

console.log("ok - a toggle's label lives in one place, and it is the markup");
