// Guards the drawer a reader just pressed against leaving the screen.
//
// THE DEFECT. Expanding a RIGHT-column drawer sends it to the next grid row,
// full width, below a first row that already runs past the fold. Measured on the
// filed Gdansk room, every drawer, from a room scrolled to its top with the rest
// closed:
//
//     drawer 1 (left)   351 -> 351    0px
//     drawer 2 (right)  351 -> 974   +623px, ends 84px BELOW the fold
//     drawer 3 (left)  1089 -> 1089   0px
//     drawer 4 (right) 1089 -> 1690  +602px, ends 800px below
//
// Viewport 890, and #stage is the scroller rather than the document. Drawer 2 is
// the whole finding: on screen when it is clicked, gone when the click resolves,
// so the press reads as dead.
//
// TWO CORRECTIONS TO THE REGISTER'S FIX, both deliberate:
//
//   - It scrolls the CARD, not the toggle. The toggle sits below the drawer's
//     plate, so aligning it to the top of the scroller cuts the head off the
//     very thing the reader asked to see.
//   - The call is in the CLICK HANDLER, not inside setOpen. setOpen(false) runs
//     once at construction for all four drawers, and a future caller restoring
//     an expanded drawer must not yank the page around.
//
// AND ONE QUESTION THE BRIEF LEFT OPEN, answered by measuring rather than
// arguing: closing does NOT need a scroll. With the card open at top 28 and the
// scroller at 946, closing returns the card to top 28 with the scroller at 323 —
// the browser's own scroll anchoring compensates when content above the viewport
// shrinks. A close-side scroll would fight it.
//
// Source assertions: web/app.js takes eleven element references and wires
// listeners at module evaluation, so it does not import against the stub.
//
// Run directly: `node tests/js/test_drawer_expand_scroll.mjs` (exit 0 = pass).

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
const css = read("web/drawer.css");

/* 1 — the press scrolls, and only when it opens. ------------------------- */

const handler = app.match(/toggle\.addEventListener\("click", \(\) => \{([\s\S]*?)\n {2}\}\);/);
assert.ok(handler, "the toggle's click handler should still exist");
assert.match(
  handler[1],
  /scrollIntoView/,
  "a press that moves the card 623px off screen has to take the reader with it"
);
assert.match(
  handler[1],
  /if \(open\)/,
  "opening only. Closing needs no scroll — measured: the card stays visible " +
    "because the browser's scroll anchoring already compensates"
);

/* 2 — it scrolls the card, not the toggle. ------------------------------- */

assert.match(
  handler[1],
  /el\.scrollIntoView/,
  "the card. Aligning the toggle to the top of the scroller would cut off the " +
    "drawer's own plate, which is the part that names what just opened"
);
assert.doesNotMatch(handler[1], /toggle\.scrollIntoView/, "not the toggle");
assert.match(handler[1], /block: "start"/, "top-aligned, so the whole card is reachable");

/* 3 — reduced motion is honoured through the existing helper. ------------ */

assert.match(
  handler[1],
  /behavior: scrollBehavior\(\)/,
  "scrollBehavior() reads matchMedia at call time and returns 'auto' under " +
    "reduce. This is its second consumer — the thing F-006's row wrongly " +
    "claimed to be, since a focus-driven scroll takes no behavior option"
);
assert.match(app, /function scrollBehavior\(\)/, "and the helper still exists");

/* 4 — construction does not scroll. -------------------------------------- */

const setOpen = app.match(/const setOpen = \(open\) => \{([\s\S]*?)\n {2}\};/);
assert.ok(setOpen, "setOpen should still exist");
assert.doesNotMatch(
  setOpen[1],
  /scrollIntoView/,
  "setOpen(false) runs at construction for all four drawers; a scroll in here " +
    "would fire on render and on any future state restore"
);

/* 5 — the tab is not sliced off by the alignment. ------------------------ */

const drawer = css.match(/\n\.drawer \{([\s\S]*?)\n\}/);
assert.ok(drawer, ".drawer rule should still exist");
assert.match(
  drawer[1],
  /scroll-margin-top: var\(--tab-rise, 1\.75rem\)/,
  "the cut tab is absolutely positioned --tab-rise above this box, so aligning " +
    "the box to the top of the scroller would slice it off. Same value and " +
    "same fallback the tab's own `top` uses, so the two cannot drift"
);

// The tab really is positioned by that variable, which is what makes sharing it
// correct rather than coincidental.
const tab = css.match(/\.drawer-tab \{([\s\S]*?)\n\}/);
assert.match(
  tab[1],
  /top: calc\(var\(--tab-rise, 1\.75rem\) \* -1\)/,
  "if the tab stops being positioned by --tab-rise, the scroll margin above is " +
    "no longer the right number and this test should say so"
);

console.log("test_drawer_expand_scroll.mjs: 11 assertions passed");
