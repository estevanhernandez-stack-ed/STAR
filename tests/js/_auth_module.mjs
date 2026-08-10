// Shared loader for the web/auth.js tests. Not a test itself — the pytest
// wrapper globs `test_*.mjs`, and this file is deliberately outside that.
//
// web/auth.js imports FIREBASE from "/config.js", an absolute browser-root
// path that only resolves inside the app's own server, so Node cannot import
// the file unmodified. This patches that one line to an inline stand-in,
// writes the result to a temp file, and hands back a URL to import. Everything
// else in web/auth.js runs byte-identical to what ships.

import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const SOURCE_PATH = new URL("web/auth.js", REPO_ROOT);

const IMPORT_LINE = 'import { FIREBASE } from "/config.js";';
const REPLACEMENT = 'const FIREBASE = { apiKey: "test-key", projectId: "test-project" };';

/** A fresh ES module instance of web/auth.js, with its one browser-root import
 *  patched out. A fresh file path per call gives each scenario its own
 *  idToken/expiresAt/pending state rather than sharing it across scenarios the
 *  way a single shared import would. */
export function loadPatchedModule() {
  const original = readFileSync(SOURCE_PATH, "utf8");

  // Assert the replacement actually matches, so a future edit to that line
  // fails these tests loudly instead of silently testing stale code.
  const occurrences = original.split(IMPORT_LINE).length - 1;
  assert.equal(
    occurrences,
    1,
    `Expected exactly one occurrence of ${JSON.stringify(IMPORT_LINE)} in ` +
      `web/auth.js, found ${occurrences}. The source likely changed shape — ` +
      "update IMPORT_LINE in tests/js/_auth_module.mjs to match."
  );

  const patched = original.replace(IMPORT_LINE, REPLACEMENT);
  assert.notEqual(patched, original, "Replacement did not change the source text.");

  const dir = mkdtempSync(join(tmpdir(), "star-auth-test-"));
  const patchedPath = join(dir, `auth-${Math.random().toString(36).slice(2)}.mjs`);
  writeFileSync(patchedPath, patched, "utf8");
  return pathToFileURL(patchedPath).href;
}

export function stubLocalStorage() {
  const store = new Map();
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}
