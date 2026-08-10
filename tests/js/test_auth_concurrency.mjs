// Proves web/auth.js's concurrency guard without a browser and without a JS
// test framework.
//
// The module loader lives in tests/js/_auth_module.mjs, shared with
// test_auth_retry.mjs: it patches web/auth.js's one browser-root import to an
// inline stand-in so Node can import it, and everything else in the file runs
// byte-identical to what ships. `globalThis.fetch` and
// `globalThis.localStorage` are stubbed here per scenario.
//
// Run directly: `node tests/js/test_auth_concurrency.mjs` (exit 0 = pass).
// Wired into pytest via tests/test_js_auth.py so pytest stays the single
// entry point.

import { strict as assert } from "node:assert";

import { loadPatchedModule, stubLocalStorage } from "./_auth_module.mjs";

function deferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
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
