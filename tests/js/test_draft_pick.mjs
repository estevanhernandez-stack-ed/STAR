// Picking a scene out of a draft lets you check that scene.
//
// THE BUG THIS EXISTS FOR, and the reason it is not a source test. Pressing a
// scene sets the textarea's value from code, and a programmatic `.value =`
// fires no `input` event — so the module's remembered `draftScenes` still held
// all 24. The guard that refuses a whole draft read that variable instead of
// the box, so it refused the very scene the reader had just loaded and told
// them to pick one from a list they had already picked from. There was no way
// forward at all.
//
// tests/js/test_draft_strip.mjs asserted the guard EXISTED. It did exist. It
// was reading the wrong thing, and no assertion about source text can tell the
// difference — the shape of the bug is state, not spelling. So this file
// stands the panel up against a DOM stub, presses the button, and asks what
// actually happened.
//
// Run directly: `node tests/js/test_draft_pick.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, REPO_ROOT), "utf8").replace(/\r\n/g, "\n");
const real = (p) => pathToFileURL(fileURLToPath(new URL(p, REPO_ROOT))).href;

const DRAFT = `Title: Test

INT. CASBAH CELLAR — NIGHT

The band plays. A Gibson through a damp PA.

EXT. LIVERPOOL — NIGHT

Rain. A double-decker grinds past.

INT. BUS (TOP DECK) — CONTINUOUS

Three boys and a chord shape.

INT. TARDIS — CONTINUOUS

The console room hums.`;

/* A DOM stub with the four things the panel actually needs: ids, children,
   classes and listeners. Deliberately no layout, no selectors beyond the one
   the strip uses, and no innerHTML — the panel never sets it. */
class Node {
  constructor(tag = "div") {
    this.nodeName = tag.toUpperCase();
    this.childNodes = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.value = "";
    this.disabled = false;
    this.classes = new Set();
    this.classList = {
      add: (c) => this.classes.add(c),
      remove: (c) => this.classes.delete(c),
      contains: (c) => this.classes.has(c),
    };
  }
  appendChild(n) { this.childNodes.push(n); return n; }
  replaceChildren(...n) { this.childNodes = n; }
  setAttribute(k, v) { this.attributes[k] = v; }
  getAttribute(k) { return this.attributes[k]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  focus() { this.focused = true; }
  get textContent() {
    return this.data !== undefined
      ? this.data
      : this.childNodes.map((c) => c.textContent).join("");
  }
  querySelector(sel) {
    const want = sel.replace(".", "");
    const hit = (n) =>
      String(n.attributes?.class || "").split(/\s+/).includes(want)
        ? n
        : (n.childNodes || []).map(hit).find(Boolean);
    return hit(this) || null;
  }
  // Returns the handlers' promise. `runCheck` is async, and a press that
  // discarded it would let every assertion below run before the fetch it is
  // asking about — a test that passes because it looked too early.
  press() { return Promise.all((this.listeners.click || []).map((fn) => fn())); }
  type() { for (const fn of this.listeners.input || []) fn(); }
}
class Text extends Node {
  constructor(data) { super("#text"); this.data = String(data); }
}

const ids = {};
for (const id of [
  "check-panel", "scene", "check-run-btn", "check-status", "check-error",
  "check-result", "check-filed-row", "check-filed-list",
  "check-draft", "check-draft-count", "check-draft-done", "check-draft-scenes",
]) ids[id] = new Node();

globalThis.document = {
  getElementById: (id) => ids[id] || null,
  createElement: (tag) => new Node(tag),
  createTextNode: (d) => new Text(d),
};
globalThis.window = {};

// Only POSTs are spends. A finished check re-reads the filed list with a GET
// through this same stub, and counting both made "one check was sent" read as
// two — a harness bug that looks exactly like a double-submit defect.
const posted = [];
globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  if (method === "POST") posted.push({ url, body: JSON.parse(options?.body || "{}") });
  return {
    ok: true,
    status: 200,
    json: async () => ({ scene_id: "s1", claims: [], search_count: 1, scenes: [] }),
  };
};

const patched = read("web/scriptcheck.js")
  .replace('import { anchor } from "/anchor.js";', `import { anchor } from ${JSON.stringify(real("web/anchor.js"))};`)
  .replace('import { excerptProse } from "/excerpt.js";', `import { excerptProse } from ${JSON.stringify(real("web/excerpt.js"))};`)
  .replace(
    'import { sceneKey, scenes as fountainScenes } from "/fountain.js";',
    `import { sceneKey, scenes as fountainScenes } from ${JSON.stringify(real("web/fountain.js"))};`
  )
  .replace(
    'import { authedFetch } from "/auth.js";',
    "const authedFetch = (...a) => globalThis.__fetch(...a);"
  );
assert.doesNotMatch(patched, /from "\/[a-z]+\.js"/, "every browser-root import should be rewritten");

const mod = await import(
  `data:text/javascript;base64,${Buffer.from(patched, "utf8").toString("base64")}`
);

mod.initScriptCheck();
mod.setCheckRoom("room-1");

/* 1 — a pasted draft raises the strip. ----------------------------------- */

ids.scene.value = DRAFT;
ids.scene.type();

const buttons = ids["check-draft-scenes"].childNodes;
assert.equal(buttons.length, 4, "four scenes, four buttons");
assert.ok(!ids["check-draft"].classList.contains("hidden"), "the strip is showing");
assert.match(ids["check-draft-count"].textContent, /4 scenes/);

/* 2 — pressing one loads it and submits nothing. ------------------------- */

buttons[2].press();

assert.match(ids.scene.value, /^INT\. BUS \(TOP DECK\)/, "that scene is in the box");
assert.doesNotMatch(ids.scene.value, /CASBAH/, "and only that scene");
assert.equal(posted.length, 0, "pressing a scene spends nothing");
assert.ok(!ids["check-draft"].classList.contains("hidden"), "the list survives the pick");
assert.equal(
  ids["check-draft-scenes"].childNodes.length,
  4,
  "all four still listed — a writer working through a draft keeps the draft"
);

/* 3 — AND THEN THE CHECK RUNS. ------------------------------------------ */

await ids["check-run-btn"].press();
await new Promise((r) => setTimeout(r, 0));

assert.equal(
  ids["check-error"].textContent,
  "",
  "THE BUG. The guard read the remembered draft rather than the box, so it " +
    "refused the scene it had just loaded and pointed at the list it came from"
);
assert.equal(posted.length, 1, "the check is sent");
assert.match(posted[0].body.scene, /^INT\. BUS \(TOP DECK\)/, "with that scene");
assert.match(posted[0].body.scene_key, /^[0-9a-f]{8}$/, "and its key");

/* 4 — the whole draft still refuses, and says where to go. --------------- */

ids.scene.value = DRAFT;
ids.scene.type();
await ids["check-run-btn"].press();
await new Promise((r) => setTimeout(r, 0));

assert.equal(posted.length, 1, "nothing further was spent");
assert.match(ids["check-error"].textContent, /whole draft — 4 scenes/);
assert.match(ids["check-error"].textContent, /Pick one from the list above/);

/* 5 — pasting something unrelated drops the list. ------------------------ */

ids.scene.value = "INT. SOMEWHERE ELSE - DAY\n\nA different script entirely.";
ids.scene.type();

assert.ok(
  ids["check-draft"].classList.contains("hidden"),
  "a writer who has moved on should not be looking at a stale list of a " +
    "screenplay they are no longer in"
);

console.log("ok - picking a scene out of a draft lets you check that scene");
