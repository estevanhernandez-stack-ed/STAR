// Proves the two properties the whole cycle's narrowing rests on, and the one
// stage-state property the card's acceptance criteria turn on.
//
//   1. THE INTAKE PATH IS SILENT. A writer who will never sign in to anything
//      walks from landing to a filed room without meeting the word "account"
//      once, and without meeting "Google" anywhere except the build credit in
//      the footer, which is a statement about the stack rather than an offer.
//      docs/design/DIRECTION.md:54 records that this project's silence is the
//      rebuttal to the adversarial critic's sign-in-wall objection, so the
//      grep is not hygiene, it is the argument.
//
//   2. THE RETENTION COPY MATCHES POST-LINK TRUTH. prd.md names two clauses in
//      the shipped intake copy that go false the moment an account is
//      attached. One was rewritten, one was CUT rather than softened, and this
//      file pins both so neither comes back by a later edit.
//
//   3. showAccount() ONLY TOGGLES PANEL VISIBILITY. That is what makes
//      "reaching the card mid-run does not disturb the stream" true: the
//      EventSource lives in web/app.js and nothing on the path from the rail's
//      entry to the card's first paint goes near it. Proved two ways — the
//      rail is byte-identical across the switch, and the source of all three
//      files on that path is asserted to contain no stream verb at all.
//
// Run directly: `node tests/js/test_intake_silence.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

import {
  loadShellModule,
  readAccountSource,
  readAppSource,
  readIndexHtml,
  readShellSource,
  stubStageDocument,
} from "./_account_module.mjs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8");

/* The one place "Google" is allowed to appear where a reader can see it, on
   any surface reachable without opening the card. It names the stack, it
   offers nothing, and it is the same credit line the submission rests on. */
const BUILD_CREDIT = "Built with Google ADK + Gemini on Google Cloud";

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

/** HTML comments out, tags out, entities that matter decoded — what is left is
 *  what a reader can read. Attribute values that ARE reader-visible
 *  (placeholder, aria-label, title, alt) are folded back in, because a
 *  placeholder is copy even though it lives inside a tag. */
function visibleText(html) {
  const source = html.replace(/<!--[\s\S]*?-->/g, "");
  const spoken = [];
  for (const attr of ["placeholder", "aria-label", "title", "alt"]) {
    for (const match of source.matchAll(new RegExp(`${attr}="([^"]*)"`, "g"))) {
      spoken.push(match[1]);
    }
  }
  const body = source.replace(/<[^>]*>/g, " ");
  return [body, ...spoken]
    .join(" ")
    .replaceAll("&amp;", "&")
    .replaceAll("&middot;", "·")
    .replace(/\s+/g, " ")
    .trim();
}

/** Every quoted string literal in a JS source, comments removed first.
 *
 *  Scoped to LITERALS on purpose. web/app.js imports `completeGoogleLink` and
 *  the identifier contains the word; an assertion over the whole source would
 *  fail on a symbol nobody can read, and softening it to pass would stop it
 *  catching the thing it is for — a sentence. */
function stringLiterals(source) {
  const clean = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  const out = [];
  for (const match of clean.matchAll(/"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g)) {
    out.push(match[1] ?? match[2] ?? match[3] ?? "");
  }
  return out;
}

/* A literal with no whitespace in it is a path, an element id, a class name or
   a single key — never a sentence. Those are split out rather than waved past,
   and the two that legitimately carry the word are named here so a third one
   appearing fails loudly instead of being absorbed by a looser rule. */
const NON_COPY_TOKENS = new Set(["/account.js", "account-panel"]);
const isToken = (literal) => !/\s/.test(literal);

/* ------------------------------------------------------------------ */
/* 1. The intake path is silent.                                       */
/* ------------------------------------------------------------------ */

test("no reader-visible text in index.html says the word account", () => {
  const visible = visibleText(readIndexHtml());
  assert.ok(
    !/account/i.test(visible),
    `"account" reached the document a reader can read: ` +
      visible.slice(Math.max(0, visible.search(/account/i) - 80), visible.search(/account/i) + 80)
  );
});

test("the only reader-visible Google in index.html is the build credit", () => {
  const visible = visibleText(readIndexHtml());
  assert.ok(visible.includes(BUILD_CREDIT), "the build credit is still in the footer");
  const withoutCredit = visible.replace(BUILD_CREDIT, "");
  assert.ok(
    !/google/i.test(withoutCredit),
    `a second "Google" reached the intake path: ` +
      withoutCredit.slice(
        Math.max(0, withoutCredit.search(/google/i) - 80),
        withoutCredit.search(/google/i) + 80
      )
  );
});

test("#account-panel ships empty, so none of the card's copy is in the document", () => {
  const html = readIndexHtml();
  assert.ok(
    /<section id="account-panel"[^>]*>\s*<\/section>/.test(html),
    "the fourth panel must be an empty container, not hidden markup"
  );
  // The card's own sentences live in web/account.js and reach the DOM only
  // when the rail's entry is used. If any of them were ever inlined into the
  // page, the two assertions above would fail — this one names why.
  for (const phrase of ["Attach a Google account", "Issue a token", "Not attached"]) {
    assert.ok(!html.includes(phrase), `${phrase} must not ship in index.html`);
  }
});

test("the rail's entry to the card says neither Google nor account", () => {
  const html = readIndexHtml();
  const entry = html.match(/<button id="rail-foot"[\s\S]*?<\/button>/);
  assert.ok(entry, "the rail carries an entry to the card");
  assert.ok(entry[0].includes("Your card"), "and it reads Your card");
  assert.ok(!/google/i.test(entry[0]));
  // The id is the only "account"-free requirement this one does not carry, and
  // it does not need to: `rail-foot` is the id, "Your card" is the copy.
  assert.ok(!/account/i.test(entry[0]));
});

test("no module that paints the intake path carries such a sentence", () => {
  // Every browser module reachable from landing to a filed room. web/auth.js
  // and web/account.js are deliberately absent: auth.js paints nothing, and
  // account.js is the card, which is the one surface allowed to say both.
  const modules = [
    "web/app.js",
    "web/shell.js",
    "web/drawer.js",
    "web/clip.js",
    "web/scriptcheck.js",
    "web/anchor.js",
  ];
  for (const path of modules) {
    for (const literal of stringLiterals(read(path))) {
      if (!/account|google/i.test(literal)) continue;
      if (isToken(literal)) {
        assert.ok(
          NON_COPY_TOKENS.has(literal),
          `${path} carries an unexpected identifier: ${literal}`
        );
        continue;
      }
      assert.fail(`${path} has a sentence saying it: ${literal.slice(0, 140)}`);
    }
  }
});

/* ------------------------------------------------------------------ */
/* 2. The retention copy, re-verified against post-link truth.         */
/* ------------------------------------------------------------------ */

function retentionCopy() {
  const html = readIndexHtml().replace(/<!--[\s\S]*?-->/g, "");
  const match = html.match(/<p class="retention">([\s\S]*?)<\/p>/);
  assert.ok(match, "the intake still carries a retention notice");
  return match[1].replace(/\s+/g, " ").trim();
}

test("the clause that goes false on link is gone, and its replacement is true either way", () => {
  const copy = retentionCopy();
  assert.ok(
    !copy.includes("kept under this browser's identity"),
    "a linked account is reachable from any browser, so this clause cannot stand"
  );
  assert.ok(
    copy.includes("filed under the identity you are signed in with"),
    "the replacement is true before AND after a link"
  );
});

test("the visibility clause is cut, not softened", () => {
  const copy = retentionCopy();
  assert.ok(
    !/nothing is visible without/i.test(copy),
    "the sentence whose plain reading goes false on link must be gone"
  );
  // Softened variants are the failure this rule exists to prevent, so the
  // shapes a rewrite would reach for are named rather than left to judgement.
  for (const softened of ["only you", "only your browser", "nobody else", "private"]) {
    assert.ok(
      !copy.toLowerCase().includes(softened),
      `the visibility claim came back softened as "${softened}"`
    );
  }
});

test("the two clauses that survive are the two star/store.py can back", () => {
  const copy = retentionCopy();
  assert.ok(copy.includes("Your treatment itself is not stored"));
  assert.ok(
    copy.includes("only the profile the department extracts from it, and the research it produces")
  );
  // room_to_document writes run_id, status, created_at, title, era, genre,
  // story_profile, research_plan, research_bible, search_count, source_count
  // and categories. No treatment field, and StoryProfile carries six extracted
  // fields, none of them the text.
  const store = read("star/store.py");
  const shaped = store.slice(store.indexOf("def room_to_document"), store.indexOf("def document_to_room"));
  assert.ok(!/"treatment"/.test(shaped), "a treatment key would make clause one false");
});

test("the full truth the intake cut is stated on the card, before the link", () => {
  const account = readAccountSource();
  assert.ok(
    account.includes("readable from any browser you sign in to"),
    "the card names any browser"
  );
  assert.ok(
    account.includes("any agent holding a token you issue"),
    "and any agent holding a token"
  );
});

/* ------------------------------------------------------------------ */
/* 3. showAccount() only toggles panel visibility.                     */
/* ------------------------------------------------------------------ */

const stage = stubStageDocument();
globalThis.document = stage.document;
let authedFetchCalls = 0;
globalThis.__starAuth = {
  authedFetch: async () => {
    authedFetchCalls += 1;
    return { ok: true, json: async () => ({ rooms: [] }) };
  },
};

const shell = await import(loadShellModule());

const ROOMS = [
  { run_id: "run-1", title: "The Whiskey Six", era: "1929", created_at: "2026-08-09T12:00:00+00:00", status: "complete" },
  { run_id: "run-2", title: "Studio B", era: "1962", created_at: "2026-08-10T12:00:00+00:00", status: "running" },
];

const panel = (id) => stage.byId.get(id);
const hidden = (id) => panel(id).classList.contains("hidden");

test("the card is a fourth stage state, and exactly one panel is ever visible", () => {
  shell.showIntake();
  assert.deepEqual(
    [hidden("intake-panel"), hidden("progress-panel"), hidden("results-panel"), hidden("account-panel")],
    [false, true, true, true]
  );

  shell.showRunning();
  assert.deepEqual(
    [hidden("intake-panel"), hidden("progress-panel"), hidden("results-panel"), hidden("account-panel")],
    [true, false, true, true]
  );

  shell.showRoom();
  assert.deepEqual(
    [hidden("intake-panel"), hidden("progress-panel"), hidden("results-panel"), hidden("account-panel")],
    [true, true, false, true]
  );

  shell.showAccount();
  assert.deepEqual(
    [hidden("intake-panel"), hidden("progress-panel"), hidden("results-panel"), hidden("account-panel")],
    [true, true, true, false]
  );
});

test("the rail's entry carries the selection, and gives it back", () => {
  shell.showAccount();
  assert.equal(panel("rail-foot").getAttribute("aria-current"), "true");
  assert.ok(panel("rail-foot").classList.contains("active"));
  shell.showRoom();
  assert.equal(panel("rail-foot").getAttribute("aria-current"), "false");
  assert.ok(!panel("rail-foot").classList.contains("active"));
});

test("the rail is byte-identical immediately before and after the card opens", () => {
  shell.renderRail(ROOMS, "run-1");
  shell.showRoom();
  const before = panel("rail-list").snapshot();

  shell.showAccount();
  const during = panel("rail-list").snapshot();
  shell.showRoom();
  const after = panel("rail-list").snapshot();

  assert.equal(during, before, "opening the card must not redraw the rail");
  assert.equal(after, before, "and neither must leaving it");
  assert.ok(before.includes("The Whiskey Six"), "the snapshot is of a real rail");
});

test("showAccount() goes nowhere near the network", () => {
  shell.renderRail(ROOMS, "run-1");
  const before = authedFetchCalls;
  shell.showAccount();
  shell.showRoom();
  shell.showAccount();
  assert.equal(authedFetchCalls, before, "no request is issued by a stage change");
});

test("showAccount() leaves the active room active, where showIntake() clears it", () => {
  shell.renderRail(ROOMS, "run-2");
  shell.showRoom();
  const active = () => panel("rail-list").snapshot().includes('["aria-current","true"]');
  assert.ok(active(), "a room is marked active");

  shell.showAccount();
  assert.ok(active(), "the card leaves it alone — the reader never left the room");

  shell.showIntake();
  assert.ok(!active(), "the intake is the one that clears it, and still does");
});

test("web/shell.js's showAccount does nothing but switch the panel", () => {
  const body = readShellSource().match(/export function showAccount\(\) \{([\s\S]*?)\n\}/);
  assert.ok(body, "showAccount is declared");
  const statements = body[1]
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !line.startsWith("//"));
  assert.deepEqual(statements, ["stage(accountPanel);"]);
});

test("nothing on the path from the rail to the card touches a stream", () => {
  const listener = readAppSource().match(
    /\$\("rail-foot"\)\.addEventListener\("click", \(\) => \{([\s\S]*?)\n\}\);/
  );
  assert.ok(listener, "web/app.js binds the rail's entry");
  const statements = listener[1]
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !line.startsWith("//"));
  assert.deepEqual(
    statements,
    ["showAccount();", "openAccount();"],
    "the listener reveals a panel and fills it, and does nothing else"
  );

  const account = readAccountSource()
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  for (const verb of ["EventSource", "openStream", "closeStream", "resetProgress", "showResults"]) {
    assert.ok(!account.includes(verb), `web/account.js must not reference ${verb}`);
  }
});

/* ------------------------------------------------------------------ */

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`FAIL  ${name}\n      ${err.message}`);
  }
}
console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed === 0 ? 0 : 1);
