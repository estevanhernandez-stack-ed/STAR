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
// WHY THIS IS A SOURCE TEST. web/scriptcheck.js takes its element references
// through `document.getElementById` at init, and the shared stub in
// _scriptcheck_module.mjs deliberately provides only createElement and
// createTextNode — it exists to exercise the renderer, which is pure. Driving
// the panel would mean a second, larger DOM in this repo, and the properties
// below are about which calls the source makes rather than about what a
// rendered node looks like. Same reasoning tests/js/test_error_spend.mjs
// records for the same kind of claim.
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

/* 1b — the refusal does not scold a reader for taking the invitation. ---- */
//
// The server answers an oversize paste with "send the department a scene, not
// the script" — correct until this surface started asking for the script. With
// the strip above it, pressing the button on a whole draft got the app arguing
// with its own instruction in front of somebody who followed it.

const guard = bare.match(/if \(draftScenes\.length > 1\) \{([\s\S]*?)\n {2}\}/);
assert.ok(guard, "the browser should catch a whole draft before the request");
assert.match(guard[1], /Pick one from the list above/, "it points at the way out");
assert.doesNotMatch(
  guard[1],
  /not the script/,
  "and never repeats the server's line, which contradicts the strip that just " +
    "asked for the script"
);
assert.match(
  guard[1],
  /return;/,
  "and it returns rather than spending — a refusal that still POSTs is a " +
    "refusal that costs the reader a check"
);

/* 2 — the strip only exists when there is a draft. ----------------------- */

assert.match(
  bare,
  /draftScenes = parsed\.length > 1 \? parsed : \[\]/,
  "more than one heading, or nothing. One scene pasted into a scene box is " +
    "the case this surface was built for and needs no strip telling it so"
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
