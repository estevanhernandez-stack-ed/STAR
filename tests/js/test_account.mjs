// Proves web/auth.js's Google linking mechanics without a browser, without a
// network, and without a JS test framework.
//
// The flow under test is a full-page OIDC redirect: location.assign out to
// accounts.google.com, an ID token back in the URL fragment, then one POST to
// accounts:signInWithIdp carrying the CURRENT anonymous idToken, which is the
// field that makes the exchange a link rather than a sign-in. Item 1 proved
// that shape against the live API on 2026-08-10 (process-notes.md); everything
// here is the client half of it, driven off stubs shaped to the response that
// round trip actually returned.
//
// What each scenario is guarding, in the order they appear:
//
//   · the authorize URL carries the parameters the registered OAuth client was
//     proved with, and the redirect_uri is origin + "/" character for character
//   · the returned fragment is stripped from the address bar BEFORE the token
//     exchange is issued, not after it
//   · a `state` that does not match what this browser stashed never reaches
//     Identity Toolkit at all
//   · a localId that is not the pre-redirect uid aborts hard, persists nothing,
//     and leaves the prior refresh token exactly where it was
//   · every row of spec.md's error table produces its own sentence, because a
//     single generic "linking failed" fails prd.md's criterion outright
//   · an absent GOOGLE_OAUTH_CLIENT_ID reads as "linking is unavailable" while
//     every other path in the module still works
//   · sign-out clears enough state that the next getIdToken() mints a new
//     anonymous account, and an acquire in flight cannot undo it
//
// Run directly: `node tests/js/test_account.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

import { loadPatchedModule, stubLocalStorage } from "./_auth_module.mjs";

const ORIGIN = "https://star-390753828501.us-central1.run.app";
const LINK_KEY = "star_link_pending";
const RUN_KEY = "star_link_run";
const STORE_KEY = "star_refresh_token";

// A shared, ordered log of the side effects that have to happen in a
// particular order. Asserting on positions in this beats asserting each one
// happened, because the ordering IS the requirement for the fragment strip.
let trace = [];

/** Installs the browser globals web/auth.js reaches for. */
function stubBrowser({ hash = "", pathname = "/", search = "" } = {}) {
  trace = [];
  const assigns = [];
  const replaced = [];

  globalThis.localStorage = stubLocalStorage();
  globalThis.sessionStorage = stubLocalStorage();
  globalThis.location = {
    origin: ORIGIN,
    pathname,
    search,
    hash,
    assign(url) {
      assigns.push(url);
      trace.push("assign");
    },
  };
  globalThis.history = {
    replaceState(_state, _title, url) {
      replaced.push(url);
      trace.push("replaceState");
    },
  };

  return { assigns, replaced };
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body };
}

/** A fetch stub serving Identity Toolkit, securetoken, and the app origin.
 *
 *  `idp` is the scenario's answer for accounts:signInWithIdp — either a
 *  response object or a function that throws, which is how the network-failure
 *  row is exercised without a timer. */
function stubIdentity({ idp, refreshToken = "anon-refresh", uid = "uid-anon" } = {}) {
  const calls = { signUp: 0, refresh: 0, idp: [], app: [] };
  let minted = 0;

  globalThis.fetch = async (url, options = {}) => {
    const href = String(url);
    if (href.includes("accounts:signUp")) {
      calls.signUp += 1;
      minted += 1;
      trace.push("signUp");
      return jsonResponse({
        idToken: `anon-token-${minted}`,
        refreshToken: `${refreshToken}-${calls.signUp}`,
        expiresIn: "3600",
        localId: `${uid}-${calls.signUp}`,
      });
    }
    if (href.includes("securetoken")) {
      calls.refresh += 1;
      minted += 1;
      trace.push("refresh");
      return jsonResponse({
        id_token: `anon-token-${minted}`,
        // Returned unchanged so a scenario can assert "the prior refresh token
        // is still the one in storage" against a fixed string.
        refresh_token: refreshToken,
        expires_in: "3600",
        user_id: uid,
      });
    }
    if (href.includes("accounts:signInWithIdp")) {
      calls.idp.push({ url: href, body: JSON.parse(options.body) });
      trace.push("signInWithIdp");
      if (typeof idp === "function") return idp();
      return idp;
    }
    calls.app.push({ url: href, auth: (options.headers || {})["Authorization"] });
    return { ok: true, status: 200, json: async () => ({ rooms: [] }) };
  };

  return calls;
}

/** A session already signed in anonymously, exactly as a returning page load
 *  finds it: a refresh token in localStorage and nothing in memory. */
function seedAnonymousSession(refreshToken = "anon-refresh") {
  globalThis.localStorage.setItem(STORE_KEY, refreshToken);
}

function seedLinkStash(stash) {
  globalThis.sessionStorage.setItem(LINK_KEY, JSON.stringify(stash));
}

function readStash(key) {
  const raw = globalThis.sessionStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}

function fakeJwt(claims) {
  const encode = (obj) => Buffer.from(JSON.stringify(obj), "utf8").toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode(claims)}.signature`;
}

const LINKED_RESPONSE = {
  federatedId: "https://accounts.google.com/1234",
  providerId: "google.com",
  email: "writer@example.com",
  emailVerified: true,
  fullName: "A Writer",
  localId: "uid-anon",
  displayName: "A Writer",
  idToken: "linked-id-token",
  refreshToken: "linked-refresh",
  // A string, exactly as measured. remember() coerces it with Number(); this
  // test exists partly so nobody "fixes" that into a double conversion.
  expiresIn: "3600",
  oauthIdToken: "google-id-token",
  kind: "identitytoolkit#VerifyAssertionResponse",
};

// -- 1: the authorize URL, and what goes into sessionStorage before it. -----
async function testBeginMintsStateAndLeaves() {
  const { assigns } = stubBrowser({ pathname: "/", search: "" });
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  auth.setLiveRunProvider(() => ({
    run_id: "run-7",
    stream_key: "key-7",
    last_event_id: 12,
  }));

  const result = await auth.beginGoogleLink({ returnTo: "/" });

  assert.equal(result.status, "redirecting");
  assert.equal(assigns.length, 1, "beginGoogleLink must navigate exactly once");

  const url = new URL(assigns[0]);
  assert.equal(url.origin + url.pathname, "https://accounts.google.com/o/oauth2/v2/auth");
  assert.equal(url.searchParams.get("response_type"), "id_token");
  assert.equal(url.searchParams.get("scope"), "openid email profile");
  assert.equal(
    url.searchParams.get("redirect_uri"),
    `${ORIGIN}/`,
    "the redirect_uri must be origin + a trailing slash, which is what is registered"
  );
  assert.equal(url.searchParams.get("prompt"), "select_account");
  assert.ok(url.searchParams.get("client_id"), "the client id must travel");
  assert.match(
    assigns[0],
    /scope=openid%20email%20profile/,
    "spaces in scope are %20-encoded, which is the form item 1 proved"
  );

  const stash = readStash(LINK_KEY);
  assert.equal(stash.state, url.searchParams.get("state"));
  assert.equal(stash.nonce, url.searchParams.get("nonce"));
  assert.notEqual(stash.state, stash.nonce, "state and nonce are separate values");
  assert.equal(stash.uid, "uid-anon", "the pre-redirect uid is what the return asserts against");
  assert.equal(stash.returnTo, "/");

  const run = readStash(RUN_KEY);
  assert.deepEqual(run, { run_id: "run-7", stream_key: "key-7", last_event_id: 12 });
}

// -- 2: no live run means no run stash left behind for the next load. -------
async function testBeginWithoutALiveRunStashesNoRun() {
  stubBrowser();
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  auth.setLiveRunProvider(() => null);
  await auth.beginGoogleLink();

  assert.equal(readStash(RUN_KEY), null);
  assert.equal(auth.takeStashedRun(), null);
}

// -- 3: the run stash is consumed once, not once per load. ------------------
async function testStashedRunIsTakenOnce() {
  stubBrowser();
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  auth.setLiveRunProvider(() => ({ run_id: "run-7", stream_key: "key-7", last_event_id: 3 }));
  await auth.beginGoogleLink();

  assert.deepEqual(auth.takeStashedRun(), {
    run_id: "run-7",
    stream_key: "key-7",
    last_event_id: 3,
  });
  assert.equal(
    auth.takeStashedRun(),
    null,
    "a stash that survives its own resume reopens a dead stream on every later load"
  );
}

// -- 4: the happy path. Fragment stripped first, uid preserved, token kept. --
async function testCompleteLinksAndKeepsTheUid() {
  const { replaced } = stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "NONCE-1", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.status, "linked");
  assert.equal(result.uid, "uid-anon", "the uid is preserved, which is the whole promise");
  assert.equal(result.provider, "google.com");
  assert.equal(result.email, "writer@example.com");

  assert.equal(replaced.length, 1, "the fragment is stripped exactly once");
  assert.equal(replaced[0], "/", "and it is stripped to path + search, with no fragment left");
  assert.ok(
    trace.indexOf("replaceState") < trace.indexOf("signInWithIdp"),
    "the fragment must leave the address bar BEFORE the exchange is issued"
  );

  assert.equal(calls.idp.length, 1);
  const body = calls.idp[0].body;
  assert.equal(
    body.idToken,
    "anon-token-1",
    "the current anonymous ID token is the field that makes this a link and not a sign-in"
  );
  assert.equal(body.postBody, "id_token=google-token&providerId=google.com");
  assert.equal(body.requestUri, ORIGIN);
  assert.equal(body.returnSecureToken, true);
  assert.equal(body.returnIdpCredential, true);

  assert.equal(
    globalThis.localStorage.getItem(STORE_KEY),
    "linked-refresh",
    "the linked refresh token replaces the anonymous one"
  );
  assert.equal(
    await auth.getIdToken(),
    "linked-id-token",
    "the linked token is live in memory, with no further network call"
  );
  assert.equal(readStash(LINK_KEY), null, "the link stash is consumed");
}

// -- 5: two callers on one load share one exchange. ------------------------
// app.js calls completeGoogleLink to get the token in place before the rail is
// drawn; the account surface calls it again to find out what to render. They
// are reading the same event and must not be able to disagree about it.
async function testCompleteIsResolvedOnce() {
  stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const [first, second] = await Promise.all([
    auth.completeGoogleLink(),
    auth.completeGoogleLink(),
  ]);

  assert.equal(calls.idp.length, 1, "one redirect, one exchange");
  assert.equal(first, second, "both callers read the same result object");
  assert.equal((await auth.completeGoogleLink()).status, "linked");
}

// -- 6: THE HARD ABORT. A localId that moved is a switch, not a link. -------
async function testUidMismatchAbortsAndRestoresTheRefreshToken() {
  stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
  stubIdentity({
    idp: jsonResponse({ ...LINKED_RESPONSE, localId: "uid-somebody-else" }),
  });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.status, "failed");
  assert.equal(result.reason, "uid-mismatch");
  assert.ok(result.message.length > 0);
  assert.equal(
    globalThis.localStorage.getItem(STORE_KEY),
    "anon-refresh",
    "the prior refresh token stays, and the linked one is never persisted"
  );
  assert.equal(
    await auth.getIdToken(),
    "anon-token-1",
    "the session is still the account it was, on the token it already held"
  );
}

// -- 7: a state that does not match never reaches Identity Toolkit. ---------
async function testStateMismatchAbortsBeforeAnyExchange() {
  stubBrowser({ hash: "#id_token=google-token&state=NOT-THE-ONE" });
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.reason, "state-mismatch");
  assert.equal(calls.idp.length, 0, "a fragment this browser did not ask for is not exchanged");
  assert.equal(globalThis.localStorage.getItem(STORE_KEY), "anon-refresh");
}

// -- 8: a fragment arriving with no stash at all. --------------------------
async function testMissingStashAborts() {
  stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.reason, "state-missing");
  assert.equal(calls.idp.length, 0);
}

// -- 9: an ordinary page load is not an event. -----------------------------
async function testNoFragmentAndNoStashIsSilent() {
  const { replaced } = stubBrowser();
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.status, "none");
  assert.equal(result.message, "", "nothing happened, so nothing is said");
  assert.equal(calls.idp.length, 0);
  assert.equal(replaced.length, 0, "there is no fragment to strip");
}

// -- 10: every row of spec.md's error table, each with its own sentence. ----
// prd.md requires the message to name WHICH failure happened. A generic
// "linking failed" across this table fails the criterion, so the table is
// walked here and the messages are compared against each other rather than
// each one being checked in isolation.
async function testEveryErrorRowHasItsOwnMessage() {
  const rows = [
    {
      name: "already linked elsewhere",
      reason: "already-linked",
      idp: () =>
        jsonResponse(
          { error: { message: "FEDERATED_USER_ID_ALREADY_LINKED" } },
          { ok: false, status: 400 }
        ),
    },
    {
      name: "the email is taken",
      reason: "email-exists",
      idp: () => jsonResponse({ error: { message: "EMAIL_EXISTS" } }, { ok: false, status: 400 }),
    },
    {
      name: "the credential went stale",
      reason: "credential-too-old",
      // Delivered as a 200 with errorMessage, which is the door
      // returnIdpCredential: true is documented to use. Item 1 measured only
      // the success path, so web/auth.js reads both doors and this row proves
      // the second one.
      idp: () => jsonResponse({ errorMessage: "CREDENTIAL_TOO_OLD_LOGIN_AGAIN" }),
    },
    {
      name: "the IdP response was not usable",
      reason: "idp-response",
      idp: () =>
        jsonResponse(
          { error: { message: "INVALID_IDP_RESPONSE : Cannot parse the response" } },
          { ok: false, status: 400 }
        ),
    },
    {
      name: "the sign-in service could not be reached",
      reason: "network",
      idp: () => {
        throw new TypeError("Failed to fetch");
      },
    },
    {
      name: "the uid moved",
      reason: "uid-mismatch",
      idp: () => jsonResponse({ ...LINKED_RESPONSE, localId: "uid-somebody-else" }),
    },
  ];

  const seen = new Map();

  for (const row of rows) {
    stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
    stubIdentity({ idp: row.idp });
    seedAnonymousSession();
    seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

    const auth = await import(loadPatchedModule());
    const result = await auth.completeGoogleLink();

    assert.equal(result.reason, row.reason, `${row.name}: wrong row`);
    assert.equal(result.status, "failed", `${row.name}: the surface must show a message`);
    assert.ok(result.message.length > 20, `${row.name}: the message must say something`);
    assert.doesNotMatch(
      result.message,
      /linking failed/i,
      `${row.name}: a generic sentence fails prd.md's criterion`
    );
    assert.equal(
      globalThis.localStorage.getItem(STORE_KEY),
      "anon-refresh",
      `${row.name}: the session must be untouched after a refused link`
    );

    assert.equal(
      seen.has(result.message),
      false,
      `${row.name}: shares its message with ${seen.get(result.message)}`
    );
    seen.set(result.message, row.name);
  }

  // The seventh row: the redirect that never came back. spec.md's answer for
  // it is "Nothing. No error state on screen", so its own message is the
  // absence of one — a distinct outcome, deliberately without a sentence.
  stubBrowser();
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const abandoned = await auth.completeGoogleLink();

  assert.equal(abandoned.status, "abandoned");
  assert.equal(abandoned.reason, "abandoned");
  assert.equal(abandoned.message, "", "a link nobody completed leaves no error on screen");
  assert.equal(calls.idp.length, 0);
  assert.equal(globalThis.localStorage.getItem(STORE_KEY), "anon-refresh");
  assert.equal(seen.size, 6, "six sentences for the six rows that get one");
}

// -- 11: declining at Google's own screen is the same non-event. ------------
async function testAccessDeniedIsSilent() {
  stubBrowser({ hash: "#error=access_denied&state=STATE-1" });
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.status, "abandoned");
  assert.equal(result.message, "");
  assert.equal(calls.idp.length, 0);
  assert.equal(
    await auth.getIdToken(),
    "anon-token-1",
    "same session, same uid, and nothing on screen to explain away"
  );
}

// -- 12: a refusal nobody wrote copy for still names itself. ---------------
async function testUnknownRefusalNamesTheCode() {
  stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
  stubIdentity({
    idp: () =>
      jsonResponse({ error: { message: "SOMETHING_NEW" } }, { ok: false, status: 400 }),
  });
  seedAnonymousSession();
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.reason, "unknown-refusal");
  assert.match(result.message, /SOMETHING_NEW/);
}

// -- 13: no client id. Linking reads as unavailable; nothing else breaks. ---
async function testAbsentClientIdDisablesLinkingOnly() {
  const { assigns } = stubBrowser();
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule({ googleClientId: "" }));

  assert.equal(auth.linkingAvailable(), false);

  const result = await auth.beginGoogleLink();
  assert.equal(result.reason, "unavailable");
  assert.ok(result.message.length > 20, "and it says why, rather than doing nothing");
  assert.equal(assigns.length, 0, "no navigation is started");
  assert.equal(readStash(LINK_KEY), null, "and nothing is stashed for a trip that did not happen");

  // Every other path still works, which is the fourth criterion under
  // prd.md > Identity That Outlives The Browser.
  assert.equal(await auth.getIdToken(), "anon-token-1");
  const res = await auth.authedFetch("/api/rooms");
  assert.equal(res.ok, true);
  assert.equal(calls.app.length, 1);
  assert.equal(calls.app[0].auth, "Bearer anon-token-1");
  assert.equal((await auth.completeGoogleLink()).status, "none");
}

async function testClientIdPresentReadsAsAvailable() {
  stubBrowser();
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  const auth = await import(loadPatchedModule());
  assert.equal(auth.linkingAvailable(), true);
}

// -- 14: a browser that refuses sessionStorage does not start the trip. -----
async function testUnwritableStashBlocksTheRedirect() {
  const { assigns } = stubBrowser();
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  globalThis.sessionStorage.setItem = () => {
    throw new Error("storage disabled");
  };

  const auth = await import(loadPatchedModule());
  const result = await auth.beginGoogleLink();

  assert.equal(result.reason, "blocked");
  assert.equal(
    assigns.length,
    0,
    "a return this browser could not verify is a trip it must not start"
  );
}

// -- 15: sign-out. The next getIdToken mints a NEW anonymous account. ------
async function testSignOutMintsAFreshAccountNext() {
  stubBrowser();
  const calls = stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  assert.equal(await auth.getIdToken(), "anon-token-1");
  assert.equal(calls.refresh, 1);

  auth.signOut();

  assert.equal(globalThis.localStorage.getItem(STORE_KEY), null, "the refresh token is gone");
  const next = await auth.getIdToken();
  assert.equal(calls.signUp, 1, "with nothing to refresh, a new anonymous account is minted");
  assert.equal(next, "anon-token-2");
  assert.notEqual(next, "anon-token-1", "and it is not the token from the session just left");
}

// -- 16: an acquire in flight cannot undo a sign-out. ---------------------
// The `pending` guard stops the next CALLER from joining a stale acquire; it
// does not stop the in-flight request from finishing and calling remember(),
// which would write the signed-out session's refresh token straight back.
async function testSignOutDuringAnAcquireDoesNotResurrectTheSession() {
  stubBrowser();
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });

  globalThis.localStorage = stubLocalStorage();
  globalThis.sessionStorage = stubLocalStorage();
  seedAnonymousSession("anon-refresh");
  globalThis.fetch = async (url) => {
    const href = String(url);
    if (href.includes("securetoken")) {
      // Suspend here so sign-out lands while the refresh is still in flight.
      await gate;
      return jsonResponse({
        id_token: "anon-token-1",
        refresh_token: "anon-refresh",
        expires_in: "3600",
        user_id: "uid-anon",
      });
    }
    return jsonResponse({
      idToken: "anon-token-2",
      refreshToken: "fresh-refresh",
      expiresIn: "3600",
      localId: "uid-new",
    });
  };

  const auth = await import(loadPatchedModule());
  const inFlight = auth.getIdToken();
  auth.signOut();
  release();

  assert.equal(await inFlight, null, "a token for an account already left is not a token");
  assert.equal(
    globalThis.localStorage.getItem(STORE_KEY),
    null,
    "and it must not put the signed-out refresh token back"
  );
}

// -- 17: what sign-out will do, said before it happens. -------------------
async function testSignOutNoticeTellsTheTruthForBothCases() {
  stubBrowser();
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();

  const auth = await import(loadPatchedModule());
  const anonymousNotice = await auth.signOutNotice();
  assert.ok(anonymousNotice.length > 40);
  assert.match(anonymousNotice, /not deleted/, "an anonymous sign-out is not a delete");

  // Now with a linked token in memory. The claims are what linkedProvider
  // reads, so a token carrying a google.com identity is what makes the notice
  // switch to the reassuring truth.
  globalThis.fetch = async (url, options = {}) => {
    const href = String(url);
    if (href.includes("accounts:signInWithIdp")) {
      return jsonResponse({
        ...LINKED_RESPONSE,
        idToken: fakeJwt({
          email: "writer@example.com",
          firebase: {
            sign_in_provider: "google.com",
            identities: { "google.com": ["1234"], email: ["writer@example.com"] },
          },
        }),
      });
    }
    return jsonResponse({
      id_token: "anon-token-1",
      refresh_token: "anon-refresh",
      expires_in: "3600",
      user_id: "uid-anon",
    });
  };
  globalThis.location.hash = "#id_token=google-token&state=STATE-1";
  seedLinkStash({ state: "STATE-1", nonce: "N", uid: "uid-anon", returnTo: "/" });

  const linkedAuth = await import(loadPatchedModule());
  await linkedAuth.completeGoogleLink();

  const linkedNotice = await linkedAuth.signOutNotice();
  assert.match(linkedNotice, /writer@example\.com/, "it names the account the rooms stay with");
  assert.notEqual(linkedNotice, anonymousNotice, "the two cases are not the same sentence");
}

// -- 18: linkedProvider reads what is attached, not how the session began. --
async function testLinkedProviderReportsTheAttachedAccount() {
  stubBrowser();
  globalThis.localStorage = stubLocalStorage();
  globalThis.sessionStorage = stubLocalStorage();
  seedAnonymousSession();

  const anonymousToken = fakeJwt({
    firebase: { sign_in_provider: "anonymous", identities: {} },
  });
  globalThis.fetch = async () =>
    jsonResponse({
      id_token: anonymousToken,
      refresh_token: "anon-refresh",
      expires_in: "3600",
      user_id: "uid-anon",
    });

  const auth = await import(loadPatchedModule());
  assert.equal(await auth.linkedProvider(), null, "an anonymous session has no attached account");

  // A token with a google.com identity, which is the durable record of what is
  // attached — sign_in_provider records how this session began, which is a
  // different question.
  globalThis.localStorage = stubLocalStorage();
  seedAnonymousSession();
  const linkedToken = fakeJwt({
    email: "writer@example.com",
    name: "A Writer",
    firebase: {
      sign_in_provider: "anonymous",
      identities: { "google.com": ["1234"] },
    },
  });
  globalThis.fetch = async () =>
    jsonResponse({
      id_token: linkedToken,
      refresh_token: "anon-refresh",
      expires_in: "3600",
      user_id: "uid-anon",
    });

  const linkedAuth = await import(loadPatchedModule());
  const linked = await linkedAuth.linkedProvider();
  assert.equal(linked.provider, "google.com");
  assert.equal(linked.email, "writer@example.com");
  assert.equal(linked.name, "A Writer");
}

// -- 19: returnTo never becomes an open redirect. -------------------------
async function testReturnToIsFilteredToASameOriginPath() {
  stubBrowser({ hash: "#id_token=google-token&state=STATE-1" });
  stubIdentity({ idp: jsonResponse(LINKED_RESPONSE) });
  seedAnonymousSession();
  seedLinkStash({
    state: "STATE-1",
    nonce: "N",
    uid: "uid-anon",
    returnTo: "//evil.example/steal",
  });

  const auth = await import(loadPatchedModule());
  const result = await auth.completeGoogleLink();

  assert.equal(result.status, "linked");
  assert.equal(result.returnTo, "/", "a protocol-relative target is not a path");
}

await testBeginMintsStateAndLeaves();
await testBeginWithoutALiveRunStashesNoRun();
await testStashedRunIsTakenOnce();
await testCompleteLinksAndKeepsTheUid();
await testCompleteIsResolvedOnce();
await testUidMismatchAbortsAndRestoresTheRefreshToken();
await testStateMismatchAbortsBeforeAnyExchange();
await testMissingStashAborts();
await testNoFragmentAndNoStashIsSilent();
await testEveryErrorRowHasItsOwnMessage();
await testAccessDeniedIsSilent();
await testUnknownRefusalNamesTheCode();
await testAbsentClientIdDisablesLinkingOnly();
await testClientIdPresentReadsAsAvailable();
await testUnwritableStashBlocksTheRedirect();
await testSignOutMintsAFreshAccountNext();
await testSignOutDuringAnAcquireDoesNotResurrectTheSession();
await testSignOutNoticeTellsTheTruthForBothCases();
await testLinkedProviderReportsTheAttachedAccount();
await testReturnToIsFilteredToASameOriginPath();

console.log("tests/js/test_account.mjs: all assertions passed");
