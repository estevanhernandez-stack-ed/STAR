// Anonymous identity, no SDK.
//
// Identity Toolkit's REST endpoints do anonymous sign-up and token refresh
// directly, which keeps the browser free of a vendored library and of any
// CDN request. The refresh token lives in localStorage so a returning writer
// keeps the same uid and therefore the same rooms.
//
// The Firebase API key here is a public project identifier, not a secret.
// Security comes from the ID token the server verifies.

import { FIREBASE } from "/config.js";

const STORE_KEY = "star_refresh_token";
const SIGNUP = "https://identitytoolkit.googleapis.com/v1/accounts:signUp";
const REFRESH = "https://securetoken.googleapis.com/v1/token";

let idToken = null;
let expiresAt = 0;
// Concurrency guard: two callers arriving before the first sign-in/refresh
// resolves must not both hit the network — that would mint two anonymous
// Firebase accounts racing over which refresh token wins in localStorage,
// breaking the "same uid, same rooms on reload" promise above. Every caller
// that arrives while a request is already in flight awaits the same promise
// instead of starting its own.
let pending = null;

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
  return { idToken: data.id_token, refreshToken: data.refresh_token, expiresIn: data.expires_in };
}

function remember(token, refreshToken, expiresIn) {
  idToken = token;
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

async function acquireToken() {
  // getIdToken awaits this unguarded, so this function's contract is that
  // it never throws — every path returns a token or null. Without the
  // outer try/catch, a second storage failure inside the stale-token
  // cleanup (removeItem after getItem already threw) would escape both
  // inner catches and leave the caller with an unhandled rejection instead
  // of a null it can react to.
  try {
    const stored = safeGetStored();
    if (stored) {
      try {
        const r = await refresh(stored);
        remember(r.idToken, r.refreshToken, r.expiresIn);
        return idToken;
      } catch {
        // A stale or revoked refresh token: fall through and start fresh.
        safeRemoveStored();
      }
    }

    try {
      const fresh = await signUpAnonymously();
      remember(fresh.idToken, fresh.refreshToken, fresh.expiresIn);
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
 *  every handler in star/server.py — create_room included, ahead of the rate
 *  limiter, the daily cap, and the run itself. A 401 from this origin therefore
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
