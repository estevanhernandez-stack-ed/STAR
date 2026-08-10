// Proves web/account.js turns the card's state into a DOM that keeps the five
// promises prd.md > Identity That Outlives The Browser makes about it, and
// never turns a string into markup on the way.
//
// What each scenario is guarding, in the order they appear:
//
//   · an unattached card shows the absence, the one-line offer, and — before
//     the link — that a linked account is readable from any browser and by any
//     agent holding a token. That sentence is the one the intake CUT rather
//     than softened, so if it is not here it is nowhere
//   · the issue control is disabled while unattached WITH THE REASON STATED,
//     wired to the control by aria-describedby rather than left as a grey box
//   · the plaintext appears exactly once, and the sentence announcing that it
//     will only ever appear once is already above it in document order
//   · the list is metadata only: a payload carrying a secret and a hash renders
//     neither, because the renderer names the fields it draws
//   · one revoke control per live token, two presses, and the first press says
//     what the second will do
//   · sign-out shows web/auth.js's signOutNotice() BEFORE signOut() is called,
//     which that function's own docstring makes a requirement
//   · a token label is reader-supplied text and reaches the DOM as characters
//   · no copy anywhere on this surface says the bare word "verified"
//
// What this file cannot prove, and what the live browser checkpoint still has
// to: that the card is legible, that the focus ring is drawn, that the issue
// row stacks below 900px, and what share of the room's pixels are manila.
// Those are measurements against a layout engine; everything below is a
// statement about a tree and a string.
//
// Run directly: `node tests/js/test_account_card.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

import {
  elements,
  loadAccountModule,
  readAccountSource,
  stubDocument,
  textNodes,
  walk,
  withClass,
} from "./_account_module.mjs";

/** Source with its comments removed.
 *
 *  The same helper tests/js/test_scriptcheck.mjs carries, for the same reason:
 *  both assertions below are about what SHIPS, not about what is explained.
 *  web/account.js's header exists to say it contains no innerHTML and that no
 *  reader-visible copy says "verified"; a check that punished it for saying so
 *  would push the explanation out of the file to satisfy the test. */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

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
globalThis.__starShell = { refreshRail: async () => {} };

const { renderAccountCard } = await import(loadAccountModule());

const XSS = "<img src=x onerror=alert(1)>";
const PLAINTEXT = "star_a1b2c3d4e5f6.0123456789abcdef0123456789abcdef";

const ANON_NOTICE =
  "Signing out starts a new, empty session in this browser. The rooms filed " +
  "under this browser are not deleted, but nothing will be able to reach them " +
  "again — this session has no account to sign back in to.";
const LINKED_NOTICE =
  "Signing out empties this browser's session. Your filed rooms stay with " +
  "writer@example.com, and signing in with it again brings them back.";

/** The state web/account.js's readCard() assembles, in the shape it assembles
 *  it. Defaults to the card a first-time reader meets: no account, linking
 *  offered, nothing issued. */
function state(overrides = {}) {
  return {
    linkingAvailable: true,
    linked: null,
    linkMessage: "",
    signOutNotice: ANON_NOTICE,
    tokens: [],
    tokensUnreadable: false,
    issued: null,
    issueError: "",
    ...overrides,
  };
}

/** One row of GET /api/tokens, in star/models.py's McpToken shape. */
function token(overrides = {}) {
  return {
    token_id: "a1b2c3d4e5f6",
    label: "desktop agent",
    created_at: "2026-08-14T09:12:00+00:00",
    last_used_at: "2026-08-19T17:40:00+00:00",
    revoked_at: null,
    ...overrides,
  };
}

function noHandlers() {
  return {
    onLink: () => assert.fail("onLink should not have been called"),
    onSignOut: () => assert.fail("onSignOut should not have been called"),
    onIssue: () => assert.fail("onIssue should not have been called"),
    onRevoke: () => assert.fail("onRevoke should not have been called"),
  };
}

function text(node) {
  return node.textContent;
}

/** Every text node's data, in document order. Positions in this list are how
 *  "before" and "after" are asserted, because the requirement on the plaintext
 *  and on the sign-out notice is an ORDER, not a presence. */
function orderedText(node) {
  return textNodes(node).map((n) => n.data);
}

function indexOfText(node, needle) {
  return orderedText(node).findIndex((data) => data.includes(needle));
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

/* ------------------------------------------------------------------ */

test("an unattached card names the absence, the offer, and what the link buys", () => {
  const root = renderAccountCard(state(), noHandlers());
  const body = text(root);

  assert.ok(body.includes("Not attached to an account."), "the absence is stated");
  assert.ok(
    body.includes("Your rooms live with this browser. Attach a Google account"),
    "the one-line offer says what linking buys"
  );

  const reach = withClass(root, "account-reach");
  assert.equal(reach.length, 1, "exactly one before-the-link reach notice");
  const said = text(reach[0]);
  assert.ok(
    said.includes("readable from any browser you sign in to with that account"),
    "the reach notice names any browser"
  );
  assert.ok(
    said.includes("any agent holding a token you issue"),
    "the reach notice names any agent holding a token"
  );

  const link = withClass(root, "account-link-btn");
  assert.equal(link.length, 1, "one link control");
  assert.equal(link[0].nodeName, "BUTTON");
  assert.equal(link[0].getAttribute("type"), "button");
});

test("the reach notice sits ABOVE the link control, not below it", () => {
  // Compared as NODES rather than as strings: "Attach a Google account" is
  // both the control's label and the tail of the one-line offer above it, so a
  // text search finds the offer and proves nothing about the button.
  const root = renderAccountCard(state(), noHandlers());
  const order = walk(root);
  const reachAt = order.indexOf(withClass(root, "account-reach")[0]);
  const actionAt = order.indexOf(withClass(root, "account-link-btn")[0]);
  assert.ok(reachAt >= 0 && actionAt >= 0);
  assert.ok(
    reachAt < actionAt,
    `the reach notice must precede the control (${reachAt} vs ${actionAt})`
  );
});

test("with linking unavailable the card says so and offers no control", () => {
  const root = renderAccountCard(state({ linkingAvailable: false }), noHandlers());
  assert.ok(
    text(root).includes("Attaching an account is not available on this deployment"),
    "the unavailable state is stated plainly"
  );
  assert.ok(
    text(root).includes("Everything else here works exactly as it does now"),
    "and it says every other path still works"
  );
  assert.equal(withClass(root, "account-link-btn").length, 0, "no dead control");
});

test("a linked card shows the address and drops the offer", () => {
  const root = renderAccountCard(
    state({ linked: { provider: "google.com", email: "writer@example.com", name: "A Writer" } }),
    noHandlers()
  );
  const body = text(root);
  assert.ok(body.includes("Attached to writer@example.com."), "the address is shown");
  assert.ok(
    !body.includes("Your rooms live with this browser."),
    "the unattached offer is gone"
  );
  assert.equal(withClass(root, "account-link-btn").length, 0, "no link control");
  assert.ok(
    body.includes("readable from any browser you sign in to with this account"),
    "the reach is restated after the link too"
  );
});

/* --- the issue control, and the reason it is refused ---------------- */

test("the issue control is disabled while unattached, with the reason stated", () => {
  const root = renderAccountCard(state(), noHandlers());
  const button = withClass(root, "token-issue-btn")[0];
  assert.ok(button, "the control exists");
  assert.equal(button.disabled, true, "and is disabled");

  const described = button.getAttribute("aria-describedby");
  assert.equal(described, "token-issue-blocked", "wired to its reason");

  const reason = walk(root).find(
    (n) => n.nodeType === 1 && n.getAttribute("id") === "token-issue-blocked"
  );
  assert.ok(reason, "the reason is a node on the page, not just a grey button");
  const said = text(reason);
  assert.ok(said.includes("this session has no account attached"), "names the state");
  assert.ok(
    said.includes("a key to rooms nobody could ever sign back in to"),
    "names WHY, in the same argument star/server.py's 403 makes"
  );
  assert.ok(said.includes("Attach an account above first"), "names what to do next");

  const input = withClass(root, "token-issue-input")[0];
  assert.equal(input.disabled, true, "the field is disabled with it");
});

test("the issue control is live once linked, and hands over the typed label", () => {
  const calls = [];
  const root = renderAccountCard(
    state({ linked: { provider: "google.com", email: "writer@example.com" } }),
    { ...noHandlers(), onIssue: (label) => calls.push(label) }
  );
  const button = withClass(root, "token-issue-btn")[0];
  assert.equal(button.disabled, false, "not disabled");
  assert.equal(button.getAttribute("aria-describedby"), null, "no reason to describe");
  assert.equal(
    walk(root).filter((n) => n.nodeType === 1 && n.getAttribute("id") === "token-issue-blocked")
      .length,
    0,
    "and the blocked sentence is gone with it"
  );

  const input = withClass(root, "token-issue-input")[0];
  input.value = "desktop agent";
  button.dispatch("click");
  assert.deepEqual(calls, ["desktop agent"]);
});

/* --- the plaintext, exactly once, announced first ------------------- */

test("the plaintext renders exactly once", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "writer@example.com" },
      issued: { token: PLAINTEXT, token_id: "a1b2c3d4e5f6", label: "desktop agent" },
      tokens: [token()],
    }),
    { ...noHandlers(), onRevoke: () => {} }
  );

  const hits = orderedText(root).filter((data) => data.includes(PLAINTEXT));
  assert.equal(hits.length, 1, `the plaintext must appear once, found ${hits.length}`);

  const value = withClass(root, "token-plaintext-value");
  assert.equal(value.length, 1);
  assert.equal(value[0].nodeName, "CODE");
  assert.equal(text(value[0]), PLAINTEXT);
});

test("the announcement that it is shown once precedes the plaintext", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "writer@example.com" },
      issued: { token: PLAINTEXT, token_id: "a1b2c3d4e5f6", label: "" },
    }),
    noHandlers()
  );
  const warnedAt = indexOfText(root, "shown once, on this screen");
  const shownAt = indexOfText(root, PLAINTEXT);
  assert.ok(warnedAt >= 0, "the announcement is on the page");
  assert.ok(shownAt >= 0, "the plaintext is on the page");
  assert.ok(
    warnedAt < shownAt,
    `the warning must come first (${warnedAt} vs ${shownAt})`
  );
  assert.ok(
    text(root).includes("cannot be shown again or recovered later"),
    "and it says the department cannot show it again"
  );
});

test("the announcement stands even when nothing has been issued", () => {
  // The requirement is "the surface says so BEFORE issuing", so the sentence
  // has to be standing copy rather than something that arrives with the token.
  const root = renderAccountCard(state(), noHandlers());
  assert.ok(indexOfText(root, "shown once, on this screen") >= 0);
  assert.equal(withClass(root, "token-plaintext").length, 0, "and no plaintext yet");
});

/* --- the list is metadata, and nothing else ------------------------- */

test("a token renders as metadata only — no secret, no hash, no plaintext", () => {
  const leaky = token({
    secret: "SECRET-MUST-NEVER-RENDER",
    secret_sha256: "HASH-MUST-NEVER-RENDER",
    token: "star_leaked.leaked",
    uid: "uid-must-never-render",
  });
  const root = renderAccountCard(
    state({ linked: { provider: "google.com", email: "w@example.com" }, tokens: [leaky] }),
    { ...noHandlers(), onRevoke: () => {} }
  );
  const body = text(root);

  for (const forbidden of [
    "SECRET-MUST-NEVER-RENDER",
    "HASH-MUST-NEVER-RENDER",
    "star_leaked.leaked",
    "uid-must-never-render",
  ]) {
    assert.ok(!body.includes(forbidden), `${forbidden} must not reach the card`);
  }

  assert.ok(body.includes("desktop agent"), "the label is shown");
  assert.ok(body.includes("ISSUED 14 AUG 2026"), "the issue date is shown");
  assert.ok(body.includes("LAST USED 19 AUG 2026"), "the last-used date is shown");
  assert.ok(body.includes("a1b2c3d4e5f6"), "the token id is shown");
});

test("a token that has never been used says so rather than leaving a blank", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      tokens: [token({ last_used_at: null })],
    }),
    { ...noHandlers(), onRevoke: () => {} }
  );
  assert.ok(text(root).includes("NEVER USED"));
});

test("an unnamed token is a truthful blank, not an invented name", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      tokens: [token({ label: "" })],
    }),
    { ...noHandlers(), onRevoke: () => {} }
  );
  const label = withClass(root, "token-label-blank");
  assert.equal(label.length, 1);
  assert.equal(text(label[0]), "Unnamed token");
});

test("an empty list and an unreadable list are different sentences", () => {
  const empty = text(
    renderAccountCard(
      state({ linked: { provider: "google.com", email: "w@example.com" } }),
      noHandlers()
    )
  );
  const broken = text(
    renderAccountCard(
      state({
        linked: { provider: "google.com", email: "w@example.com" },
        tokensUnreadable: true,
      }),
      noHandlers()
    )
  );
  assert.ok(empty.includes("No tokens have been issued from this account."));
  assert.ok(!empty.includes("could not be reached"));
  assert.ok(broken.includes("could not be reached just now"));
  assert.ok(broken.includes("They are not gone"));
  assert.ok(
    !broken.includes("No tokens have been issued"),
    "an unreadable list must never assert an empty account"
  );
});

/* --- revoke, per token --------------------------------------------- */

test("every live token carries its own revoke control", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      tokens: [token(), token({ token_id: "ffeeddccbbaa", label: "laptop agent" })],
    }),
    { ...noHandlers(), onRevoke: () => {} }
  );
  assert.equal(withClass(root, "token-revoke-btn").length, 2);
});

test("revoke arms first and says what the second press does", () => {
  const calls = [];
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      tokens: [token()],
    }),
    { ...noHandlers(), onRevoke: (id) => calls.push(id) }
  );
  const button = withClass(root, "token-revoke-btn")[0];
  const notice = withClass(root, "token-revoke-btn-notice")[0];

  assert.equal(text(notice), "", "nothing said until it is armed");
  button.dispatch("click");
  assert.deepEqual(calls, [], "the first press revokes nothing");
  assert.equal(button.getAttribute("data-armed"), "true");
  assert.ok(
    text(notice).includes("Revoking is immediate and cannot be undone"),
    "and it says what the next press will do"
  );
  assert.ok(
    text(notice).includes("stops being able to read your rooms"),
    "in terms of what the reader loses"
  );

  button.dispatch("click");
  assert.deepEqual(calls, ["a1b2c3d4e5f6"], "the second press revokes, by id");
  assert.equal(button.disabled, true, "and cannot be pressed a third time");
});

test("a revoked token stays on the card, stamped, with no revoke control", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      tokens: [token({ revoked_at: "2026-08-20T11:00:00+00:00" })],
    }),
    noHandlers()
  );
  const body = text(root);
  assert.ok(body.includes("desktop agent"), "it is still listed");
  assert.ok(body.includes("Revoked"), "and stamped");
  assert.ok(body.includes("REVOKED 20 AUG 2026"), "with the day it stopped working");
  assert.equal(withClass(root, "token-revoke-btn").length, 0, "nothing left to revoke");
});

/* --- sign-out says what it will do, before it does it --------------- */

test("sign-out shows the notice before signOut is called", () => {
  const calls = [];
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "writer@example.com" },
      signOutNotice: LINKED_NOTICE,
    }),
    { ...noHandlers(), onSignOut: () => calls.push("out") }
  );
  const button = withClass(root, "account-signout-btn")[0];
  const notice = withClass(root, "account-signout-btn-notice")[0];

  assert.equal(text(notice), "");
  button.dispatch("click");
  assert.deepEqual(calls, [], "the first press signs nobody out");
  assert.equal(text(notice), LINKED_NOTICE, "web/auth.js's own sentence, verbatim");

  button.dispatch("click");
  assert.deepEqual(calls, ["out"], "the second press does it");
});

test("the anonymous sign-out notice is the harsher one, and is still shown first", () => {
  const calls = [];
  const root = renderAccountCard(state({ signOutNotice: ANON_NOTICE }), {
    ...noHandlers(),
    onSignOut: () => calls.push("out"),
  });
  const button = withClass(root, "account-signout-btn")[0];
  button.dispatch("click");
  assert.deepEqual(calls, []);
  assert.equal(text(withClass(root, "account-signout-btn-notice")[0]), ANON_NOTICE);
  assert.ok(ANON_NOTICE.includes("nothing will be able to reach them again"));
});

/* --- a refusal from the redirect, in web/auth.js's own words -------- */

test("a link refusal is rendered as itself and nothing generic is invented", () => {
  const message =
    "This Google account is already attached to a different set of rooms. " +
    "You can sign in as that account instead, but the rooms on screen now " +
    "would not come along. Nothing here has changed.";
  const root = renderAccountCard(state({ linkMessage: message }), noHandlers());
  const refusal = withClass(root, "account-refusal");
  assert.equal(refusal.length, 1);
  assert.equal(text(refusal[0]), message);
});

/* --- nothing here ever becomes markup ------------------------------ */

test("a token label reaches the DOM as characters, never as an element", () => {
  const root = renderAccountCard(
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      tokens: [token({ label: XSS })],
    }),
    { ...noHandlers(), onRevoke: () => {} }
  );
  assert.equal(elements(root, "img").length, 0, "no IMG anywhere in the tree");
  const exact = orderedText(root).filter((data) => data === XSS);
  assert.equal(exact.length, 1, "the payload is one text node, verbatim");
});

test("web/account.js contains no way to turn a string into markup", () => {
  const source = stripComments(readAccountSource());
  for (const sink of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"]) {
    assert.ok(!source.includes(sink), `web/account.js must not use ${sink}`);
  }
});

/* --- copy discipline ----------------------------------------------- */

test('no copy on this surface says the bare word "verified"', () => {
  const surfaces = [
    state(),
    state({ linkingAvailable: false }),
    state({ linked: { provider: "google.com", email: "w@example.com" } }),
    state({ tokensUnreadable: true }),
    state({ linkMessage: "a refusal" }),
    state({
      linked: { provider: "google.com", email: "w@example.com" },
      issued: { token: PLAINTEXT, token_id: "a1b2c3d4e5f6", label: "x" },
      tokens: [token(), token({ token_id: "ffeeddccbbaa", revoked_at: "2026-08-20T11:00:00+00:00" })],
    }),
  ];
  for (const s of surfaces) {
    const body = text(renderAccountCard(s, { ...noHandlers(), onRevoke: () => {} }));
    assert.ok(
      !/verified/i.test(body),
      `"verified" reached the card: ${body.slice(0, 200)}`
    );
  }
});

test("the card promises no duration and no ETA", () => {
  const body = text(
    renderAccountCard(
      state({ linked: { provider: "google.com", email: "w@example.com" }, tokens: [token()] }),
      { ...noHandlers(), onRevoke: () => {} }
    )
  );
  for (const phrase of ["minute", "second", "expires in", "about a"]) {
    assert.ok(!body.toLowerCase().includes(phrase), `"${phrase}" is a duration promise`);
  }
});

/* ------------------------------------------------------------------ */

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`FAIL  ${name}\n      ${err.message}`);
  }
}
console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed === 0 ? 0 : 1);
