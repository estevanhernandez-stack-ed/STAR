// Shared loaders and DOM stubs for the web/account.js and web/shell.js tests.
// Not a test itself — the pytest wrapper globs `test_*.mjs`, and this file is
// deliberately outside that, the same way _auth_module.mjs and
// _scriptcheck_module.mjs are.
//
// TWO MODULES, TWO SHAPES OF STUB, and the split is deliberate.
//
//   web/account.js   is a RENDERER plus a thin wiring tail. Its two imports
//                    are absolute browser-root paths, rewritten here to
//                    late-bound calls through globals the test owns, so
//                    nothing touches a real endpoint. The renderer is
//                    exercised against the same tiny document stub
//                    _scriptcheck_module.mjs already ships — reused rather
//                    than copied, because a second stub is a second thing that
//                    can quietly do more than a browser would.
//
//   web/shell.js     is the STAGE, and it manipulates classList and innerHTML,
//                    which the renderer stub deliberately does not implement.
//                    It gets its own slightly larger stub below, and the
//                    reason it is worth having is the acceptance criterion it
//                    proves: showAccount() only toggles panel visibility, so
//                    reaching the card mid-run cannot disturb a live stream.
//
// The account stub implements NO innerHTML and no HTML parser at all, which is
// the same property _scriptcheck_module.mjs's header argues for: there is no
// code path by which a string could become an element, so a test asserting "a
// token label rendered as text, not as an <img>" is paired with a source
// assertion that web/account.js contains no innerHTML anywhere.

import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
export const ACCOUNT_PATH = new URL("web/account.js", REPO_ROOT);
export const SHELL_PATH = new URL("web/shell.js", REPO_ROOT);
export const APP_PATH = new URL("web/app.js", REPO_ROOT);
export const INDEX_PATH = new URL("web/index.html", REPO_ROOT);

export { stubDocument, walk, elements, textNodes, withClass } from "./_scriptcheck_module.mjs";

const AUTH_IMPORT = /import\s*\{[\s\S]*?\}\s*from\s*"\/auth\.js";/;
const SHELL_IMPORT = /import\s*\{[\s\S]*?\}\s*from\s*"\/shell\.js";/;

/** Every name web/account.js pulls out of web/auth.js, bound late.
 *
 *  Late — through a getter on a global the test replaces per scenario —
 *  rather than captured at module evaluation, so one loaded module can be
 *  driven through several different auth answers. */
const AUTH_SHIM = [
  "const authedFetch = (...a) => globalThis.__starAuth.authedFetch(...a);",
  "const beginGoogleLink = (...a) => globalThis.__starAuth.beginGoogleLink(...a);",
  "const completeGoogleLink = (...a) => globalThis.__starAuth.completeGoogleLink(...a);",
  "const linkedProvider = (...a) => globalThis.__starAuth.linkedProvider(...a);",
  "const linkingAvailable = (...a) => globalThis.__starAuth.linkingAvailable(...a);",
  "const signOut = (...a) => globalThis.__starAuth.signOut(...a);",
  "const signOutNotice = (...a) => globalThis.__starAuth.signOutNotice(...a);",
].join("\n");

const SHELL_SHIM = "const refreshRail = (...a) => globalThis.__starShell.refreshRail(...a);";

function writeModule(prefix, source) {
  const dir = mkdtempSync(join(tmpdir(), `star-${prefix}-test-`));
  const path = join(dir, `${prefix}-${Math.random().toString(36).slice(2)}.mjs`);
  writeFileSync(path, source, "utf8");
  return pathToFileURL(path).href;
}

function replaceOnce(source, pattern, replacement, what) {
  const matches = source.match(new RegExp(pattern.source, "g")) || [];
  assert.equal(
    matches.length,
    1,
    `Expected exactly one ${what} in the source, found ${matches.length}. The ` +
      "file likely changed shape — update tests/js/_account_module.mjs to match."
  );
  const patched = source.replace(pattern, replacement);
  assert.notEqual(patched, source, `Replacing ${what} did not change the source text.`);
  return patched;
}

/** A fresh ES module instance of web/account.js with its two browser-root
 *  imports rewritten. Fresh per call, so a scenario cannot inherit another
 *  scenario's module state. */
export function loadAccountModule() {
  let source = readFileSync(ACCOUNT_PATH, "utf8");
  source = replaceOnce(source, AUTH_IMPORT, AUTH_SHIM, 'import from "/auth.js"');
  source = replaceOnce(source, SHELL_IMPORT, SHELL_SHIM, 'import from "/shell.js"');
  return writeModule("account", source);
}

/** A fresh ES module instance of web/shell.js with its one browser-root import
 *  rewritten. web/shell.js reaches the DOM at module evaluation (it takes six
 *  element references), so `globalThis.document` has to be installed before
 *  this URL is imported. */
export function loadShellModule() {
  const source = readFileSync(SHELL_PATH, "utf8");
  return writeModule(
    "shell",
    replaceOnce(
      source,
      AUTH_IMPORT,
      "const authedFetch = (...a) => globalThis.__starAuth.authedFetch(...a);",
      'import from "/auth.js"'
    )
  );
}

export function readAccountSource() {
  return readFileSync(ACCOUNT_PATH, "utf8");
}

export function readShellSource() {
  return readFileSync(SHELL_PATH, "utf8");
}

export function readAppSource() {
  return readFileSync(APP_PATH, "utf8");
}

export function readIndexHtml() {
  return readFileSync(INDEX_PATH, "utf8");
}

/* ---------------------------------------------------------------------
   The stage stub: enough of a document for web/shell.js, and no more.

   It implements classList (add / remove / toggle / contains), innerHTML,
   className, dataset, setAttribute / getAttribute, appendChild,
   addEventListener and childNodes. It parses nothing: setting innerHTML
   records the characters and produces no elements, which is why the rail
   assertions compare recorded strings rather than trees. It DOES clear the
   children on assignment, because a browser does — and because web/shell.js's
   renderRail opens with `railList.innerHTML = ""` and then appends, so a stub
   that only recorded the string would accumulate every rail it ever drew and
   quietly make a "the rail did not change" assertion unfalsifiable.
--------------------------------------------------------------------- */

class StubClassList {
  constructor() {
    this.set = new Set();
  }

  add(name) {
    this.set.add(name);
  }

  remove(name) {
    this.set.delete(name);
  }

  contains(name) {
    return this.set.has(name);
  }

  toggle(name, force) {
    if (force === undefined) {
      if (this.set.has(name)) this.set.delete(name);
      else this.set.add(name);
      return this.set.has(name);
    }
    if (force) this.set.add(name);
    else this.set.delete(name);
    return Boolean(force);
  }

  toString() {
    return [...this.set].join(" ");
  }
}

class StageElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.classList = new StubClassList();
    this.attributes = new Map();
    this.dataset = {};
    this.childNodes = [];
    this.listeners = new Map();
    this._innerHTML = "";
    this.className = "";
    this.type = "";
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(value) {
    this._innerHTML = String(value);
    this.childNodes = [];
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    const key = String(name);
    return this.attributes.has(key) ? this.attributes.get(key) : null;
  }

  appendChild(node) {
    this.childNodes.push(node);
    return node;
  }

  replaceChildren(...nodes) {
    this.childNodes = nodes;
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  dispatch(type, event = {}) {
    for (const handler of this.listeners.get(type) || []) handler(event);
  }

  /** Everything about this element a stage change could plausibly touch, as
   *  one comparable string. The rail assertions use it to prove that opening
   *  the card leaves the room list byte-identical. */
  snapshot() {
    return JSON.stringify({
      tag: this.tagName,
      classes: [...this.classList.set].sort(),
      className: this.className,
      attributes: [...this.attributes.entries()].sort(),
      dataset: { ...this.dataset },
      innerHTML: this.innerHTML,
      children: this.childNodes.map((child) =>
        typeof child.snapshot === "function" ? JSON.parse(child.snapshot()) : String(child)
      ),
    });
  }
}

/** A document holding exactly the six ids web/shell.js reads at load. */
export function stubStageDocument() {
  const byId = new Map();
  for (const id of [
    "rail-list",
    "rail-foot",
    "intake-panel",
    "progress-panel",
    "results-panel",
    "account-panel",
  ]) {
    const node = new StageElement(id.endsWith("list") ? "nav" : "section");
    node.setAttribute("id", id);
    byId.set(id, node);
  }
  return {
    byId,
    document: {
      getElementById: (id) => byId.get(id) || null,
      createElement: (tag) => new StageElement(tag),
    },
  };
}
