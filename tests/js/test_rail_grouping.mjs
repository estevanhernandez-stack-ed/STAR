// A story spanning five eras is one body of work, not five strangers.
//
// THE BUG. The rail sorted newest-first and knew nothing about relationships,
// so a writer researching one story across Liverpool '58, Hamburg '60, the '64
// tour and the '69 rooftop got four unrelated rows in reverse order. That is
// the fragmentation a writer feels on their second room, and it is the same
// wound the judge reported from the other end as "room hygiene".
//
// WHY THIS ONE RUNS THE CODE. Unlike the other browser guards here, `orderRail`
// and `chainSize` are pure functions of a list — no DOM, no module-evaluation
// element grabs — so they can be imported and actually executed. Source
// assertions are the fallback for code that cannot be loaded, not the goal.
// web/shell.js does touch the DOM at import, so the two functions are read out
// of the source and evaluated in isolation rather than importing the module.
//
// The rendering half — indent, hairline, which row carries `.follows` — is
// checked in a live browser, because this morning proved that a source
// assertion about markup is a statement about source, not about a page.
//
// Run directly: `node tests/js/test_rail_grouping.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8");

const source = read("web/shell.js");

/* Lift the two pure functions out and evaluate them. Reading the real source
   rather than restating the algorithm: a copy in the test is a second
   implementation, and it would pass while the app's own drifted. */
function lift(name) {
  const match = source.match(
    new RegExp(`export function ${name}\\(([\\s\\S]*?)\\n\\}`)
  );
  assert.ok(match, `${name} should still be exported from web/shell.js`);
  return new Function(`return function ${name}(${match[1]}\n}`)();
}

const orderRail = lift("orderRail");
const chainSize = lift("chainSize");

const room = (id, continues = "") => ({ run_id: id, continues, title: id });
const ids = (rooms) => rooms.map((r) => r.run_id);

/* 1 — a story reads down, in the order it was written. -------------------- */

assert.deepEqual(
  ids(orderRail([room("c", "b"), room("b", "a"), room("a")])),
  ["a", "b", "c"],
  "a chain should read oldest first — a story told newest-first is a story " +
    "told backwards"
);

/* 2 — standalone rooms keep the order they arrived in. -------------------- */

assert.deepEqual(
  ids(orderRail([room("new"), room("old")])),
  ["new", "old"],
  "rooms that belong to nothing keep the rail's existing newest-first order; " +
    "this feature reorders stories, it does not reorder the rail"
);

/* 3 — a story stays together, and does not scatter its members. ----------- */

const mixed = orderRail([
  room("loose-new"),
  room("era-2", "era-1"),
  room("loose-old"),
  room("era-1"),
]);
const positions = ids(mixed);
assert.equal(
  positions.indexOf("era-2") - positions.indexOf("era-1"),
  1,
  "a room should sit immediately under the room it follows, whatever else is " +
    "in the list"
);
assert.equal(mixed.length, 4, "grouping must not drop or duplicate a room");

/* 4 — branches: two rooms following the same one. ------------------------- */

const branched = ids(
  orderRail([room("root"), room("first", "root"), room("second", "root")])
);
assert.deepEqual(
  branched,
  ["root", "first", "second"],
  "two rooms can follow the same one — a story that forks is still one story, " +
    "and both branches belong under their root in the order they were made"
);

/* 5 — a link to a room that is not here is no link at all. ---------------- */

assert.deepEqual(
  ids(orderRail([room("orphan", "deleted-and-purged"), room("plain")])),
  ["orphan", "plain"],
  "a room whose parent has been purged keeps its place in the rail rather " +
    "than vanishing into a group whose head does not exist"
);

/* 6 — a ring in the data cannot hang the rail. ---------------------------- */
//
// The endpoint refuses to create one, but data written before that guard
// existed must still draw. A rail that spins is worse than a rail that shows
// an odd order, and this is the browser's own copy of the bound the server's
// cycle check carries.

const ring = orderRail([room("x", "y"), room("y", "x"), room("free")]);
assert.equal(
  ring.length,
  3,
  "every room still gets drawn. Rooms in a ring have no root — each follows " +
    "another that is present — so a walk that only descends from roots cannot " +
    "reach them, and an earlier version dropped both from the rail. Mutation " +
    "testing found it; the assertion before this one only checked that " +
    "something came back."
);
assert.deepEqual(
  ids(ring).sort(),
  ["free", "x", "y"],
  "and the ring's own rooms are among them, not swallowed"
);

/* 7 — every room is drawn exactly once. ----------------------------------- */

const many = [
  room("a"),
  room("b", "a"),
  room("c", "b"),
  room("d", "a"),
  room("e"),
];
const drawn = ids(orderRail(many));
assert.equal(drawn.length, many.length, "no room may be dropped");
assert.equal(new Set(drawn).size, many.length, "and none may be drawn twice");

/* 8 — chainSize counts what a delete would leave behind. ------------------ */

assert.equal(
  chainSize(many, "a"),
  3,
  "b, c and d follow a, directly or further down — the delete warning has to " +
    "count the whole chain, not the first hop"
);
assert.equal(chainSize(many, "e"), 0, "a room nothing follows leaves nothing behind");
assert.equal(
  chainSize([room("x", "y"), room("y", "x")], "x"),
  1,
  "and a ring in the data must not spin the count either"
);

console.log("ok - stories read as stories, and nothing spins");
