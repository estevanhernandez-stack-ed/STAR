// Guards the values this wave collapsed against being written out twice again.
//
// THE SHAPE. Six rows of the register share it: a value declared more than once
// and drifting apart. Two of them (F-017, F-019) render byte-identical pixels,
// and wave 3 passed on them for exactly that reason — so the argument for doing
// them is F-016, where the same duplication had ALREADY drifted far enough to be
// visible. Measured before the fix: the bible and the docket stack in one column
// and share a left edge at x=348, but their first characters sat at x=384 and
// x=376. An 8px step between two full-width cards, from a 36px inset against a
// 28px one.
//
// So this file is mostly prohibitions. The values are correct today; what it
// guards is that they stay in ONE place, because the app has already shown what
// the second copy becomes.
//
// Run directly: `node tests/js/test_said_once.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

const shell = read("web/shell.css");
const clip = read("web/clip.css");
const scene = read("web/scene.css");
const bible = read("web/bible.css");
const consent = read("web/consent.css");
const tokens = read("web/tokens.css");

/** The body of a top-level rule, by its exact selector text. Anchored to the
 *  line start so `.clip` cannot match inside `.clip-stamp`. */
function rule(css, selector) {
  const at = css.indexOf(`\n${selector} {`);
  if (at === -1) return null;
  const open = css.indexOf("{", at);
  const close = css.indexOf("\n}", open);
  return close === -1 ? null : css.slice(open + 1, close);
}

const paddingOf = (body, what) => {
  assert.ok(body, `${what} should still exist`);
  const m = body.match(/padding: ([^;]+);/);
  assert.ok(m, `${what} should still declare padding`);
  return m[1].trim();
};

/* F-019 — the onionskin fragment is declared once. ----------------------- */

const shared = rule(shell, ".clip,\n.rail-card");
assert.ok(shared, ".clip and .rail-card should share one rule in shell.css");
for (const decl of [
  "background: var(--onionskin);",
  "border-radius: 3px;",
  "border-left: 3px solid var(--manila-edge);",
  "padding: 0.95rem 1.1rem 1rem;",
]) {
  assert.ok(shared.includes(decl), `the shared rule keeps "${decl}"`);
}

// Neither component re-declares the stock it was cut from.
assert.equal(rule(clip, ".clip"), null, "web/clip.css must not re-declare .clip's base");
assert.equal(rule(scene, ".rail-card"), null, "web/scene.css must not re-declare .rail-card's base");

// The state recolours DO stay in their own files — they are the component's
// business, and they are attribute selectors that outrank the shared rule
// regardless of load order.
assert.match(clip, /\.clip\[data-unsourced/, "clip.css keeps its own state recolour");
assert.match(scene, /\.rail-card\[data-verdict/, "scene.css keeps its own state recolour");

// The narrow-viewport override was the same three values twice, and collapsed.
assert.match(
  shell,
  /\.clip,\n {2}\.rail-card \{\n {4}padding: 0\.8rem 0\.75rem 0\.85rem;/,
  "the 560px padding is shared too"
);
for (const [css, name] of [
  [clip, "clip.css"],
  [scene, "scene.css"],
]) {
  assert.doesNotMatch(
    css,
    /padding: 0\.8rem 0\.75rem 0\.85rem/,
    `${name} must not keep its own copy of the narrow-viewport padding`
  );
}

// .scene-page is a consumer with an override, not a third copy of the stock.
assert.ok(rule(scene, ".scene-page"), ".scene-page keeps its own rule");
assert.match(scene, /max-height: 32rem/, "because it carries eight declarations of its own");

/* F-017 — the UNSOURCED block, built twice, now built once. -------------- */

for (const [selector, marker, why] of [
  [".clip-unsourced,\n.rail-unsourced", "border-top: 1px solid", "the divider above the block"],
  [".clip-stamp,\n.rail-unsourced-stamp", "color: var(--oxide)", "the stamp itself"],
  [".unsourced-urls,\n.rail-unsourced-urls", "list-style: none", "the list"],
  [".unsourced-url,\n.rail-unsourced-url", "overflow-wrap: anywhere", "each url"],
]) {
  const body = rule(shell, selector);
  assert.ok(body, `${why}: should be one shared rule in shell.css`);
  assert.ok(body.includes(marker), `${why}: keeps "${marker}"`);
}

// Neither file re-declares any of the eight.
for (const [css, name, sels] of [
  [clip, "clip.css", [".clip-unsourced", ".clip-stamp", ".unsourced-urls", ".unsourced-url"]],
  [scene, "scene.css", [".rail-unsourced", ".rail-unsourced-stamp", ".rail-unsourced-urls", ".rail-unsourced-url"]],
]) {
  for (const sel of sels) {
    assert.equal(rule(css, sel), null, `${name} must not re-declare ${sel}`);
  }
}

// The orphan stays. The check surface never built a twin for it, and inventing
// one to make the merge symmetrical would ship a rule nothing uses.
assert.ok(rule(clip, ".clip-stamp-note"), ".clip-stamp-note stays in clip.css");
assert.equal(rule(scene, ".rail-stamp-note"), null, "and gains no invented twin");

// The two ratios that were split across the two copies both survive, because a
// merged rule that keeps neither is how a measured pair becomes an unmeasured
// one. Invariant 5.
assert.match(shell, /4\.75:1 on --onionskin/, "the stamp's oxide ratio is recorded");
assert.match(shell, /6\.24:1 on --onionskin/, "and the url's");

/* F-016 — the card padding that drifted, and the count it drifted from. --- */

const bibleP = paddingOf(rule(bible, ".bible"), ".bible");
const docketP = paddingOf(rule(shell, ".docket"), ".docket");
assert.equal(
  bibleP,
  "1.5rem 1.75rem 1.6rem",
  "the bible takes the docket's inset: it stacks directly under it and shares " +
    "a left edge, so a different inset is a visible step between two cards"
);
assert.equal(bibleP, docketP, "and it is the SAME value, not merely a similar one");

// Three distinct card paddings became two. A third reappearing IS the finding.
const surfaces = [
  [shell, ".docket"],
  [shell, ".intake"],
  [scene, ".check"],
  [read("web/account.css"), ".account"],
  [consent, ".consent"],
  [bible, ".bible"],
];
const distinct = new Set(surfaces.map(([css, sel]) => paddingOf(rule(css, sel), sel)));
assert.equal(
  distinct.size,
  2,
  `six card surfaces, two paddings. Got ${distinct.size}: ${[...distinct].join(" / ")}. ` +
    `The bible's third value was the one that shipped a visible break`
);

/* F-020 — the wordmark's star is sized once. ----------------------------- */

assert.match(tokens, /--mark-lg: 1\.7rem;/, "the size lives in tokens.css");
for (const [css, name] of [
  [shell, "shell.css"],
  [consent, "consent.css"],
]) {
  const mark = rule(css, ".star-mark");
  assert.ok(mark, `${name} should still style .star-mark`);
  assert.match(mark, /font-size: var\(--mark-lg\)/, `${name} takes the token`);
  assert.doesNotMatch(mark, /1\.7rem/, `${name} keeps no literal`);
}

// The token, NOT a stylesheet link.
const consentHtml = read("web/consent.html");
assert.doesNotMatch(
  consentHtml,
  /href="\/shell\.css"/,
  "linking shell.css to reach one declaration imports 36.5KB and three " +
    "unmeasured globals onto the one screen where a reader hands something " +
    "away: `a` at 4.37:1 on manila, :focus-visible at 1.88:1, and a body flex " +
    "layout consent.css does not override"
);
assert.equal(
  (consentHtml.match(/rel="stylesheet"/g) || []).length,
  2,
  "tokens.css and consent.css, and that is the whole list"
);

console.log("test_said_once.mjs: 45 assertions passed");
