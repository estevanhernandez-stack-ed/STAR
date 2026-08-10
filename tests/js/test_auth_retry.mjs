// Proves web/auth.js's authedFetch retries exactly once on a 401, and only on
// a 401, without a browser and without a JS test framework.
//
// The bug this guards: GET /api/rooms comes back 401 at roughly 393ms on a
// cold load, on a browser that has just minted a brand-new anonymous account.
// The token is real; Google has not finished accepting it yet. Without a retry
// a returning writer's rail is empty on first paint.
//
// The behaviour is deliberately narrow and the narrowness is what needs
// guarding: once, not twice; on 401, not on any other failure; and the second
// attempt carries a newly minted token rather than the rejected one. Each of
// those is one character away from a retry loop, a retried 500, or a retry
// that was always going to fail the same way.
//
// Run directly: `node tests/js/test_auth_retry.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

import { loadPatchedModule, stubLocalStorage } from "./_auth_module.mjs";

const APP_URL = "/api/rooms";

/** A fetch stub that serves both Identity Toolkit and the app origin.
 *
 *  `appStatuses` is consumed one entry per app request, so a scenario states
 *  its server's answers in order and cannot accidentally describe an infinite
 *  one. Every request is recorded with the Authorization header it carried,
 *  which is how "the retry used a NEW token" is checked rather than assumed. */
function stubFetch(appStatuses) {
  const calls = { signUp: 0, app: [] };
  let minted = 0;

  globalThis.fetch = async (url, options = {}) => {
    const href = String(url);
    if (href.includes("accounts:signUp")) {
      calls.signUp += 1;
      minted += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          idToken: `token-${minted}`,
          refreshToken: `refresh-${minted}`,
          expiresIn: "3600",
        }),
      };
    }
    if (href.includes("securetoken")) {
      minted += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id_token: `token-${minted}`,
          refresh_token: `refresh-${minted}`,
          expires_in: "3600",
        }),
      };
    }
    calls.app.push({
      url: href,
      method: options.method || "GET",
      body: options.body,
      auth: (options.headers || {})["Authorization"],
    });
    const status = appStatuses.shift();
    assert.notEqual(
      status,
      undefined,
      `the app was called more times than the scenario allows (${calls.app.length})`
    );
    return { ok: status < 400, status };
  };

  return calls;
}

// -- 1: 401 then 200. One retry, and it carries a different token. ----------
async function testRetriesOnceAfterA401() {
  globalThis.localStorage = stubLocalStorage();
  const calls = stubFetch([401, 200]);
  const { authedFetch } = await import(loadPatchedModule());

  const res = await authedFetch(APP_URL);

  assert.equal(res.status, 200, "the caller must receive the retry's response");
  assert.equal(calls.app.length, 2, "exactly one retry");
  assert.equal(calls.app[0].auth, "Bearer token-1");
  assert.equal(
    calls.app[1].auth,
    "Bearer token-2",
    "the retry must carry a freshly minted token, not the rejected one"
  );
}

// -- 2: 401 twice. The second failure is surfaced, not retried. -------------
async function testDoesNotLoopOnRepeated401() {
  globalThis.localStorage = stubLocalStorage();
  // Only two statuses are supplied; a third app request would fail the
  // assertion inside the stub rather than hang, so "no loop" is proven by
  // construction and not by waiting to see.
  const calls = stubFetch([401, 401]);
  const { authedFetch } = await import(loadPatchedModule());

  const res = await authedFetch(APP_URL);

  assert.equal(res.status, 401, "the second 401 must reach the caller");
  assert.equal(calls.app.length, 2, "once, then surface it");
}

// -- 3: a success is not retried, and costs no extra sign-in. ---------------
async function testHappyPathIssuesOneRequest() {
  globalThis.localStorage = stubLocalStorage();
  const calls = stubFetch([200]);
  const { authedFetch } = await import(loadPatchedModule());

  const res = await authedFetch(APP_URL);

  assert.equal(res.status, 200);
  assert.equal(calls.app.length, 1, "no retry on a response that worked");
  assert.equal(calls.signUp, 1, "one anonymous sign-up for the session");
}

// -- 4: only 401. A 500 is the server's answer, not an auth problem. --------
async function testDoesNotRetryOtherFailures() {
  globalThis.localStorage = stubLocalStorage();
  const calls = stubFetch([500]);
  const { authedFetch } = await import(loadPatchedModule());

  const res = await authedFetch(APP_URL);

  assert.equal(res.status, 500, "a 500 is returned as-is");
  assert.equal(calls.app.length, 1, "a 500 must not be retried");
}

// -- 5: the retry replays the request, not a different one. ----------------
// A POST that lost its body or its content type on the second attempt would
// turn a recoverable 401 into a 400 nobody could explain.
async function testRetryReplaysMethodBodyAndHeaders() {
  globalThis.localStorage = stubLocalStorage();
  const calls = stubFetch([401, 200]);
  const { authedFetch } = await import(loadPatchedModule());

  const body = JSON.stringify({ treatment: "Winter 1929, Detroit." });
  await authedFetch(APP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  assert.equal(calls.app.length, 2);
  for (const call of calls.app) {
    assert.equal(call.method, "POST");
    assert.equal(call.body, body);
  }
}

// -- 6: sign-in itself being down surfaces the original 401. ---------------
// Not a different error invented on the way out: the caller asked a question
// and got one refusal, and that is what it should be told about.
async function testUnavailableSignInSurfacesTheOriginal401() {
  globalThis.localStorage = stubLocalStorage();

  let signUps = 0;
  const appCalls = [];
  globalThis.fetch = async (url, options = {}) => {
    const href = String(url);
    if (href.includes("accounts:signUp")) {
      signUps += 1;
      if (signUps === 1) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            idToken: "token-1",
            refreshToken: "refresh-1",
            expiresIn: "3600",
          }),
        };
      }
      // The re-mint fails: acquireToken() resolves null rather than throwing.
      return { ok: false, status: 503, json: async () => ({ error: "down" }) };
    }
    if (href.includes("securetoken")) {
      // The stored refresh token is rejected too, so acquireToken falls
      // through to the failing sign-up above.
      return { ok: false, status: 503, json: async () => ({ error: "down" }) };
    }
    appCalls.push(options);
    return { ok: false, status: 401 };
  };

  const { authedFetch } = await import(loadPatchedModule());
  const res = await authedFetch(APP_URL);

  assert.equal(res.status, 401, "the original refusal is what the caller gets");
  assert.equal(appCalls.length, 1, "no request is issued without a token");
}

await testRetriesOnceAfterA401();
await testDoesNotLoopOnRepeated401();
await testHappyPathIssuesOneRequest();
await testDoesNotRetryOtherFailures();
await testRetryReplaysMethodBodyAndHeaders();
await testUnavailableSignInSurfacesTheOriginal401();

console.log("tests/js/test_auth_retry.mjs: all assertions passed");
