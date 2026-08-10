// Anonymous identity, no SDK — and, since Phase 4, the Google account that can
// be attached to it without replacing it.
//
// Identity Toolkit's REST endpoints do anonymous sign-up and token refresh
// directly, which keeps the browser free of a vendored library and of any
// CDN request. The refresh token lives in localStorage so a returning writer
// keeps the same uid and therefore the same rooms.
//
// The Firebase API key here is a public project identifier, not a secret.
// Security comes from the ID token the server verifies. GOOGLE.clientId is
// public for the same reason — an OAuth client id is an identifier, and the
// only secret in the linking flow is the ID token Google mints for it.
//
// Linking is ADDITIVE and that is the whole design: the anonymous account is
// the front door, a Google account is an upgrade on it, and the uid never
// changes. Everything below that looks defensive — the state comparison, the
// localId assertion, the refusal to persist a token whose uid moved — exists
// to keep that one property true, because the failure mode of getting it wrong
// is a reader silently switched to an empty account with their rooms gone.

import { FIREBASE, GOOGLE } from "/config.js";

const STORE_KEY = "star_refresh_token";
const SIGNUP = "https://identitytoolkit.googleapis.com/v1/accounts:signUp";
const REFRESH = "https://securetoken.googleapis.com/v1/token";
const SIGN_IN_WITH_IDP =
  "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp";
const GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth";

// Two sessionStorage keys, not one, and the split is load-bearing.
// completeGoogleLink() consumes and deletes LINK_KEY on the first load after
// the redirect — one attempt per redirect, so a replayed fragment finds no
// state to match. The live run has to outlive that deletion, because app.js
// reads it after the link has already resolved. One key would mean either a
// replayable link stash or a run that gets thrown away before it is used.
const LINK_KEY = "star_link_pending";
const RUN_KEY = "star_link_run";

let idToken = null;
let expiresAt = 0;
// The uid the current token belongs to, read off the response that minted it
// (`localId` on signUp and signInWithIdp, `user_id` on a securetoken refresh —
// all three measured in process-notes.md). It is held because beginGoogleLink
// has to record which account it was standing in before it leaves the page,
// and completeGoogleLink has to compare that against the localId that comes
// back. Read off the response rather than decoded out of the JWT because the
// response field is the one item 1 actually measured.
let uid = null;
// Concurrency guard: two callers arriving before the first sign-in/refresh
// resolves must not both hit the network — that would mint two anonymous
// Firebase accounts racing over which refresh token wins in localStorage,
// breaking the "same uid, same rooms on reload" promise above. Every caller
// that arrives while a request is already in flight awaits the same promise
// instead of starting its own.
let pending = null;
// Bumped by signOut(). An acquire that started before the sign-out resolves
// after it, and without this it would call remember() and write the signed-out
// session's refresh token straight back into localStorage — resurrecting the
// account the reader just left. The `pending` guard above does not cover this:
// clearing `pending` stops the next CALLER from joining, it does not stop the
// in-flight request from finishing. Same class of race, one layer down.
let sessionEpoch = 0;

async function signUpAnonymously() {
  const res = await fetch(`${SIGNUP}?key=${FIREBASE.apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ returnSecureToken: true }),
  });
  if (!res.ok) throw new Error("anonymous sign-in failed");
  return res.json();
}

async function refresh(refreshToken) {
  const res = await fetch(`${REFRESH}?key=${FIREBASE.apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=refresh_token&refresh_token=${encodeURIComponent(refreshToken)}`,
  });
  if (!res.ok) throw new Error("token refresh failed");
  const data = await res.json();
  return {
    idToken: data.id_token,
    refreshToken: data.refresh_token,
    expiresIn: data.expires_in,
    userId: data.user_id,
  };
}

/** Holds a freshly minted token, and the account it belongs to.
 *
 *  `userId` is optional and a falsy one leaves the remembered uid alone rather
 *  than clearing it: a caller that does not know the uid has not learned that
 *  there isn't one. Only signOut() clears it. */
function remember(token, refreshToken, expiresIn, userId) {
  idToken = token;
  if (userId) uid = String(userId);
  // Refresh a minute early rather than racing the expiry.
  expiresAt = Date.now() + (Number(expiresIn) - 60) * 1000;
  if (refreshToken) {
    // Losing durability of the refresh token (quota exceeded, storage
    // disabled in a privacy mode) is not the same failure as failing to
    // sign in — the session already holds a good idToken in memory. Only
    // cross-reload persistence is lost, so this write gets its own catch
    // rather than letting a storage error read as a sign-in failure.
    try {
      localStorage.setItem(STORE_KEY, refreshToken);
    } catch {
      // Ignored: see comment above.
    }
  }
}

function safeGetStored() {
  try {
    return localStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}

function safeRemoveStored() {
  try {
    localStorage.removeItem(STORE_KEY);
  } catch {
    // Storage is already unavailable; nothing to clean up.
  }
}

/** Puts a refresh token back exactly as it was.
 *
 *  Only the uid-mismatch abort calls this. Nothing on that path has written to
 *  storage yet, so this is belt and braces rather than a repair — but the whole
 *  point of that branch is that the reader's session is provably untouched, and
 *  "provably" is worth one write that is usually a no-op. */
function restoreStored(refreshToken) {
  if (!refreshToken) return;
  try {
    localStorage.setItem(STORE_KEY, refreshToken);
  } catch {
    // Same reasoning as remember()'s own catch: durability is lost, the live
    // session is not.
  }
}

async function acquireToken() {
  // getIdToken awaits this unguarded, so this function's contract is that
  // it never throws — every path returns a token or null. Without the
  // outer try/catch, a second storage failure inside the stale-token
  // cleanup (removeItem after getItem already threw) would escape both
  // inner catches and leave the caller with an unhandled rejection instead
  // of a null it can react to.
  //
  // `epoch` is read once here and checked after every await that produced a
  // token: a signOut() that landed while this was in flight means the token
  // now in hand belongs to an account the reader has already left, and writing
  // it back would undo the sign-out. Returning null is the honest answer —
  // getIdToken()'s next call starts a clean acquire on the new epoch.
  const epoch = sessionEpoch;
  try {
    const stored = safeGetStored();
    if (stored) {
      try {
        const r = await refresh(stored);
        if (epoch !== sessionEpoch) return null;
        remember(r.idToken, r.refreshToken, r.expiresIn, r.userId);
        return idToken;
      } catch {
        // A stale or revoked refresh token: fall through and start fresh.
        safeRemoveStored();
      }
    }

    try {
      const fresh = await signUpAnonymously();
      if (epoch !== sessionEpoch) return null;
      remember(fresh.idToken, fresh.refreshToken, fresh.expiresIn, fresh.localId);
      return idToken;
    } catch {
      return null;
    }
  } catch {
    return null;
  }
}

/** The session's ID token.
 *
 *  `{ fresh: true }` discards the cached token first, so the next call goes
 *  back to Identity Toolkit instead of handing back the one the server just
 *  rejected. It does NOT bypass the concurrency guard: a caller asking for a
 *  fresh token while an acquire is already in flight awaits that one, because
 *  the in-flight request is itself producing a token newer than the rejected
 *  one, and starting a second would be exactly the double-sign-up the guard
 *  exists to prevent. */
export async function getIdToken({ fresh = false } = {}) {
  if (fresh) {
    idToken = null;
    expiresAt = 0;
  }
  if (idToken && Date.now() < expiresAt) return idToken;
  if (pending) return pending;

  pending = acquireToken();
  try {
    return await pending;
  } finally {
    pending = null;
  }
}

function send(url, options, token) {
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}

/** One retry on 401, and only on 401.
 *
 *  THE BUG. Seen on cold loads since Task 2 and reproduced again in Task 7:
 *  `GET /api/rooms` comes back 401 at roughly 393ms, with a real token in the
 *  header, and the rail paints empty for a reader who has saved rooms. On demo
 *  day that reader is a judge, whose first impression is a product that lost
 *  their work.
 *
 *  WHAT IS ACTUALLY KNOWN, because the standing explanation turned out to be
 *  wrong. It was assumed to be a propagation lag — a token too new for Google
 *  to accept yet. Measured directly in Task 7: a token minted seconds earlier
 *  and sent at an age of 0ms was accepted five times out of five. Token age is
 *  not the cause, so a delay would not have fixed it and neither this retry nor
 *  anything else on this side can be claimed to. What IS established is that the
 *  refusal is intermittent and short-lived, that it is not a property of the
 *  token, and that star/auth.py's verify_token returns None for EVERY failure
 *  including a transient one in verification itself — so a forged token and a
 *  server that could not verify a good one are the same 401 here.
 *
 *  WHY A RETRY AND NOT A DELAY. A delay is a guess about a window nobody has
 *  measured, and now that the window is measured it is not about time-since-
 *  minting at all. A retry costs one round trip in exactly the case that was
 *  already broken and nothing at all otherwise, and it recovers every cause
 *  that is transient — which, on the evidence, this one is.
 *
 *  WHY ONCE. Twice is a loop with a small number in it. If the second attempt
 *  is also refused, the caller gets that response and says so: shell.js's
 *  refreshRail draws the rail with "Your filed rooms could not be reached just
 *  now. They are not lost — reload to try again.", and app.js's buildRoom shows
 *  the banner. A wrong answer arriving honestly beats a spinner that never
 *  resolves — but only if the answer is actually honest, and this comment used
 *  to claim "draws an empty rail" while the rail said "Nothing filed yet. Paste
 *  a treatment below and the department gets started." That is not empty, it is
 *  an assertion that the reader has no saved work, on the exact screen where
 *  this file has just established that we do not know. Fixed in shell.js's
 *  renderRail, and the sentence above is what it now renders.
 *
 *  WHY RETRYING A POST IS SAFE HERE. `_require_uid` is the first statement of
 *  create_room (star/server.py), ahead of the rate limiter, the daily cap,
 *  and the run itself. It is NOT the first statement of every handler:
 *  stream_events has no Authorization header to read (EventSource sends no
 *  custom headers) and is guarded by a per-run key instead. The conclusion
 *  below only ever rested on create_room, but a premise stated wider than it
 *  holds is a premise the next reader will reuse somewhere it does not. A 401 from this origin therefore
 *  means the request was refused before it could spend anything, so replaying
 *  it cannot start a second build. This is a property of that server, not a
 *  general truth about retrying POSTs, which is why it is written down here.
 *
 *  The retry re-mints rather than re-sending the same token. That covers the
 *  one cause a client can actually fix — a token this browser believes is live
 *  and the server does not — and it is not claimed to fix the cause measured
 *  above, which is not on this side. A null from `getIdToken` means sign-in
 *  itself is down, and the original 401 is returned untouched: inventing a
 *  different failure would tell the caller a different story about the same
 *  event.
 *
 *  WHAT THIS DOES NOT FIX, stated because one cold load in Task 7 did it: both
 *  attempts can be refused, roughly a second apart, and then the rail is empty
 *  and says so. This narrows the window; it does not close it. Closing it needs
 *  to start on the server, where the cause is — see the note in star/auth.py. */
export async function authedFetch(url, options = {}) {
  const first = await send(url, options, await getIdToken());
  if (first.status !== 401) return first;

  const token = await getIdToken({ fresh: true });
  if (!token) return first;
  return send(url, options, token);
}

// ---------------------------------------------------------------------------
// Attaching a Google account
// ---------------------------------------------------------------------------
//
// The shape, and why it is this shape. Google Identity Services is a remote
// <script> from accounts.google.com, and a remote script is the silent
// mid-demo failure the zero-third-party rule exists to prevent. So the
// interaction with Google is a NAVIGATION: location.assign to the OIDC
// authorize endpoint with response_type=id_token, and Google hands the token
// back in the URL fragment. Nothing is loaded from accounts.google.com, and
// the one fetch below goes to identitytoolkit.googleapis.com, which this file
// already calls for anonymous sign-up.
//
// Measured on 2026-08-10 against the live API before any of this was written
// (process-notes.md, "Item 1"), because both halves rested on documentation
// rather than on a round trip:
//
//   · response_type=id_token is still honoured for this client. The fragment
//     comes back as #id_token=…&state=…, with no access_token and no code.
//   · signInWithIdp accepted a Google ID token minted outside Firebase's own
//     handler, carrying a nonce Firebase never issued, HTTP 200 on the FIRST
//     attempt. The &nonce=<raw> retry the spec named as a fallback was never
//     needed, and the server-side code exchange named as the second fallback
//     is not built and must not be assumed by anything here.
//   · localId came back byte-identical to the pre-link uid.
//   · expiresIn is the STRING "3600". remember() already coerces with
//     Number(), so it is passed through untouched rather than converted twice.
//   · There is no oauthAccessToken. The implicit ID-token flow yields no
//     Google access token at all, so a leaked fragment is worth no reach into
//     Google's APIs — which is the honest bound on what the fragment is worth,
//     and it is still stripped from the address bar immediately.

/** Is linking offered at all?
 *
 *  GOOGLE_OAUTH_CLIENT_ID deliberately does not join star/config.py's
 *  validate_env(): that function fails the boot on anything whose absence would
 *  be SILENT, and this one's absence is loud by design. /config.js serves "",
 *  this returns false, and the account surface says linking is unavailable
 *  while every other path in the app works exactly as it did. */
export function linkingAvailable() {
  return Boolean(googleClientId());
}

function googleClientId() {
  // Optional-chained rather than assumed: an older /config.js that predates
  // the GOOGLE export is the same situation as an unset variable, and it
  // should read as "unavailable", not as a module that fails to evaluate.
  return String(GOOGLE?.clientId || "").trim();
}

/** The account attached to this session, or null when there is none.
 *
 *  Read from `firebase.identities` on the ID token rather than from
 *  `firebase.sign_in_provider`: identities is the durable record of what is
 *  ATTACHED, while sign_in_provider records how this particular session began.
 *  A reader who signed in anonymously and then linked is, by every meaning the
 *  card cares about, linked.
 *
 *  The claims are decoded without verifying the signature, and that is safe
 *  here for one reason worth stating: nothing is authorised on the strength of
 *  it. Every privileged action still carries the token to the server, which
 *  verifies it properly (star/auth.py). A tampered local token can make this
 *  browser draw the wrong label on its own screen and nothing else. */
export async function linkedProvider() {
  const token = idToken || (await getIdToken());
  const claims = decodeTokenClaims(token);
  if (!claims) return null;

  const identities = claims.firebase?.identities || {};
  // Firebase keys a federated identity by the provider's domain — google.com,
  // apple.com, github.com — and keys the two non-federated ones as plain
  // "email" and "phone". The dot is what separates a provider from a contact
  // detail, and it is the whole of the rule.
  const provider = Object.keys(identities).find((key) => key.includes("."));
  const signIn = claims.firebase?.sign_in_provider;
  const attached = provider || (signIn && signIn !== "anonymous" ? signIn : "");
  if (!attached) return null;

  return {
    provider: attached,
    email: String(claims.email || ""),
    name: String(claims.name || ""),
  };
}

/** A JWT's payload, or null. Never throws — every caller treats null as
 *  "anonymous, or a token this page cannot read", which are the same answer as
 *  far as anything on screen is concerned. */
function decodeTokenClaims(token) {
  try {
    const segment = String(token || "").split(".")[1];
    if (!segment) return null;
    const base64 = segment.replaceAll("-", "+").replaceAll("_", "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const binary = atob(padded);
    // Through TextDecoder rather than straight to JSON.parse: atob yields one
    // char per BYTE, so a display name outside ASCII would arrive mojibaked
    // and could break the parse outright.
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

/** Every outcome the flow can produce, and the sentence each one earns.
 *
 *  `status` is what the surface branches on: "linked" paints the account,
 *  "failed" shows `message`, and "none"/"abandoned" show nothing at all.
 *  `reason` is the specific row, kept separate so a caller can tell two
 *  outcomes apart even where spec.md's error table gives them one sentence.
 *
 *  Six of the seven rows in spec.md's table get their own distinct message,
 *  and the seventh — the reader who backed out of the redirect — deliberately
 *  gets none: prd.md requires "no error state left on screen" for a link
 *  nobody completed, so silence is that row's correct answer rather than a
 *  gap. A single generic "linking failed" across the table fails the criterion
 *  outright, which is why this is a table and not a catch. */
const OUTCOMES = {
  // Nothing was attempted. An ordinary page load.
  none: { status: "none", message: "" },

  // Row 7. The redirect never came back: the reader closed the tab at Google,
  // hit back, or declined. Their session is exactly as they left it and the
  // interface says nothing, because nothing happened to them.
  abandoned: { status: "abandoned", message: "" },

  // Row 1.
  "already-linked": {
    status: "failed",
    message:
      "This Google account is already attached to a different set of rooms. " +
      "You can sign in as that account instead, but the rooms on screen now " +
      "would not come along. Nothing here has changed.",
  },

  // Row 2. Same shape as row 1 and a different fact: the collision is on the
  // address, not on the federated id.
  "email-exists": {
    status: "failed",
    message:
      "An account here already uses this Google address, and it holds a " +
      "different set of rooms. You can sign in as that account instead, but " +
      "the rooms on screen now would not come along. Nothing here has changed.",
  },

  // Row 3.
  "credential-too-old": {
    status: "failed",
    message:
      "The sign-in took too long to come back, and Google's answer is no " +
      "longer accepted. Start the link again. Nothing here has changed.",
  },

  // Row 4, all three doors into it: Identity Toolkit calling the response
  // invalid, a `state` that does not match what this browser stashed, and a
  // stash that is not there to match against. spec.md groups them under one
  // sentence on purpose — from the reader's side they are the same event, and
  // naming a state mismatch specifically would describe an attack to the
  // person it was aimed at without giving them anything to do about it.
  "idp-response": { status: "failed", message: badResponseMessage() },
  "state-mismatch": { status: "failed", message: badResponseMessage() },
  "state-missing": { status: "failed", message: badResponseMessage() },

  // Row 5.
  network: {
    status: "failed",
    message:
      "The department could not reach the sign-in service. Nothing here has " +
      "changed. Check your connection and start the link again.",
  },

  // Row 6. The dangerous one — see completeGoogleLink.
  "uid-mismatch": {
    status: "failed",
    message:
      "That sign-in would have switched you to a different account rather " +
      "than attaching this one, so the department stopped before anything " +
      "was saved. Your session and your rooms are exactly as they were.",
  },

  // Outside the table, and both reachable before the redirect rather than
  // after it.
  unavailable: {
    status: "failed",
    message:
      "Attaching a Google account is not available on this deployment. " +
      "Everything else works exactly as it does now, and your rooms stay " +
      "with this browser.",
  },
  blocked: {
    status: "failed",
    message:
      "This browser did not allow the hand-off to Google's sign-in, so the " +
      "department did not start one. Nothing here has changed.",
  },
};

function badResponseMessage() {
  return (
    "The sign-in did not come back cleanly, so the department did not act on " +
    "it. Nothing here has changed. Start the link again."
  );
}

function outcome(reason, extra = {}) {
  const row = OUTCOMES[reason] || OUTCOMES["idp-response"];
  return { status: row.status, reason, message: row.message, ...extra };
}

/** Identity Toolkit's refusal codes, mapped to the rows above. */
const REFUSAL_CODES = {
  FEDERATED_USER_ID_ALREADY_LINKED: "already-linked",
  EMAIL_EXISTS: "email-exists",
  CREDENTIAL_TOO_OLD_LOGIN_AGAIN: "credential-too-old",
  INVALID_IDP_RESPONSE: "idp-response",
};

/** Leaves for Google, and only returns if it could not.
 *
 *  What goes into sessionStorage before the navigation, and why each piece is
 *  there:
 *
 *    state    compared against what comes back. A fragment arriving with a
 *             state this browser did not mint is not our redirect.
 *    nonce    handed to Google and carried inside the ID token it mints. Item
 *             1 measured that Identity Toolkit accepts a nonce it did not
 *             issue, so this is not load-bearing for the exchange; it is what
 *             stops a token minted for one authorize request being replayed
 *             into another.
 *    uid      the account we are standing in. completeGoogleLink asserts the
 *             localId that comes back equals this, and that assertion is the
 *             difference between linking and switching.
 *    returnTo where the surface wants to be afterwards. Never navigated to by
 *             this file — it is handed back to the caller, and it is filtered
 *             to a same-origin absolute path so a stashed value can never
 *             become an open redirect.
 *
 *  A live run is stashed separately (see RUN_KEY): the OAuth flow leaves the
 *  page, and {run_id, stream_key} live in app.js's page memory only, so a
 *  build in flight comes back unstreamable without this. The run itself
 *  survives — the asyncio task keeps going and _persist writes at terminal
 *  status — so what is being rescued is the stream, not the research. */
export async function beginGoogleLink({ returnTo } = {}) {
  const clientId = googleClientId();
  if (!clientId) return outcome("unavailable");

  // The uid has to be known BEFORE the page leaves, because the assertion on
  // the way back has nothing to compare against otherwise. No token means no
  // uid, and starting an OAuth round trip we could not finish safely is worse
  // than declining to start one.
  const token = await getIdToken();
  if (!token || !uid) return outcome("network");

  const state = randomHex(16);
  const nonce = randomHex(16);
  const target = safeReturnTo(returnTo);

  // Written before the navigation and checked for success: a browser that
  // refuses sessionStorage (a privacy mode, storage disabled) cannot verify
  // the return, so it must not start the trip either. This is the "blocked"
  // failure named in prd.md, in the form a redirect flow can actually take —
  // there is no popup here to be blocked.
  if (!writeStash(LINK_KEY, { state, nonce, uid, returnTo: target })) {
    return outcome("blocked");
  }
  stashLiveRun();

  // Built by hand rather than through URLSearchParams so `scope` travels as
  // %20-separated, which is the shape the authorize URL was proved with in
  // item 1. URLSearchParams would encode the spaces as "+", which Google also
  // accepts — but "also accepts" is a claim nobody measured here.
  const url =
    `${GOOGLE_AUTHORIZE}?client_id=${encodeURIComponent(clientId)}` +
    `&response_type=id_token` +
    `&scope=${encodeURIComponent("openid email profile")}` +
    `&redirect_uri=${encodeURIComponent(redirectUri())}` +
    `&nonce=${encodeURIComponent(nonce)}` +
    `&state=${encodeURIComponent(state)}` +
    `&prompt=select_account`;

  try {
    location.assign(url);
  } catch {
    removeStash(LINK_KEY);
    removeStash(RUN_KEY);
    return outcome("blocked");
  }
  return { status: "redirecting", reason: "redirecting", message: "", url };
}

/** The redirect URI Google is handed, and it must match a registered one
 *  character for character.
 *
 *  Origin plus a trailing slash, because that is what is registered on the
 *  OAuth client: https://star-390753828501.us-central1.run.app/ and
 *  http://localhost:8000/. Item 1 lost a round trip to this — the console has
 *  two boxes with opposite rules, and the pair went into "Authorized
 *  JavaScript origins", which rejects a trailing slash, instead of "Authorized
 *  redirect URIs", which requires the full URL. Registering the localhost one
 *  is the step that is easy to skip and shows up as a button that works in
 *  production and does nothing on a laptop. */
function redirectUri() {
  return `${location.origin}/`;
}

// Cached per page load by completeGoogleLink below.
let completion = null;

/** Runs at load, and resolves whatever the redirect brought back.
 *
 *  ORDER IS THE POINT. The fragment is read and stripped by the first two
 *  synchronous statements this function runs, before the state comparison,
 *  before the exchange, before anything can await. A fragment that survives
 *  into a reload or a bookmark is an ID token sitting in the reader's address
 *  bar, and there is no later moment where stripping it is as cheap.
 *
 *  The result is cached and the cache is the promise, not its value, so two
 *  callers on the same load share one exchange. That matters because app.js
 *  calls this to get the linked token in place before the rail is drawn, and
 *  the account surface calls it again to find out what to render. Both are
 *  reading the same event and must not be able to disagree about it. */
export function completeGoogleLink() {
  if (!completion) {
    const fragment = readAndStripFragment();
    completion = finishGoogleLink(fragment);
  }
  return completion;
}

function readAndStripFragment() {
  let raw = "";
  try {
    raw = String(location.hash || "");
  } catch {
    return "";
  }
  if (!raw) return "";
  try {
    history.replaceState(null, "", location.pathname + location.search);
  } catch {
    // The fragment is already in the address bar and refusing to continue
    // would not take it out of there — it would only cost the reader the link
    // they just authorised. Proceed, and let the exchange happen.
  }
  return raw.startsWith("#") ? raw.slice(1) : raw;
}

async function finishGoogleLink(fragment) {
  // Consumed unconditionally, whatever happens next: one stash, one attempt.
  // A fragment replayed into a second load then finds nothing to match and
  // lands on the state-missing row rather than being exchanged twice.
  const stash = readStash(LINK_KEY);
  removeStash(LINK_KEY);

  const params = new URLSearchParams(fragment);
  const googleToken = params.get("id_token");
  const googleError = params.get("error");
  const returnedState = params.get("state");
  const returnTo = safeReturnTo(stash?.returnTo);

  if (!googleToken && !googleError) {
    // No fragment at all. With a stash, that is the reader who backed out;
    // without one, it is an ordinary page load and not an event.
    return outcome(stash ? "abandoned" : "none", { returnTo });
  }
  if (googleError) {
    // access_denied is the reader declining at Google's own screen, which is
    // the same non-event as backing out. Anything else is Google telling us
    // the request was wrong, which the reader can only read as a sign-in that
    // did not come back cleanly.
    return outcome(googleError === "access_denied" ? "abandoned" : "idp-response", {
      returnTo,
    });
  }
  if (!stash || typeof stash.state !== "string" || !stash.state) {
    return outcome("state-missing", { returnTo });
  }
  if (returnedState !== stash.state) {
    return outcome("state-mismatch", { returnTo });
  }

  const anonToken = await getIdToken();
  if (!anonToken) return outcome("network", { returnTo });

  // Captured before the exchange so the abort below has something exact to put
  // back, rather than a reconstruction.
  const priorRefreshToken = safeGetStored();

  let res;
  try {
    res = await fetch(`${SIGN_IN_WITH_IDP}?key=${FIREBASE.apiKey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        postBody: `id_token=${encodeURIComponent(googleToken)}&providerId=google.com`,
        requestUri: location.origin,
        // THIS FIELD IS THE WHOLE LINKING MECHANISM. Identity Toolkit's
        // contract: "If passed, the user's account at the IdP will be linked
        // to the account represented by this ID token." Drop it and the same
        // call signs in as a brand new account instead, with a new uid and an
        // empty rail. Everything else in this request is routine.
        idToken: anonToken,
        returnSecureToken: true,
        returnIdpCredential: true,
      }),
    });
  } catch {
    return outcome("network", { returnTo });
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!data) return outcome("idp-response", { returnTo });

  const refusal = refusalFor(res, data);
  if (refusal) return { ...refusal, returnTo };

  if (!data.idToken || !data.localId) return outcome("idp-response", { returnTo });

  // THE HARD ABORT. A localId that is not the uid we left with means Identity
  // Toolkit did not link the two accounts, it signed us into a different one —
  // and persisting that token would swap the reader's rooms for someone
  // else's without either of them being told. Nothing is remembered, the prior
  // refresh token goes back exactly as it was, and the session carries on as
  // the account it already was. Item 1 measured localId coming back
  // byte-identical, so this branch is not expected to fire; it is here because
  // the cost of being wrong about that is the worst outcome in the file.
  if (data.localId !== stash.uid) {
    restoreStored(priorRefreshToken);
    return outcome("uid-mismatch", { returnTo });
  }

  // expiresIn is the string "3600" (measured). remember() coerces with
  // Number(); passing it through untouched is deliberate, not an oversight.
  remember(data.idToken, data.refreshToken, data.expiresIn, data.localId);

  return {
    status: "linked",
    reason: "linked",
    message: "",
    uid: data.localId,
    provider: data.providerId || "google.com",
    email: String(data.email || ""),
    name: String(data.fullName || data.displayName || ""),
    returnTo,
  };
}

/** Reads a refusal out of the response, whichever door it came through.
 *
 *  returnIdpCredential: true is documented to move federated refusals into a
 *  200 body under `errorMessage`, instead of an HTTP error carrying
 *  `error.message`. Item 1 only measured the SUCCESS path, so which door a
 *  refusal actually uses here is unmeasured and both are read. Saying that out
 *  loud rather than picking one: an untested assumption about an error path is
 *  how an error path becomes a blank screen.
 *
 *  A refusal with no code at all still names its status rather than falling
 *  back on a generic sentence — a reader who is told the number can act on it,
 *  and a shrug is what this table exists to avoid. */
function refusalFor(res, data) {
  const raw = String(data?.errorMessage || data?.error?.message || "").trim();
  if (!raw) {
    if (res.ok) return null;
    return {
      status: "failed",
      reason: "unknown-refusal",
      message:
        `The sign-in service refused the link with status ${res.status} and ` +
        "gave no reason. Nothing here has changed.",
    };
  }
  const code = raw.split(":")[0].trim().toUpperCase();
  const reason = REFUSAL_CODES[code];
  if (reason) return outcome(reason);
  return {
    status: "failed",
    reason: "unknown-refusal",
    message:
      `The sign-in service refused the link and named a reason this page has ` +
      `no copy for: ${code}. Nothing here has changed.`,
  };
}

/** Back to a fresh anonymous session.
 *
 *  The stored refresh token goes, the in-memory token goes, the remembered uid
 *  goes, and the epoch moves so an acquire already in flight cannot write any
 *  of it back. The next getIdToken() finds nothing to refresh and mints a new
 *  anonymous account, which is the whole implementation — there is no sign-out
 *  endpoint and there does not need to be one.
 *
 *  The surface must show signOutNotice() BEFORE calling this. Not a suggestion:
 *  this is the one control on the account surface that looks destructive, and a
 *  reader who is not told what it does will read an emptied rail as lost work. */
export function signOut() {
  sessionEpoch += 1;
  pending = null;
  idToken = null;
  expiresAt = 0;
  uid = null;
  safeRemoveStored();
  removeStash(LINK_KEY);
  removeStash(RUN_KEY);
}

/** What signing out will do, said before it happens.
 *
 *  Two sentences, because there are two truths and only one of them is gentle.
 *  A linked reader gets their rooms back by signing in again, so the honest
 *  line says so and does not dress the moment up as a loss. An anonymous
 *  reader does not: their rooms are not deleted, and nothing will ever be able
 *  to reach them again, and that is the sentence they are owed BEFORE the
 *  click rather than after it. */
export async function signOutNotice() {
  const linked = await linkedProvider();
  if (linked) {
    const who = linked.email || "the Google account attached to it";
    return (
      `Signing out empties this browser's session. Your filed rooms stay with ` +
      `${who}, and signing in with it again brings them back.`
    );
  }
  return (
    "Signing out starts a new, empty session in this browser. The rooms filed " +
    "under this browser are not deleted, but nothing will be able to reach " +
    "them again — this session has no account to sign back in to."
  );
}

// --- The live run across the redirect -------------------------------------
//
// app.js registers a getter rather than this file importing app.js, for the
// same reason shell.js takes setRoomRenderer: app.js already imports this
// module, and the reverse edge would make the pair circular.

let liveRunProvider = null;

/** Registers the function beginGoogleLink asks for the run in flight.
 *  It returns {run_id, stream_key, last_event_id} or null. */
export function setLiveRunProvider(fn) {
  liveRunProvider = typeof fn === "function" ? fn : null;
}

function stashLiveRun() {
  let run = null;
  try {
    run = liveRunProvider ? liveRunProvider() : null;
  } catch {
    run = null;
  }
  if (!run || !run.run_id || !run.stream_key) {
    removeStash(RUN_KEY);
    return;
  }
  writeStash(RUN_KEY, {
    run_id: String(run.run_id),
    stream_key: String(run.stream_key),
    last_event_id: Number.isInteger(run.last_event_id) ? run.last_event_id : null,
  });
}

/** The run that was in flight when the page left, once.
 *
 *  Removed on read whether or not it is usable: a stash that survives its own
 *  resume would try to reopen the same stream on every subsequent load, long
 *  after the run had filed. */
export function takeStashedRun() {
  const run = readStash(RUN_KEY);
  removeStash(RUN_KEY);
  if (!run || typeof run.run_id !== "string" || typeof run.stream_key !== "string") {
    return null;
  }
  return {
    run_id: run.run_id,
    stream_key: run.stream_key,
    last_event_id: Number.isInteger(run.last_event_id) ? run.last_event_id : null,
  };
}

// --- sessionStorage, guarded the way localStorage already is ---------------
//
// sessionStorage is the right store for all of this and not localStorage: it
// is scoped to the one tab and it is cleared when that tab closes, which is
// exactly the lifetime of a redirect. It survives the navigation to
// accounts.google.com and back because the tab and the origin are the same on
// both sides of the trip.

function writeStash(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

function readStash(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // Unavailable storage and a value that is not JSON are the same answer:
    // there is nothing here to trust.
    return null;
  }
}

function removeStash(key) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Already unavailable; nothing to clean up.
  }
}

function randomHex(bytes) {
  const buffer = new Uint8Array(bytes);
  crypto.getRandomValues(buffer);
  return [...buffer].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** A same-origin absolute path, or "/".
 *
 *  Anything stashed and later handed back to a caller that might navigate to
 *  it is an open redirect waiting to happen, and "//evil.example" is a path by
 *  the loosest reading and an absolute URL by the browser's. Filtered here so
 *  no caller has to remember to. */
function safeReturnTo(value) {
  let raw = typeof value === "string" && value ? value : "";
  if (!raw) {
    try {
      raw = `${location.pathname}${location.search}`;
    } catch {
      raw = "/";
    }
  }
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}
