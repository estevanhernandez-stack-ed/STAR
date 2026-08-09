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
let ephemeral = false;

export function isEphemeral() {
  return ephemeral;
}

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
  if (refreshToken) localStorage.setItem(STORE_KEY, refreshToken);
}

export async function getIdToken() {
  if (idToken && Date.now() < expiresAt) return idToken;

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
    ephemeral = false;
    return idToken;
  } catch {
    ephemeral = true;
    return null;
  }
}

export async function authedFetch(url, options = {}) {
  const token = await getIdToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}
