// The campaign's last four rows, and three of them are the same defect.
//
// F-023, F-022 and F-024 are all "something the reader did left them with
// nowhere to stand". Two were filed BY earlier builds rather than by the audit
// — wave 3 found them while fixing F-006 and declined them as drive-bys — and
// the third is the same mechanism a third time. F-015 is unrelated and is here
// because it is what was left.
//
// F-023 is F-006's mechanism on the intake surface. Measured in Chromium:
// focus build-btn, disable it, activeElement is BODY, re-enable, still BODY.
// Both of buildRoom's failure exits leaked it, and F-010's role="alert" does
// not help — an alert announces wherever focus sits, and gives a keyboard
// reader nowhere to stand afterwards.
//
// F-022's fix is focus rather than a role, and that is a mechanical choice
// rather than a preference: both account refusals are built WITH their text by
// renderAccountCard inside a subtree draw() inserts whole, so a role on them is
// the fragile insert-with-text alert — and here, unlike the progress timeline's
// first entry, it is every announcement there is rather than one of many.
// renderAccountCard also has to stay pure, which test_token_retention.mjs
// guards.
//
// F-024 keeps the rebuild the code argues for and pays its cost back.
// openFiledCheck rebuilds the filed row so one path decides aria-current; that
// reasoning is sound, and it destroys the button the reader pressed.
//
// Run directly: `node tests/js/test_last_four.mjs` (exit 0 = pass).

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
const account = strip(read("web/account.js"));
const check = strip(read("web/scriptcheck.js"));

/* F-015 — the failure is stated once. ----------------------------------- */

assert.doesNotMatch(
  app,
  /Something broke/,
  "the server's own sentence already declares the failure in its first clause, " +
    "in both messages it can send: '...was stopped before anything could be " +
    "filed' and '...hit an unexpected problem and stopped'"
);
assert.match(
  app,
  /addEntry\("error", escapeHtml\(ev\.message\)\)/,
  "the message still renders, and still escaped — addEntry writes innerHTML"
);

/* F-023 — both of buildRoom's failure exits hand focus back. ------------- */

const build = app.match(/async function buildRoom\(\) \{([\s\S]*?)\n\}/);
assert.ok(build, "buildRoom should still exist");
assert.equal(
  (build[1].match(/\$\("build-btn"\)\.focus\(\)/g) || []).length,
  2,
  "the auth failure and the request failure are two exits and both leaked. " +
    "One fixed exit is half a fix"
);

// Order is load-bearing: focus() on a disabled element does nothing.
for (const exit of build[1].split('$("build-btn").focus()').slice(0, -1)) {
  const enable = exit.lastIndexOf('$("build-btn").disabled = false');
  assert.ok(
    enable > -1,
    "each focus call must be preceded by the re-enable — focus() on a disabled " +
      "button is a no-op, so the wrong order looks right and does nothing"
  );
}

/* F-022 — the account refusals reach somebody. -------------------------- */

assert.match(
  account,
  /if \(patch\.issueError \|\| patch\.linkMessage\) focusRefusal\(\);/,
  "a refusal the reader just caused sends the reader to it"
);
assert.match(account, /function focusRefusal\(\)/, "and there is one place that does it");

const focusFn = account.match(/function focusRefusal\(\) \{([\s\S]*?)\n\}/);
assert.ok(focusFn, "focusRefusal should exist");
assert.match(
  focusFn[1],
  /setAttribute\("tabindex", "-1"\)/,
  "reachable programmatically and never by Tab: it is a sentence, not a control"
);
assert.match(focusFn[1], /\.focus\(\)/, "and it actually takes focus");

// Only on a patch that carries one. redraw clears issueError on every other
// path, so an ordinary revoke or a fresh read must not steal focus.
const redraw = account.match(/function redraw\(patch = \{\}\) \{([\s\S]*?)\n\}/);
assert.match(
  redraw[1],
  /issueError: ""/,
  "redraw still clears the refusal by default, which is what makes the guard " +
    "above mean 'this draw carries a new one'"
);

// The render path stays pure — no role, no focus, anywhere in the module's
// rendering. Scoping this to renderAccountCard's own body is not enough: the
// refusals are built in helpers it calls, and a role added there sailed
// straight through the first version of this assertion.
assert.ok(
  account.includes("export function renderAccountCard("),
  "renderAccountCard should still exist"
);
assert.doesNotMatch(
  account,
  /"account-refusal"[\s\S]{0,120}?setAttribute\("role"/,
  "no role on a refusal: both are built WITH their text inside a subtree " +
    "draw() inserts whole, which is the fragile insert-with-text alert, and " +
    "here it would be every announcement there is rather than one of many"
);
assert.equal(
  (account.match(/\.focus\(\)/g) || []).length,
  1,
  "exactly one focus call in this module, and it is focusRefusal's. A second " +
    "means the renderer started doing I/O, which test_token_retention guards " +
    "against by exercising it on a stubbed document"
);

/* F-024 — the filed row hands the press back. --------------------------- */

assert.match(check, /let focusFiledAfterLoad = null;/, "the intent is a module-level flag");
assert.match(
  check,
  /if \(focusFiledAfterLoad === id\) button\.focus\(\);/,
  "the rebuilt row for the scene that was opened takes focus back"
);
assert.match(
  check,
  /focusFiledAfterLoad = sceneId;/,
  "set by openFiledCheck, so the panel's FIRST open cannot pull focus out of " +
    "whatever the reader was using"
);
// Cleared after the rebuild. Asserted as a COUNT, because the declaration
// `let focusFiledAfterLoad = null` satisfies a bare pattern all by itself —
// which is how a build that never cleared the flag passed this test once.
assert.equal(
  (check.match(/focusFiledAfterLoad = null;/g) || []).length,
  2,
  "the declaration and the reset. One occurrence means the flag is set and " +
    "never cleared, so a later unrelated load steals focus"
);

// The rebuild itself is untouched. Its argument — one path decides
// aria-current — is sound, and this finding pays its cost rather than
// overturning it.
const loadFiled = check.match(/async function loadFiledChecks\(\) \{([\s\S]*?)\n\}/);
assert.ok(loadFiled, "loadFiledChecks should still exist");
assert.match(
  loadFiled[1],
  /els\.filedList\.replaceChildren\(\);/,
  "the row is still REBUILT rather than patched in place. Asserted inside this " +
    "function: the module has a second replaceChildren on the same element, so " +
    "a whole-file pattern stays green while this one disappears"
);
assert.match(loadFiled[1], /aria-current/, "and aria-current is still decided by that one path");

console.log("test_last_four.mjs: 18 assertions passed");
