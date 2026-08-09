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

async function acquireToken() {
  try {
    const stored = localStorage.getItem(STORE_KEY);
    if (stored) {
      const r = await refresh(stored);
      remember(r.idToken, r.refreshToken, r.expiresIn);
      return idToken;
    }
  } catch {
    // A stale or revoked refresh token: fall through and start fresh.
    localStorage.removeItem(STORE_KEY);
  }

  try {
    const fresh = await signUpAnonymously();
    remember(fresh.idToken, fresh.refreshToken, fresh.expiresIn);
    return idToken;
  } catch {
    return null;
  }
}

export async function getIdToken() {
  if (idToken && Date.now() < expiresAt) return idToken;
  if (pending) return pending;

  pending = acquireToken();
  try {
    return await pending;
  } finally {
    pending = null;
  }
}

export async function authedFetch(url, options = {}) {
  const token = await getIdToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}
