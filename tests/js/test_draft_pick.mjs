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
      // `toggle(c, force)` with an explicit second argument, which is what the
      // panel uses to show or hide the import in one line. Omitted from this
      // stub until the import needed it, and its absence surfaced as a
      // TypeError rather than as a wrong answer — which is the right way round.
      toggle: (c, force) => (force ? this.classes.add(c) : this.classes.delete(c)),
    };
  }
  appendChild(n) { this.childNodes.push(n); return n; }
  replaceChildren(...n) { this.childNodes = n; }
  setAttribute(k, v) { this.attributes[k] = v; }
  getAttribute(k) { return this.attributes[k]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  focus() { this.focused = true; }
  get textContent() {
    if (this.text !== undefined) return this.text;
    return this.data !== undefined
      ? this.data
      : this.childNodes.map((c) => c.textContent).join("");
  }
  // Settable, because the import re-labels its button between the two presses
  // and the label IS the arming — a control that looks identical either side
  // of a confirmation is one a reader presses twice by accident. A getter-only
  // stub made that a TypeError rather than a missed assertion.
  set textContent(value) {
    this.text = String(value);
    this.childNodes = [];
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
  // A programmatic .click() on a created <a> is how a fetched file is saved.
  // Recorded rather than ignored, because the filename it carries is the one
  // thing a reader finds in their downloads folder.
  click() {
    globalThis.__clickedLinks.push({
      href: this.attributes.href,
      download: this.attributes.download,
    });
  }
  type() {
    for (const fn of this.listeners.input || []) fn();
    for (const fn of this.listeners.change || []) fn();
  }
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
  "check-import", "check-import-input", "check-import-btn", "check-import-result",
]) ids[id] = new Node();

// The file input the import reads from. `files` and `.text()` are the whole of
// what web/scriptcheck.js touches on it.
ids["check-import-input"].files = [];
function chooseFile(text) {
  ids["check-import-input"].files = [{ text: async () => text }];
  ids["check-import-input"].type();
}

globalThis.document = {
  getElementById: (id) => ids[id] || null,
  createElement: (tag) => new Node(tag),
  createTextNode: (d) => new Text(d),
};
globalThis.window = {};
// What a download touches. `createObjectURL` and an <a>.click() are the only
// way to save a file that had to be FETCHED with credentials — see the note on
// downloadCsv in web/scriptcheck.js.
// Added AS STATICS on the real URL rather than replacing it: web/clip.js's
// httpUrl does `new URL(...)` to refuse a `javascript:` href, and swapping the
// constructor for a plain object broke that guard rather than the download.
const objectUrls = [];
URL.createObjectURL = (blob) => {
  objectUrls.push(blob);
  return `blob:stub/${objectUrls.length}`;
};
URL.revokeObjectURL = () => {};
const clicked = [];
globalThis.__clickedLinks = clicked;

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

/* 4d2 — the CSV download carries credentials. ---------------------------- */
//
// THE BUG THIS EXISTS FOR. It shipped as a plain <a href> to an /api route,
// which is a browser NAVIGATION: cookies, no Authorization header. The server
// correctly answered 401 and a reader who was signed in was told to sign in.
//
// The server test asserting that route 401s without a token PASSED the whole
// time — it was asserting the very thing going wrong. Nothing either side of
// the seam was broken; the seam was. So this drives the button and asks
// whether the request that actually goes out is an authed one.

const fetched = [];
globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  fetched.push({ url, method });
  if (url.endsWith(".csv")) {
    return {
      ok: true,
      status: 200,
      headers: {
        get: (name) =>
          name.toLowerCase() === "content-disposition"
            ? 'attachment; filename="doctor-who-sweep-2026-08-12.csv"'
            : null,
      },
      blob: async () => "scenes,claim\n1,a Gibson\n",
    };
  }
  if (method === "GET" && url.includes("/sweeps/")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({ sweep_id: "swcsv", scenes_read: 4, claims_raised: 5, claims: [] }),
    };
  }
  if (method === "GET" && url.includes("/sweeps")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        sweeps: [{ sweep_id: "swcsv", created_at: "2026-08-12T22:00:00Z", scenes_read: 4, claim_count: 5 }],
      }),
    };
  }
  return { ok: true, status: 200, json: async () => ({ scene_id: "s9", claims: [], scenes: [] }) };
};

mod.resetCheck();
mod.setCheckRoom("room-csv");
mod.openedCheck();
await new Promise((r) => setTimeout(r, 0));
await ids["check-swept-list"].childNodes[0].press();
await new Promise((r) => setTimeout(r, 0));

const exportRow = ids["check-sweep-result"];
const findCsv = (node) =>
  String(node.attributes?.class || "").includes("sweep-report-btn")
    ? node
    : (node.childNodes || []).map(findCsv).find(Boolean);
const csvButton = findCsv(exportRow);

assert.ok(csvButton, "a filed sweep offers a CSV control");
assert.equal(
  csvButton.nodeName,
  "BUTTON",
  "a BUTTON, not a link. An <a href> to /api sends no Authorization header, " +
    "so the server 401s and a signed-in reader is told to sign in"
);

clicked.length = 0;
await csvButton.press();
await new Promise((r) => setTimeout(r, 0));

const csvRequest = fetched.find((f) => f.url.endsWith(".csv"));
assert.ok(csvRequest, "pressing it goes through authedFetch, which is what carries the token");
assert.equal(clicked.length, 1, "and the fetched bytes are handed to the browser as a file");
assert.equal(
  clicked[0].download,
  "doctor-who-sweep-2026-08-12.csv",
  "under the name the SERVER chose — read back from the disposition rather " +
    "than rebuilt here, so there is one source for what lands in a downloads folder"
);

/* 4e — the import is armed by a file and confirmed by a second press. ---- */
//
// The import writes into a filed record, so the first press changes nothing.
// Driven here rather than asserted from source, because the defect this shape
// invites is state — a confirmation applying a file the reader has moved on
// from — and no assertion about spelling can see that.

const annotations = [];
globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  if (method === "POST" && url.includes("/annotations")) {
    const body = JSON.parse(options?.body || "{}");
    annotations.push(body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        applied: Boolean(body.apply),
        matched: 2,
        unmatched: ["A claim that was never here"],
        complaints: ["Row 4 carries verdict, which the department writes."],
        claims: [],
      }),
    };
  }
  if (method === "GET" && url.includes("/sweeps/sw9")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        sweep_id: "sw9",
        scenes_read: 4,
        claims_raised: 5,
        search_count: 1,
        claims: [{ text: "a Gibson", verdict: "confirmed", scenes: [1] }],
      }),
    };
  }
  if (method === "GET" && url.includes("/sweeps")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        sweeps: [{ sweep_id: "sw9", created_at: "2026-08-12T22:00:00Z", scenes_read: 4, claim_count: 5 }],
      }),
    };
  }
  return { ok: true, status: 200, json: async () => ({ scene_id: "s9", claims: [], scenes: [] }) };
};

mod.resetCheck();
mod.setCheckRoom("room-5");

assert.ok(
  ids["check-import"].classList.contains("hidden"),
  "hidden until a filed sweep is on screen — there is nothing to annotate before that"
);

mod.openedCheck();
await new Promise((r) => setTimeout(r, 0));
await ids["check-swept-list"].childNodes[0].press();
await new Promise((r) => setTimeout(r, 0));

assert.ok(
  !ids["check-import"].classList.contains("hidden"),
  "a filed sweep is open, so the import appears"
);
assert.equal(ids["check-import-btn"].disabled, true, "and the button is dead until a file is chosen");

chooseFile("claim,writer_note\na Gibson,Keep it\n");
assert.equal(ids["check-import-btn"].disabled, false, "a file arms the button");

await ids["check-import-btn"].press();
await new Promise((r) => setTimeout(r, 0));

assert.equal(annotations.length, 1, "the first press reads the file");
assert.equal(annotations[0].apply, false, "AND CHANGES NOTHING");
assert.match(ids["check-import-result"].textContent, /Nothing has been changed yet/);
assert.match(ids["check-import-btn"].textContent, /File these notes/, "the label is the arming");
assert.match(
  ids["check-import-result"].textContent,
  /A claim that was never here/,
  "a row matching nothing is NAMED — silence would let a writer annotate twenty " +
    "claims, import, find nineteen, and never learn which"
);
assert.match(
  ids["check-import-result"].textContent,
  /carries verdict, which the department writes/,
  "and the refusal names the column it kept for itself"
);

await ids["check-import-btn"].press();
await new Promise((r) => setTimeout(r, 0));

assert.equal(annotations.length, 2, "the second press files them");
assert.equal(annotations[1].apply, true);
assert.match(ids["check-import-result"].textContent, /2 notes filed/);
assert.match(ids["check-import-btn"].textContent, /Read the file/, "and disarms");

/* 4f — a different file cannot be applied by the arming of the first. ---- */
//
// THE SWAP HAS TO HAPPEN AFTER A PREVIEW, not after an apply. A successful
// apply clears the arming anyway, so testing the swap there proves nothing —
// an arming that merely asked "is anything armed?" instead of "is THIS the
// file I previewed?" passed that version of this test, and would silently
// write a file the reader never looked at.

chooseFile("claim,writer_note\na Gibson,First file\n");
await ids["check-import-btn"].press();
await new Promise((r) => setTimeout(r, 0));
assert.equal(annotations[annotations.length - 1].apply, false, "previewed, not applied");
assert.match(ids["check-import-btn"].textContent, /File these notes/, "and armed");

// Now swap the file while still armed, and confirm.
chooseFile("claim,writer_note\na Gibson,A DIFFERENT note\n");
await ids["check-import-btn"].press();
await new Promise((r) => setTimeout(r, 0));

const last = annotations[annotations.length - 1];
assert.equal(
  last.apply,
  false,
  "the second file is PREVIEWED rather than filed. An arming that survives a " +
    "file change would write something the reader never saw a preview of"
);
assert.match(last.csv, /A DIFFERENT note/, "and it is the new file being read");

/* 4g — a LIVE sweep offers no import, because there is nothing to write into. */
//
// A sweep that has just run carries its own sweep_id, so this needs the case
// where one does not — a payload with no id is a result the server could not
// file, and an import pointed at it would post to `/sweeps/null/annotations`.

globalThis.__fetch = async (url, options) => {
  const method = (options?.method || "GET").toUpperCase();
  if (method === "POST" && url.includes("/sweep")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({ scenes_read: 4, claims_raised: 2, claims: [], search_count: 0 }),
    };
  }
  return { ok: true, status: 200, json: async () => ({ sweeps: [], claims: [], scenes: [] }) };
};

mod.resetCheck();
mod.setCheckRoom("room-6");
ids.scene.value = DRAFT;
ids.scene.type();
await ids["check-sweep-btn"].press();
await new Promise((r) => setTimeout(r, 0));

assert.ok(
  ids["check-import"].classList.contains("hidden"),
  "no sweep_id came back, so there is nothing an import could write into"
);

/* 5 — pasting something unrelated drops the list. ------------------------ */

ids.scene.value = "INT. SOMEWHERE ELSE - DAY\n\nA different script entirely.";
ids.scene.type();

assert.ok(
  ids["check-draft"].classList.contains("hidden"),
  "a writer who has moved on should not be looking at a stale list of a " +
    "screenplay they are no longer in"
);

console.log("ok - picking a scene out of a draft lets you check that scene");
