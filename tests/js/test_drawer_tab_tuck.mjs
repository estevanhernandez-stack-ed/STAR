// Guards the hanging folder against reading as a label stuck on a box.
//
// THE DEFECT. drawer.css:96-108 documents the construction on the record: a
// hanging folder's cut tab is part of the BACK panel, it rises above the front
// face, and its base is hidden behind it. "A tab painted on top reads as a label
// stuck on a box." The paint order is correct — ::after -1, tab 0, face
// ::before 1, content 2 — but the numbers gave the face nothing to occlude.
//
// Measured before the change, on the filed Gdansk room: the tab sits at
// top: -28px and stood 29.6px tall, so exactly 1.6px of its base fell under the
// face. The register filed it as 0px from a pixel scan of the render; both
// figures are true, because the clip-path makes the painted extent narrower
// than the box and 1.6px at a sloped edge scans as nothing.
//
// After: 37.6px tall, 9.6px of tuck. The visible tab is UNCHANGED — only the
// top padding positions the label, so this adds hidden height and nothing a
// reader can see moves.
//
// WHY THE CLIP-PATH MOVED WITH IT. Those coordinates are percentages of the
// box, so a taller tab with the same numbers is a differently-angled tab.
// Measured: with the old percentages the sides reached 2.77px of inset at the
// face line where they used to reach 0.59px, leaving the visible tab's bottom
// edge ~4.4px narrower and its taper visibly shallower. Carrying the slope past
// the box restores it — re-measured at 0.62px against the original 0.59px.
//
// The geometry above was verified in a browser against a cache-busted
// stylesheet. This file guards the values that produced it; it cannot recompute
// them, because the tab's height depends on the label's font metrics.
//
// Run directly: `node tests/js/test_drawer_tab_tuck.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../../web/drawer.css", import.meta.url), "utf8").replace(
  /\r\n/g,
  "\n"
);

const tab = css.match(/\.drawer-tab \{([\s\S]*?)\n\}/);
assert.ok(tab, ".drawer-tab should still exist");

/* 1 — the tuck itself. --------------------------------------------------- */

const padding = tab[1].match(/padding: ([^;]+);/);
assert.ok(padding, ".drawer-tab should still declare padding");
const [top, sides, bottom] = padding[1].trim().split(/\s+/);
assert.equal(top, "0.4rem", "the top padding positions the label and must not move");
assert.equal(sides, "1.15rem", "the sides are unrelated to the tuck");
assert.equal(
  bottom,
  "1.05rem",
  "the bottom padding IS the tuck: +8px of height with the top edge pinned by " +
    "--tab-rise puts ~9.6px of base under the face, where 0.55rem left 1.6px"
);

/* 2 — the top edge is still pinned by the variable the tuck is measured from. */

assert.match(
  tab[1],
  /top: calc\(var\(--tab-rise, 1\.75rem\) \* -1\)/,
  "the tuck is (tab height - tab rise). If the rise stops driving the top, the " +
    "8px above is no longer the right number"
);

/* 3 — the cut was re-sloped for the taller box. -------------------------- */

const clip = tab[1].match(/clip-path: polygon\(([^)]*)\)/);
assert.ok(clip, ".drawer-tab should still be cut");
assert.match(
  clip[1],
  /6% 0%, 94% 0%/,
  "the crown is unchanged — that is the part of the taper a reader sees most"
);
assert.match(
  clip[1],
  /101\.6% 100%, -1\.6% 100%/,
  "the slope carries past the box so the sides keep their original angle. " +
    "Leaving these at 100%/0% re-slopes the cut against a 27% taller box and " +
    "flattens the visible taper by ~4.4px across the bottom edge"
);

/* 4 — the layering this depends on is still documented and still correct. - */

assert.match(
  css,
  /0\s+\.drawer-tab\s+the cut tab/,
  "the paint-order comment is what makes the tuck meaningful: the tab is " +
    "BEHIND the face, so extra height at its base is hidden rather than stacked"
);
// Scoped to the tab's own block. Asserting this against the whole file passes
// on `.drawer { z-index: 0 }` and says nothing about the tab — which is how a
// mutation putting the tab at z-index 3 got through the first version of this.
assert.match(
  tab[1],
  /z-index: 0;/,
  "the tab still sits at 0, under the face's ::before at 1. Paint it above and " +
    "the tuck becomes invisible: extra height at the base stacks ON the face " +
    "instead of hiding behind it, which is the defect the layering prevents"
);

console.log("test_drawer_tab_tuck.mjs: 9 assertions passed");
