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
  "check-sweep-btn", "check-sweep-note", "check-sweep-result",
  "check-swept-row", "check-swept-list",
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

/* 4b — a filed check is labelled by its scene, not by its date. ---------- */
//
// Every check filed in one sitting carries the same day, so a row reading
// "12 AUG 2026 · 3 claims" above "12 AUG 2026 · 5 claims" asks a writer to
// remember which was which. The scene is the one thing they know about it.

globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  if (method === "POST") posted.push({ url, body: JSON.parse(options?.body || "{}") });
  return {
    ok: true,
    status: 200,
    json: async () => ({
      scene_id: "s1",
      claims: [],
      search_count: 1,
      scenes: [
        {
          scene_id: "s1",
          created_at: "2026-08-12T10:00:00Z",
          claim_count: 5,
          scene_label: "INT. BUS (TOP DECK) — CONTINUOUS",
        },
        {
          scene_id: "s2",
          created_at: "2026-08-12T11:00:00Z",
          claim_count: 3,
          scene_label: "",
        },
      ],
    }),
  };
};

mod.resetCheck();
mod.setCheckRoom("room-2");
mod.openedCheck();
await new Promise((r) => setTimeout(r, 0));

const filed = ids["check-filed-list"].childNodes.map((n) => n.textContent);
assert.match(filed[0], /^INT\. BUS \(TOP DECK\)/, "the scene leads the label");
assert.match(filed[0], /5 claims/, "with what it found");
assert.match(filed[0], /AUG 2026/, "and the date after, which separates two checks of one scene");
assert.match(
  filed[1],
  /^\d/,
  "a check filed before scene_label existed falls back to the date rather " +
    "than rendering an empty button"
);

/* 4c — the sweep sends the whole draft and reports both numbers. --------- */
//
// The one control on this surface that spends without a scene being chosen.
// What matters is that it sends EVERY scene, that it says what it will cost
// before it is pressed, and that the answer carries the gap between what the
// draft raised and what was distinct — the number that is the case for the
// feature and the one a reader cannot work out alone.

const swept = [];
globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  if (method === "POST" && url.includes("/sweep")) {
    swept.push(JSON.parse(options?.body || "{}"));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        run_id: "room-3",
        scenes_read: 4,
        claims_raised: 7,
        search_count: 3,
        budget_exhausted: false,
        claims: [
          {
            text: "a Gibson",
            verdict: "confirmed",
            scenes: [1, 3],
            note: "In production.",
            citations: [
              {
                url: "https://gibson.example/history",
                title: "Gibson, a history",
                excerpt: "The model was in production from 1958.",
              },
            ],
          },
          { text: "a cassette deck", verdict: "anachronism", scenes: [4], note: "1963." },
        ],
      }),
    };
  }
  if (method === "POST") posted.push({ url, body: JSON.parse(options?.body || "{}") });
  return { ok: true, status: 200, json: async () => ({ scene_id: "s9", claims: [], scenes: [] }) };
};

mod.resetCheck();
mod.setCheckRoom("room-3");
ids.scene.value = DRAFT;
ids.scene.type();

assert.match(
  ids["check-sweep-note"].textContent,
  /4 scenes/,
  "the cost is on the page before the button is pressed, not after"
);
assert.match(ids["check-sweep-note"].textContent, /One search budget/);

await ids["check-sweep-btn"].press();
await new Promise((r) => setTimeout(r, 0));

assert.equal(swept.length, 1, "one request for the whole draft");
assert.equal(swept[0].scenes.length, 4, "carrying every scene");
assert.deepEqual(
  swept[0].scenes.map((s) => s.index),
  [1, 2, 3, 4],
  "with their indices, which is how a verdict finds its way back to a page"
);

const sweepText = ids["check-sweep-result"].textContent;
assert.match(sweepText, /7 claims raised/, "what the draft raised");
assert.match(sweepText, /2 distinct/, "and what was actually asked about");
assert.match(sweepText, /3 live searches/, "and what that cost");
assert.match(sweepText, /scene 1, 3/, "which pages a claim came from");
assert.match(sweepText, /anachronism/, "and the verdict that matters most");

// THE RECEIPTS. The first sweep of a real draft returned forty-five
// confirmations with nothing on screen behind any of them. star/verdicts.py
// guarantees a confirmed claim holds at least one hydrated citation, so the
// sources were always there — this surface just did not print them, which
// asked a reader to take the stamp on trust.
assert.match(sweepText, /Gibson, a history/, "the source's own title");
assert.match(sweepText, /gibson\.example/, "and where it came from");
assert.match(sweepText, /in production from 1958/, "and the page's own words");
assert.match(
  sweepText,
  /reading of the sources under it, not a check of the line against the world/,
  "with the scope a page of stamps cannot go without"
);
assert.ok(
  !ids["check-sweep-result"].classList.contains("hidden"),
  "the answer is showing"
);

/* 4d — a filed sweep is listed and reopens. ------------------------------ */
//
// A sweep costs a draft read and a search budget, and until it was filed the
// answer lived only in the tab that ran it. The row is what makes that real to
// a reader: it has to appear after a sweep runs, and pressing an entry has to
// bring the whole thing back — verdicts, sources and scene numbers.

globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  if (method === "GET" && url.includes("/sweeps/")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        sweep_id: "sw1",
        scenes_read: 24,
        claims_raised: 85,
        search_count: 4,
        claims: [
          {
            text: "turning it up to eleven",
            verdict: "anachronism",
            scenes: [19],
            note: "Coined in 1984.",
            citations: [
              { url: "https://tap.example/11", title: "Spinal Tap", excerpt: "1984." },
            ],
          },
        ],
      }),
    };
  }
  if (method === "GET" && url.includes("/sweeps")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        sweeps: [
          { sweep_id: "sw1", created_at: "2026-08-12T22:00:00Z", scenes_read: 24, claim_count: 67 },
        ],
      }),
    };
  }
  if (method === "POST") posted.push({ url, body: JSON.parse(options?.body || "{}") });
  return { ok: true, status: 200, json: async () => ({ scene_id: "s9", claims: [], scenes: [] }) };
};

mod.resetCheck();
mod.setCheckRoom("room-4");
mod.openedCheck();
await new Promise((r) => setTimeout(r, 0));

const sweptRow = ids["check-swept-list"].childNodes.map((n) => n.textContent);
assert.equal(sweptRow.length, 1, "the filed sweep is listed");
assert.match(sweptRow[0], /24 scenes/, "labelled by what it swept");
assert.match(sweptRow[0], /67 claims/, "and how much it found");
assert.match(sweptRow[0], /AUG 2026/, "with the date after — two sweeps of one draft " +
  "on one day are told apart by their counts, which a rewrite changes");
assert.ok(!ids["check-swept-row"].classList.contains("hidden"));

await ids["check-swept-list"].childNodes[0].press();
await new Promise((r) => setTimeout(r, 0));

const reopened = ids["check-sweep-result"].textContent;
assert.match(reopened, /turning it up to eleven/, "the claim comes back");
assert.match(reopened, /anachronism/, "with its verdict");
assert.match(reopened, /Spinal Tap/, "AND its sources — a reopened page of stamps with " +
  "nothing under them is the defect this surface already shipped once");
assert.match(reopened, /scene 19/, "and which page it belongs to");

/* 5 — pasting something unrelated drops the list. ------------------------ */

ids.scene.value = "INT. SOMEWHERE ELSE - DAY\n\nA different script entirely.";
ids.scene.type();

assert.ok(
  ids["check-draft"].classList.contains("hidden"),
  "a writer who has moved on should not be looking at a stale list of a " +
    "screenplay they are no longer in"
);

console.log("ok - picking a scene out of a draft lets you check that scene");
