// Guards every failure message in the app against being silent.
//
// THE GAP. Every failure the app can show — including the one saying the
// department cannot be reached at all — appeared with no role and no live
// region. #intake-error and #check-error were bare spans written via
// textContent. The only role="status" in web/ sat beside one of them, on the
// sibling that carries the working line rather than the failure.
//
// WHY alert AND NOT status. A failure has to interrupt; that is the whole
// distinction between the two roles. #check-error deliberately ships next to a
// role="status" sibling: the status region says the department is working, the
// alert says it did not, and only one of the pair is ever non-empty.
//
// WHY #auth-error IS EMPTY IN THE MARKUP. It used to ship its sentence and be
// revealed by removing .hidden. role="alert" is specified to announce on
// becoming visible OR on content change, and implementations genuinely differ
// on the first — so the fix is not "a class change fires nothing", it is
// "content change is the half everything supports". app.js owns the sentence
// and writes it at both reveal sites.
//
// WHY THE ROLE IS NOT ON .consent-refusal AS A CLASS. Six of that class's seven
// construction sites build the paragraph with its text already inside, as
// static first-paint prose. A class-wide role would make six paragraphs
// assertive live regions at page load — the same defect this file exists to
// fix, six times over. Only consent.js's buildDecide pair is created empty and
// written into later, so only that pair takes a role, imperatively.
//
// Every assertion below is a statement about source text. Whether a real screen
// reader speaks these at the right moment is a manual check this file cannot
// make and does not claim to.
//
// Run directly: `node tests/js/test_failures_announced.mjs` (exit 0 = pass).

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
const consent = stripComments(read("web/consent.js"));
const consentCss = read("web/consent.css");

/* 1 — the two form errors announce, and ship empty so they can. ---------- */

for (const id of ["intake-error", "check-error"]) {
  const tag = html.match(new RegExp(`<span id="${id}"[^>]*>`));
  assert.ok(tag, `#${id} should still exist`);
  assert.match(
    tag[0],
    /role="alert"/,
    `#${id}: a failure the reader caused by submitting has to interrupt, and ` +
      `ARIA19 is the canonical technique for a post-submit form error`
  );
  // Empty in the markup is what makes the role work: alert fires on the text
  // being written in, and there is nothing to write over.
  const shipped = html.match(new RegExp(`<span id="${id}"[^>]*>([\\s\\S]*?)</span>`));
  assert.equal(
    shipped[1].trim(),
    "",
    `#${id} must ship empty — prose here announces at first paint or not at ` +
      `all, depending on the reader's software`
  );
}

/* 2 — the working line stays polite, right beside the alert. ------------- */

const status = html.match(/<span id="check-status"[^>]*>/);
assert.ok(status, "#check-status should still exist");
assert.match(
  status[0],
  /role="status"/,
  "the department working is not an emergency; only the failure interrupts"
);
assert.doesNotMatch(
  status[0],
  /role="alert"/,
  "promoting this to alert would make every working line interrupt, which is " +
    "the babbling the search meter was deliberately denied a live region over"
);

/* 3 — the banner ships empty with the role, and app.js owns the words. --- */

const banner = html.match(/<div id="auth-error"[^>]*>([\s\S]*?)<\/div>/);
assert.ok(banner, "#auth-error should still exist");
assert.match(banner[0], /role="alert"/, "the department being unreachable interrupts");
assert.equal(
  banner[1].trim(),
  "",
  "#auth-error must ship empty: it used to carry its sentence and appear by " +
    "having .hidden removed, and a class change is not a trigger every " +
    "assistive technology is required to announce"
);

assert.match(
  app,
  /const AUTH_UNREACHABLE =\s*\n?\s*"Could not start a session with the department\. Check your connection and reload\.";/,
  "the sentence moved to app.js unchanged — this is a plumbing fix, not a " +
    "rewrite of what the reader is told"
);

// Every reveal and every hide goes through the one function, or the banner can
// still be shown by a class change that announces nothing.
assert.doesNotMatch(
  app,
  /\$\("auth-error"\)\.classList\.(remove|add)\("hidden"\)/,
  "no direct .hidden toggling on the banner — that is the bug, and leaving " +
    "one call site is leaving the bug"
);
const reveals = app.match(/showAuthError\(true\)/g) || [];
assert.equal(
  reveals.length,
  2,
  "both reveal sites should route through showAuthError: the build path and " +
    "the resume path each fail auth independently"
);

/* 4 — hiding clears the text. This is the load-bearing half. ------------- */

const fn = app.match(/function showAuthError\(show\) \{([\s\S]*?)\n\}/);
assert.ok(fn, "showAuthError should exist");
assert.match(
  fn[1],
  /replaceChildren\(\)/,
  "clearing on hide is what makes the next reveal an empty-to-text mutation " +
    "rather than the same words written over themselves, which a screen " +
    "reader may treat as nothing new"
);
assert.doesNotMatch(
  fn[1],
  /replaceChildren\(""\)/,
  "replaceChildren(\"\") appends an empty text node and leaves the element " +
    "non-empty to CSS and to the accessibility tree"
);

/* 5 — the consent pair takes roles, and the right ones. ------------------ */

assert.match(
  consent,
  /const status = el\("p", "consent-status"\);\s*\n\s*status\.setAttribute\("role", "status"\);/,
  "WORKING and ATTACHING are progress, and progress that interrupts is the " +
    "same defect as a babbling meter"
);
assert.match(
  consent,
  /const refusal = el\("p", "consent-refusal"\);\s*\n\s*refusal\.setAttribute\("role", "alert"\);/,
  "the reader's answer not going through interrupts"
);

/* 6 — and the six that ship prose do NOT. -------------------------------- */

const withText = consent.match(/el\("p", "consent-refusal", [A-Z_]+\)/g) || [];
assert.equal(
  withText.length,
  6,
  "six refusal paragraphs are built with their text already in them; if this " +
    "count moves, re-derive whether a class-wide role is still wrong before " +
    "changing anything"
);
const empty = consent.match(/el\("p", "consent-refusal"\)/g) || [];
assert.equal(empty.length, 1, "exactly one is created empty and written into later");

// The prohibition itself: no sweep that would reach the other six.
assert.doesNotMatch(
  consent,
  /querySelectorAll\(["'`]\.consent-(refusal|status)/,
  "a class-wide sweep would make six static paragraphs assertive live regions " +
    "at page load — the defect this file fixes, six times over"
);
assert.equal(
  (consent.match(/setAttribute\("role", "alert"\)/g) || []).length,
  1,
  "one alert on this page, on the one element that can receive text later"
);

/* 7 — an empty live region must stay in the tree. ------------------------ */

// A region that is display:none while empty was never registered, so the write
// that fills it has no region to fire in. The :empty rules here zero a margin
// and nothing else, which is why the roles above work at all.
const emptyRule = consentCss.match(
  /\.consent-status:empty,\s*\n\.consent-decide \.consent-refusal:empty \{([\s\S]*?)\}/
);
assert.ok(emptyRule, "the :empty rules should still exist");
assert.doesNotMatch(
  emptyRule[1],
  /display\s*:\s*none|visibility\s*:\s*hidden/,
  "hiding an empty live region unregisters it, and the text written into it " +
    "later announces nothing. Zeroing the margin is the whole intent here"
);

/* 8 — no library was reached for. ---------------------------------------- */

assert.doesNotMatch(
  html,
  /<script[^>]+src="(?:https?:)?\/\//,
  "invariant 6: this fix is four attributes, one constant and one function"
);

console.log("test_failures_announced.mjs: 20 assertions passed");
