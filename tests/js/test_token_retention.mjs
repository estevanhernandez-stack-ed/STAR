// Guards the issued token against being destroyed by something the reader did
// not do.
//
// THE BUG. The plaintext exists in exactly one place — web/account.js's module
// scope, on one render — because star/tokens.py stores only a sha256 and the
// card's own standing copy says so. Issue a token during a 146-420s build, the
// build finishes anywhere in the app, showResults calls stage(), the panel is
// switched off, and coming back through the rail ran openAccount() which
// re-read the card and discarded the credential. The remedy was revoke and
// re-issue. Nothing the reader did caused it.
//
// THE SHAPE OF THE FIX, and why it is not a weakening of "shown exactly once":
// stage() hides panels, it does not empty them, so the render carrying the
// plaintext is still intact behind the class. openAccount now declines to
// re-read while a plaintext is live. It does not render the token a second
// time — it stops destroying the first render. The reader ends that render
// themselves, through a dismiss control that clears `issued` and re-reads.
//
// The renderer half below is a real behaviour test against the stub document.
// The openAccount half is a source assertion: that function is the wiring tail,
// it awaits the network, and the stub implements no fetch.
//
// Run directly: `node tests/js/test_token_retention.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

import { ACCOUNT_PATH, loadAccountModule, stubDocument, withClass } from "./_account_module.mjs";

globalThis.document = stubDocument();
globalThis.__starAuth = {
  authedFetch: async () => {
    throw new Error("no test below should reach the network");
  },
  beginGoogleLink: async () => {
    throw new Error("no test below should leave the page");
  },
  completeGoogleLink: async () => ({ status: "none", message: "" }),
  linkedProvider: async () => null,
  linkingAvailable: () => true,
  signOut: () => {},
  signOutNotice: async () => "",
};
globalThis.__starShell = {
  refreshRail: async () => {},
  showPreviousStage: () => {
    throw new Error("no test below should change the stage");
  },
};

const { renderAccountCard } = await import(loadAccountModule());

const PLAINTEXT = "star_a1b2c3d4e5f6.0123456789abcdef0123456789abcdef";

function state(overrides = {}) {
  return {
    linkingAvailable: true,
    linked: "writer@example.com",
    linkMessage: "",
    signOutNotice: "",
    tokens: [],
    tokensUnreadable: false,
    issued: null,
    issueError: "",
    ...overrides,
  };
}

/* 1 — the dismiss control renders with the plaintext, and only with it. -- */

const withToken = renderAccountCard(state({ issued: { token: PLAINTEXT } }), {
  onDismissToken: () => {},
});
const dismiss = withClass(withToken, "token-plaintext-dismiss");
assert.equal(
  dismiss.length,
  1,
  "a card carrying a plaintext should carry exactly one way to put it away"
);
assert.equal(dismiss[0].tagName, "BUTTON", "the dismiss control should be a real button");
assert.equal(
  dismiss[0].getAttribute("type"),
  "button",
  "an untyped button inside a form submits it"
);

const withoutToken = renderAccountCard(state(), { onDismissToken: () => {} });
assert.equal(
  withClass(withoutToken, "token-plaintext-dismiss").length,
  0,
  "no plaintext, no dismiss control — there is nothing to put away"
);

/* 2 — the renderer stays pure when no handler is supplied. --------------- */

const noHandlers = renderAccountCard(state({ issued: { token: PLAINTEXT } }));
assert.equal(
  withClass(noHandlers, "token-plaintext-dismiss").length,
  0,
  "the control is handler-gated, so this function keeps performing no I/O of " +
    "its own and stays exercisable against a stubbed document"
);
// The plaintext itself must still render — the gate is on the control, not on
// the token.
assert.equal(
  withClass(noHandlers, "token-plaintext-value").length,
  1,
  "the token still renders without handlers"
);

/* 3 — pressing it calls the handler exactly once. ------------------------ */

let pressed = 0;
const pressable = renderAccountCard(state({ issued: { token: PLAINTEXT } }), {
  onDismissToken: () => {
    pressed += 1;
  },
});
withClass(pressable, "token-plaintext-dismiss")[0].dispatch("click");
assert.equal(pressed, 1, "the dismiss control should call its handler on click");

/* 4 — openAccount declines to re-read while a plaintext is live. --------- */

const source = readFileSync(ACCOUNT_PATH, "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .filter((line) => !/^\s*\/\//.test(line))
  .join("\n");

const openAccount = source.match(/export async function openAccount\(\) \{([\s\S]*?)\n\}/);
assert.ok(openAccount, "openAccount should still be an exported async function");
assert.match(
  openAccount[1],
  /if \(card && card\.issued\) return;/,
  "openAccount must not re-read a card that is still holding a plaintext — " +
    "re-reading is the only way the token can be lost, and readCard hardcodes " +
    "issued: null"
);
// Order matters: the guard has to come BEFORE the panel is emptied, or the
// render it exists to protect is destroyed on the way to protecting it.
const guardAt = openAccount[1].indexOf("if (card && card.issued) return;");
const wipeAt = openAccount[1].indexOf("panel.replaceChildren(working())");
assert.ok(guardAt > -1 && wipeAt > -1, "both lines should be present");
assert.ok(
  guardAt < wipeAt,
  "the guard must precede panel.replaceChildren — otherwise the plaintext is " +
    "wiped before the early return can decline to wipe it"
);

/* 5 — the dismiss handler clears the token, then re-reads. --------------- */

const handler = source.match(/onDismissToken\(\) \{([\s\S]*?)\n {2}\}/);
assert.ok(handler, "onDismissToken should exist in the handler table");
assert.match(
  handler[1],
  /issued: null/,
  "dismissing should clear the plaintext, so openAccount stops returning early"
);
assert.match(
  handler[1],
  /openAccount\(\)/,
  "and then re-read, so the card goes back to being the live view it is the " +
    "rest of the time rather than sitting stale for the session"
);

/* 6 — the standing promise is untouched. -------------------------------- */

assert.match(
  source,
  /const PLAINTEXT_LEGEND = "This is the only time this token is shown";/,
  "the legend still says the token is shown once, and it is still true: the " +
    "fix declines to destroy one render, it does not produce a second"
);
// \r? because this repo's working copies are CRLF on Windows, and a test that
// only matches LF passes or fails on the checkout rather than on the source.
assert.match(
  source,
  /issued: null,\r?\n {4}issueError: "",/,
  "readCard should still hardcode issued: null — a re-read genuinely has no " +
    "token to return, which is why the guard above is the whole fix"
);

console.log("test_token_retention.mjs: 15 assertions passed");
