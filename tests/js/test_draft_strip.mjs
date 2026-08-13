// A whole draft in the box costs no more than one scene did.
//
// THE THING AT RISK. web/fountain.js splits a ninety-page screenplay into
// fifty scenes and the strip lists them. Fifty scenes next to a button that
// spends live searches is a shape where one wrong wire costs a writer their
// hourly budget in a single click, and star/server.py's limiter would then
// refuse the checks they actually wanted. So the property that matters most
// here is not that the strip works — it is that pressing a scene submits
// NOTHING.
//
// WHAT A SOURCE TEST IS FOR HERE, AND WHAT IT IS NOT. This file was once the
// only test of the strip, and it passed while the feature was unusable: it
// asserted that the whole-draft guard existed, the guard did exist, and the
// guard was reading the wrong variable. Source text cannot tell working from
// spelled-right. tests/js/test_draft_pick.mjs now stands the panel up against
// a DOM stub and presses the button, and that is where the behaviour is
// proved.
//
// What is left here are the claims that ARE about source text: which value a
// guard reads, which module a symbol comes from, and whether this file ever
// assembles markup. Those cannot be observed by pressing anything, and they
// are the ones worth grepping for in a review.
//
// The SPLITTING itself is not asserted here. tests/js/test_fountain.mjs loads
// that module for real and drives it with actual Fountain.
//
// Run directly: `node tests/js/test_draft_strip.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) =>
  // Normalised at read: working copies are CRLF and CI is not, and a pattern
  // anchored to a newline passes on one checkout and fails on another.
  readFileSync(new URL(path, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");

const source = read("web/scriptcheck.js");
const bare = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* 1 — pressing a scene loads it. It does not check it. ------------------- */

const handler = bare.match(/btn\.addEventListener\("click", \(\) => \{([\s\S]*?)\n {4}\}\);/);
assert.ok(handler, "each scene button should carry a click handler");
const onPress = handler[1];

assert.match(onPress, /els\.input\.value = scene\.text/, "it loads the scene into the box");
assert.doesNotMatch(
  onPress,
  /runCheck|authedFetch|fetch\(/,
  "AND SUBMITS NOTHING. A fifty-scene draft beside a button that spends live " +
    "searches must not be able to spend fifty times on one press; the check " +
    "stays where it was, behind the control the writer already knows"
);

/* 1b — the refusal reads the BOX, not the remembered draft. -------------- */
//
// This assertion used to name `draftScenes` and it PASSED while the feature was
// unusable: the guard existed, it was reading the remembered draft rather than
// the textarea, and so it refused the very scene a reader had just loaded. A
// source test cannot tell a guard that works from a guard that is spelled
// right, which is why tests/js/test_draft_pick.mjs now stands the panel up and
// presses the button. What is left here is the one half that IS about source
// text: which value the guard reads.

const guard = bare.match(/const inBox = fountainScenes\(scene\);[\s\S]*?\n {2}\}/);
assert.ok(guard, "the guard should parse the scene currently in the box");
assert.doesNotMatch(
  guard[0],
  /draftScenes\.length/,
  "and never the remembered draft, which survives picking a scene out of it " +
    "and therefore says 'this is a whole draft' about a single loaded scene"
);
assert.match(guard[0], /Pick one from the list above/, "it points at the way out");
assert.doesNotMatch(
  guard[0],
  /not the script/,
  "and never repeats the server's line, which contradicts the strip that just " +
    "asked for the script"
);

/* 2 — the strip only exists when there is a draft. ----------------------- */

assert.match(
  bare,
  /if \(parsed\.length > 1\) \{\s*draftScenes = parsed;/,
  "more than one heading raises it. One scene pasted into a scene box is the " +
    "case this surface was built for and needs no strip telling it so"
);
assert.match(
  bare,
  /draftScenes\.some\(\(s\) => sceneKey\(s\.text\) === key\)/,
  "and a single scene in the box only CLEARS the list when it is not one of " +
    "the draft's own — picking a scene must not destroy the list it came from"
);

/* 3 — the check carries the key that makes the strip durable. ------------ */

assert.match(
  bare,
  /body: JSON\.stringify\(\{ scene, scene_key: sceneKey\(scene\) \}\)/,
  "the browser computes the key and sends it — star/store.py keeps it without " +
    "interpreting it, so there is exactly one implementation of what 'the " +
    "same scene' means"
);
assert.match(
  bare,
  /checkedKeys\.add\(sceneKey\(scene\)\)/,
  "and marks the scene it just ran, rather than waiting for the refetch to " +
    "tell the reader what they watched happen"
);
assert.match(
  bare,
  /checkedKeys = new Set\(\s*scenes\.map\(\(summary\) => String\(summary\?\.scene_key/,
  "with the durable half read off the filed list, which is what survives a " +
    "reload"
);

/* 4 — a scene heading is a writer's text and never becomes markup. ------- */

const strip = bare.slice(bare.indexOf("function renderDraft"));
assert.doesNotMatch(
  strip.slice(0, strip.indexOf("\n}\n")),
  /innerHTML|insertAdjacentHTML/,
  "THE RULE THIS WHOLE FILE KEEPS. A scene slug comes out of a pasted draft, " +
    "and this is the surface built around a hostile paste — the strip reaches " +
    "the DOM through createTextNode like everything else here"
);

/* 5 — the module the splitting lives in is imported, not reimplemented. -- */

assert.match(
  bare,
  /import \{ sceneKey, scenes as fountainScenes \} from "\/fountain\.js";/,
  "one splitter, with its own tests that never touch a DOM"
);
assert.doesNotMatch(
  bare,
  /INT\\?\.\|EXT|\/\^\(int/i,
  "and no second copy of the heading rules living in this file"
);

console.log("ok - a whole draft in the box costs no more than one scene did");
