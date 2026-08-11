// Guards the writer's own pasted pages against being unreachable by keyboard.
//
// THE GAP. scene.css caps .scene-page at 32rem and scrolls it, and a scene runs
// to config.max_scene_chars() — 8000 characters, roughly four script pages. A
// scroller is only reachable by keyboard if it is a tab stop or holds one, and
// the zero-marks state is DESIGNED FOR: server.py writes a dedicated cover note
// for a scene of pure interior dialogue that asserts nothing about the world,
// and the rail ships bespoke copy for it. In that state the box holds no
// focusable child at all, so a keyboard-only reader could not reach the text
// they pasted.
//
// Safari alone, now. Firefox has made scrollers tab stops since Firefox 4
// (2011) and Chrome since stable 132 — corrected from the register row, which
// said two engines and Chrome 127.
//
// WHY ALL THREE ATTRIBUTES ARE ASSERTED TOGETHER. A tab stop with no accessible
// name is worse than no tab stop: it is a stop that announces nothing. A name
// with no tab stop does not make the box reachable. And a name on a bare div is
// an authoring-conformance error, because `generic` is name-prohibited — though
// Chromium does expose it in practice, measured on 2026-08-11 as
// `generic "The scene, with each checked line marked"`. So the role is not what
// makes this named; the tab stop is the fix and the role makes the existing name
// legitimate.
//
// Run directly: `node tests/js/test_scene_reachable.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

import { loadPatchedModule, readSource, stubDocument, walk, withClass } from "./_scriptcheck_module.mjs";

globalThis.document = stubDocument();

const { renderCheckResult } = await import(loadPatchedModule());

const SCENE = "She sits with it a while, and decides nothing.";

/* 1 — the three attributes, and all three of them. ----------------------- */

const marked = renderCheckResult({
  claims: [{ text: "She sits with it", verdict: "confirmed", sources: [] }],
  scene: SCENE,
});
const page = withClass(marked, "scene-page")[0];
assert.ok(page, ".scene-page should still be built");

assert.equal(
  page.getAttribute("tabindex"),
  "0",
  "a real tab stop, not -1: nothing sends focus here, so the reader has to be " +
    "able to arrive under their own power"
);
assert.equal(
  page.getAttribute("role"),
  "region",
  "region over group — the marked scene is a major perceivable section, which " +
    "is the case MDN says group should not carry, and region earns a landmark"
);
assert.ok(
  page.getAttribute("aria-label"),
  "a tab stop with no name is a stop that announces nothing, which is worse " +
    "than the gap this fixes"
);

/* 2 — the zero-marks state, which is the one that stranded people. ------- */

const bare = renderCheckResult({ claims: [], scene: SCENE });
const barePage = withClass(bare, "scene-page")[0];
assert.ok(barePage, "a scene with no marks still renders its page");

// The precondition of the finding: nothing inside is focusable.
const focusableInside = walk(barePage).filter(
  (n) => n.nodeType === 1 && n !== barePage && n.getAttribute("tabindex") !== null
);
assert.equal(
  focusableInside.length,
  0,
  "this is the designed-for state the finding turns on — a scene that asserts " +
    "nothing about the world produces no marks, so the scroller holds no " +
    "focusable child and the container itself has to be the stop"
);
assert.equal(
  barePage.getAttribute("tabindex"),
  "0",
  "so the container is the stop, unconditionally"
);
assert.ok(barePage.getAttribute("aria-label"), "and it is named in that state too");

/* 3 — two nested regions must not answer to the same name. --------------- */

// F-006 made the result body a region as well. Nesting is legal and useful
// here, but two landmarks reading identically would be worse than one.
assert.equal(marked.getAttribute("role"), "region", "the result body is the outer region");
assert.notEqual(
  marked.getAttribute("aria-label"),
  page.getAttribute("aria-label"),
  "the outer region says what landed and the inner names the scene — two " +
    "landmarks with one name is a worse tree than no landmark"
);

/* 4 — the stop is permanent by choice, not by accident. ------------------ */

const source = readSource()
  .replace(/\r\n/g, "\n")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .filter((line) => !/^\s*\/\//.test(line))
  .join("\n");

const build = source.match(/function buildScenePage\([\s\S]*?\n\}/);
assert.ok(build, "buildScenePage should still exist");
assert.doesNotMatch(
  build[0],
  /scrollHeight|clientHeight|offsetHeight|ResizeObserver/,
  "the tab stop is not conditional on measured overflow. That would mean " +
    "re-measuring on every reflow, font swap and resize, and a tab stop that " +
    "comes and goes is worse than one that is always there"
);

// All three set on the same element, in one place, so they cannot drift apart.
for (const attr of ['"role", "region"', '"tabindex", "0"', '"aria-label"']) {
  assert.ok(
    build[0].includes(`page.setAttribute(${attr}`),
    `${attr} belongs on .scene-page beside the other two`
  );
}

console.log("test_scene_reachable.mjs: 12 assertions passed");
