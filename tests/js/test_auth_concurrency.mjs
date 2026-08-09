// Proves web/auth.js's concurrency guard without a browser and without a JS
// test framework.
//
// web/auth.js imports FIREBASE from "/config.js" — an absolute browser-root
// path that only resolves inside the app's own server. Node cannot import
// the file unmodified. This script patches that one line to an inline
// stand-in, writes the result to a temp file, and dynamically imports it
// with globalThis.fetch and globalThis.localStorage stubbed. Everything
// else in web/auth.js runs byte-identical to what ships.
//
// Run directly: `node tests/js/test_auth_concurrency.mjs` (exit 0 = pass).
// Wired into pytest via tests/test_js_auth.py so pytest stays the single
// entry point.

import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const SOURCE_PATH = new URL("web/auth.js", REPO_ROOT);

const IMPORT_LINE = 'import { FIREBASE } from "/config.js";';
const REPLACEMENT = 'const FIREBASE = { apiKey: "test-key", projectId: "test-project" };';

function loadPatchedModule() {
  const original = readFileSync(SOURCE_PATH, "utf8");

  // Assert the replacement actually matches, so a future edit to that line
  // fails this test loudly instead of silently testing stale code.
  const occurrences = original.split(IMPORT_LINE).length - 1;
  assert.equal(
    occurrences,
    1,
    `Expected exactly one occurrence of ${JSON.stringify(IMPORT_LINE)} in ` +
      `web/auth.js, found ${occurrences}. The source likely changed shape — ` +
      "update IMPORT_LINE in this test to match."
  );

  const patched = original.replace(IMPORT_LINE, REPLACEMENT);
  assert.notEqual(
    patched,
    original,
    "Replacement did not change the source text."
  );

  // A fresh file path gives a fresh ES module instance — each caller of
  // loadPatchedModule() gets its own idToken/expiresAt/pending state,
  // rather than sharing state across scenarios the way a single shared
  // import would.
  const dir = mkdtempSync(join(tmpdir(), "star-auth-test-"));
  const patchedPath = join(dir, `auth-${Math.random().toString(36).slice(2)}.mjs`);
  writeFileSync(patchedPath, patched, "utf8");
  return pathToFileURL(patchedPath).href;
}

function deferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function stubLocalStorage() {
  const store = new Map();
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
}

// -- Scenario 1: two concurrent callers before the first sign-up resolves --
// must produce exactly one accounts:signUp request, and both callers must
// receive the same token.
async function testConcurrentCallsShareOneSignUp() {
  globalThis.localStorage = stubLocalStorage();

  let signUpCalls = 0;
  const gate = deferred();
  globalThis.fetch = async (url) => {
    assert.match(String(url), /accounts:signUp/, "unexpected fetch in scenario 1");
    signUpCalls += 1;
    // Pause here until the test releases the gate — this is what makes the
    // race deterministic instead of timing-dependent: both getIdToken()
    // calls are issued while this request is still in flight.
    await gate.promise;
    return {
      ok: true,
      json: async () => ({
        idToken: "token-A",
        refreshToken: "refresh-A",
        expiresIn: "3600",
      }),
    };
  };

  const { getIdToken } = await import(loadPatchedModule());

  const p1 = getIdToken();
  const p2 = getIdToken();

  // No await has happened between the two calls above, so both have already
  // run synchronously up to the point where the stubbed fetch suspended on
  // the gate. The dedupe must already have happened.
  assert.equal(
    signUpCalls,
    1,
    "two concurrent getIdToken() calls before the first resolves must " +
      "produce exactly one accounts:signUp request"
  );

  gate.resolve();

  const [token1, token2] = await Promise.all([p1, p2]);
  assert.equal(token1, "token-A");
  assert.equal(token2, "token-A");
  assert.equal(
    token1,
    token2,
    "both concurrent callers must receive the same token"
  );
  assert.equal(
    signUpCalls,
    1,
    "no additional sign-up request should have been issued after settling"
  );
}

// -- Scenario 2: a caller arriving after a failed attempt gets a fresh -----
// attempt, not a poisoned pending promise.
async function testFailedAttemptDoesNotPoisonFuturePendingState() {
  globalThis.localStorage = stubLocalStorage();

  let signUpCalls = 0;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /accounts:signUp/, "unexpected fetch in scenario 2");
    signUpCalls += 1;
    if (signUpCalls === 1) {
      // Simulate a failed anonymous sign-up (Identity Toolkit returns a
      // non-2xx). signUpAnonymously() turns this into a thrown Error.
      return { ok: false, json: async () => ({ error: "boom" }) };
    }
    return {
      ok: true,
      json: async () => ({
        idToken: "token-C",
        refreshToken: "refresh-C",
        expiresIn: "3600",
      }),
    };
  };

  const { getIdToken } = await import(loadPatchedModule());

  const first = await getIdToken();
  assert.equal(first, null, "a failed sign-up must resolve to null, not throw");
  assert.equal(signUpCalls, 1);

  const second = await getIdToken();
  assert.equal(
    second,
    "token-C",
    "a caller arriving after a failed attempt must get a fresh attempt"
  );
  assert.equal(
    signUpCalls,
    2,
    "the pending promise from the failed attempt must not be reused for " +
      "the next caller"
  );
}

await testConcurrentCallsShareOneSignUp();
await testFailedAttemptDoesNotPoisonFuturePendingState();

console.log("tests/js/test_auth_concurrency.mjs: all assertions passed");
