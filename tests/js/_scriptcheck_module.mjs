// Shared loader and DOM stub for the web/scriptcheck.js tests. Not a test
// itself — the pytest wrapper globs `test_*.mjs`, and this file is deliberately
// outside that, the same way _auth_module.mjs is.
//
// web/scriptcheck.js has exactly two imports and both are absolute browser-root
// paths that only resolve inside the app's own server:
//
//   /anchor.js   the matcher. Rewritten to a file:// URL of the REAL
//                web/anchor.js, so these tests exercise the matcher that ships
//                rather than a stand-in. That matters here: the security
//                property being tested is that a pasted payload survives the
//                matcher as characters and reaches the DOM as a text node, and
//                a fake matcher would prove nothing about the first half.
//   /auth.js     the authed fetch. Rewritten to a call through a global the
//                test owns, so the network is deterministic and nothing here
//                touches a real endpoint.
//
// Everything else in web/scriptcheck.js runs byte-identical to what ships.
//
// WHAT THE DOM STUB IS, stated plainly because a stub that quietly does more
// than the browser would make these tests worthless. It implements exactly the
// eleven things the renderer uses — createElement, createTextNode, setAttribute,
// getAttribute, appendChild, replaceChildren, addEventListener, childNodes,
// children, textContent, and a `disabled` property — and nothing else. In
// particular it implements NO innerHTML and NO HTML parser at all: there is no
// code path in this stub by which a string could become an element. That is not
// a limitation being worked around, it is the point. A test asserting "the
// payload rendered as text, not as an <img>" against a stub that cannot parse
// HTML would be circular on its own, so the test file pairs it with a source
// assertion that web/scriptcheck.js contains no innerHTML at all — the stub
// proves the tree's shape, the grep proves the tree is the only way in.

import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
export const SOURCE_PATH = new URL("web/scriptcheck.js", REPO_ROOT);
const ANCHOR_PATH = new URL("web/anchor.js", REPO_ROOT);

const IMPORT_ANCHOR = 'import { anchor } from "/anchor.js";';
const IMPORT_AUTH = 'import { authedFetch } from "/auth.js";';

/** A fresh ES module instance of web/scriptcheck.js with its two browser-root
 *  imports rewritten. Fresh per call, so a scenario cannot inherit another
 *  scenario's module state. */
export function loadPatchedModule() {
  const original = readFileSync(SOURCE_PATH, "utf8");

  for (const line of [IMPORT_ANCHOR, IMPORT_AUTH]) {
    const occurrences = original.split(line).length - 1;
    assert.equal(
      occurrences,
      1,
      `Expected exactly one occurrence of ${JSON.stringify(line)} in ` +
        `web/scriptcheck.js, found ${occurrences}. The source likely changed ` +
        "shape — update tests/js/_scriptcheck_module.mjs to match."
    );
  }

  const patched = original
    .replace(IMPORT_ANCHOR, `import { anchor } from ${JSON.stringify(ANCHOR_PATH.href)};`)
    .replace(
      IMPORT_AUTH,
      "const authedFetch = (...args) => globalThis.__starAuthedFetch(...args);"
    );
  assert.notEqual(patched, original, "Replacement did not change the source text.");

  const dir = mkdtempSync(join(tmpdir(), "star-scriptcheck-test-"));
  const path = join(dir, `scriptcheck-${Math.random().toString(36).slice(2)}.mjs`);
  writeFileSync(path, patched, "utf8");
  return pathToFileURL(path).href;
}

export function readSource() {
  return readFileSync(SOURCE_PATH, "utf8");
}

class TextNode {
  constructor(data) {
    this.nodeType = 3;
    this.nodeName = "#text";
    this.data = String(data);
  }

  get textContent() {
    return this.data;
  }
}

class StubElement {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.nodeName = this.tagName;
    this.attributes = new Map();
    this.childNodes = [];
    this.listeners = new Map();
    this.disabled = false;
  }

  get children() {
    return this.childNodes.filter((node) => node.nodeType === 1);
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

  /** Fire every handler registered for one event type. The renderer wires
   *  click and keydown by hand (a <mark> with role="button" gets neither
   *  natively), so this is how a test presses one. */
  dispatch(type, event = {}) {
    for (const handler of this.listeners.get(type) || []) handler(event);
  }

  get textContent() {
    return this.childNodes.map((node) => node.textContent).join("");
  }
}

/** The document the renderer runs against. Deliberately tiny — see the header
 *  for the full list of what it does and does not do. */
export function stubDocument() {
  return {
    createElement: (tag) => new StubElement(tag),
    createTextNode: (data) => new TextNode(data),
  };
}

/** Every node in a subtree, the root included, in document order. */
export function walk(node, out = []) {
  out.push(node);
  for (const child of node.childNodes || []) walk(child, out);
  return out;
}

export function elements(node, tagName) {
  const want = tagName.toUpperCase();
  return walk(node).filter((n) => n.nodeType === 1 && n.nodeName === want);
}

export function textNodes(node) {
  return walk(node).filter((n) => n.nodeType === 3);
}

export function withClass(node, className) {
  return walk(node).filter(
    (n) => n.nodeType === 1 && String(n.getAttribute("class") || "").split(/\s+/).includes(className)
  );
}
