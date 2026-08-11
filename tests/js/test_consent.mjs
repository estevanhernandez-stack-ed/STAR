// Proves web/consent.js turns an OAuth authorization request into a DOM that
// says the three things docs/spec-oauth-as.md > The consent screen requires,
// and never turns any of the six attacker-controlled query parameters into
// markup on the way.
//
// WHY THIS IS NOT CIRCULAR, which matters more here than on any other surface
// in this app. The document stub these tests run against — reused from
// tests/js/_scriptcheck_module.mjs rather than copied — implements NO
// innerHTML and NO HTML parser at all. There is no code path in it by which a
// string could become an element. On its own that would make "the payload
// rendered as text, not as an <img>" unfalsifiable, so every XSS assertion
// below is PAIRED with a source assertion: web/consent.js contains no HTML
// sink and no template literal anywhere. The stub proves the shape of the
// tree, the greps prove the tree is the only way in.
//
// The module is imported UNPATCHED, byte for byte as it ships. It has no
// imports to rewrite, and its wiring tail is guarded on `window`, which does
// not exist in Node — so importing it here reaches no DOM and starts nothing.
// The query string is parsed by the real URLSearchParams, so an attacker's
// characters are decoded by the same parser the browser would use rather than
// by a stand-in that might normalise something away.
//
// What each group is guarding, in the order they appear:
//
//   · the six parameters are read as data, and an absent one is an absence
//   · who is asking: the registered name, and the sentence saying the
//     department checked it against nothing
//   · a client_uri is linked only when its scheme is http or https, carries
//     rel="noopener noreferrer", and its label is its own href
//   · a javascript: client_uri produces no anchor at all, and is still shown
//   · what it is asking for: two scopes, two distinct blocks, and copy that
//     agrees phrase-for-phrase with star/mcp/tools.py
//   · where it will send you back: the hostname, plainly, and a loopback host
//     said in words
//   · deny is present, first, reachable, and structurally identical to approve
//   · nothing on this surface ever becomes markup, and nothing says the bare
//     word "verified" or promises a duration
//
// What this file cannot prove, and what a live browser check still has to:
// that the card is legible, that the focus ring is drawn at the measured
// ratio, that a 4000-character client name scrolls inside its own box instead
// of pushing the deny control off screen, and that the two controls compute to
// the same width. Those are measurements against a layout engine; everything
// below is a statement about a tree and a string.
//
// Run directly: `node tests/js/test_consent.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

import { elements, stubDocument, textNodes, walk, withClass } from "./_scriptcheck_module.mjs";

const REPO_ROOT = new URL("../../", import.meta.url);
const CONSENT_JS = new URL("web/consent.js", REPO_ROOT);
const CONSENT_CSS = new URL("web/consent.css", REPO_ROOT);
const CONSENT_HTML = new URL("web/consent.html", REPO_ROOT);
const TOOLS_PY = new URL("star/mcp/tools.py", REPO_ROOT);

globalThis.document = stubDocument();

const { readParams, redirectTarget, renderConsent } = await import(CONSENT_JS.href);

const XSS = "<img src=x onerror=alert(1)>";
const JS_URI = "javascript:alert(document.domain)";

/** Source with its comments removed.
 *
 *  The same helper tests/js/test_account_card.mjs and test_scriptcheck.mjs
 *  carry, for the same reason: every assertion below is about what SHIPS, not
 *  about what is explained. web/consent.js's header exists to say it contains
 *  no HTML sink; a check that punished it for saying so would push the
 *  explanation out of the file to satisfy the test. */
function stripJsComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

function stripCssComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Python source with adjacent string literals joined.
 *
 *  star/mcp/tools.py writes its prose as runs of concatenated literals, so a
 *  sentence that reads as one line to an agent is split across three in the
 *  file. Joining `" <newline> "` (and its f-prefixed form) is what lets the
 *  agreement test below compare the two surfaces' SENTENCES rather than their
 *  source formatting. */
function pythonProse(source) {
  return source.replace(/"\s*\n\s*f?"/g, "").toLowerCase();
}

/* ------------------------------------------------------------------ */

/** One request, in the shape the server renders this page with. Defaults to a
 *  well-formed one; every scenario below overrides what it is about. Pass
 *  `undefined` for a parameter to leave it out of the query string entirely. */
function request(overrides = {}) {
  return {
    client_name: "Claude Desktop",
    client_uri: "https://claude.ai/",
    redirect_host: "claude.ai",
    scope: "rooms:read rooms:write",
    state_key: "opaque-handle-9f3a",
    account: "writer@example.com",
    ...overrides,
  };
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) search.append(key, String(value));
  }
  return search.toString();
}

function render(params, handlers = noHandlers()) {
  return renderConsent(readParams(query(params)), handlers);
}

function noHandlers() {
  return { onDecide: () => assert.fail("onDecide should not have been called") };
}

function text(node) {
  return node.textContent;
}

/** Every text node's data, in document order. Positions in this list are how
 *  "verbatim" and "exactly once" are asserted. */
function orderedText(node) {
  return textNodes(node).map((n) => n.data);
}

/** Every attribute NAME in a subtree. The `on*` assertion walks this rather
 *  than the rendered string, because an event handler that got through would
 *  be an attribute and would leave no trace in textContent. */
function attributeNames(node) {
  const names = [];
  for (const found of walk(node)) {
    if (found.nodeType !== 1) continue;
    for (const key of found.attributes.keys()) names.push(key);
  }
  return names;
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

/* --- the parameters, as data ---------------------------------------- */

test("the six parameters are read off the query string as data", () => {
  const params = readParams(query(request()));
  assert.equal(params.clientName, "Claude Desktop");
  assert.equal(params.clientUri, "https://claude.ai/");
  assert.equal(params.redirectHost, "claude.ai");
  assert.deepEqual(params.scopes, ["rooms:read", "rooms:write"]);
  assert.equal(params.stateKey, "opaque-handle-9f3a");
  assert.equal(params.account, "writer@example.com");
});

test("an absent parameter is an absence, and an empty search does not throw", () => {
  const params = readParams("");
  assert.deepEqual(params, {
    clientName: "",
    clientUri: "",
    redirectHost: "",
    scopes: [],
    stateKey: "",
    account: "",
  });
  assert.deepEqual(readParams(undefined).scopes, []);
});

test("the state key is taken verbatim and a repeated scope is not printed twice", () => {
  // Never interpreted: no trim, no parse, no re-encoding. It is the server's
  // handle and this page is not the thing that decides whether it is good.
  const spaced = readParams(query(request({ state_key: "  padded-handle  " })));
  assert.equal(spaced.stateKey, "  padded-handle  ", "the handle is untouched");

  const repeated = readParams(query(request({ scope: "rooms:read rooms:read rooms:write" })));
  assert.deepEqual(repeated.scopes, ["rooms:read", "rooms:write"]);
});

/* --- 1. which client is asking -------------------------------------- */

test("the registered client name is shown, with the department's caveat beside it", () => {
  const root = render(request());
  const name = withClass(root, "consent-client-name");
  assert.equal(name.length, 1, "exactly one name on the page");
  assert.equal(text(name[0]), "Claude Desktop");

  const body = text(root);
  assert.ok(
    body.includes("That is the name this client registered for itself"),
    "the name is attributed to the client, not to the department"
  );
  assert.ok(
    body.includes("did not check it against anything"),
    "and the department says what it checked, which is nothing"
  );
  assert.ok(
    body.includes("any client can register any name"),
    "which is the fact that makes the hostname below worth reading"
  );
});

test("a request with no client name says so rather than leaving a blank", () => {
  const root = render(request({ client_name: undefined }));
  assert.equal(withClass(root, "consent-client-name").length, 0);
  assert.ok(text(root).includes("carried no client name"));
});

test("an http(s) client_uri is one anchor, safely relled, labelled with its own href", () => {
  const root = render(request());
  const links = elements(root, "a");
  assert.equal(links.length, 1, "exactly one anchor on the page");
  const link = links[0];
  assert.equal(link.getAttribute("href"), "https://claude.ai/");
  assert.equal(link.getAttribute("rel"), "noopener noreferrer");
  assert.equal(link.getAttribute("target"), "_blank");
  // What you read and what you click are the same string, deliberately.
  assert.equal(text(link), link.getAttribute("href"));
});

/* --- 2. what it is asking for --------------------------------------- */

test("both scopes produce their own distinct block and their own copy", () => {
  const both = render(request());
  const blocks = withClass(both, "consent-scope");
  assert.equal(blocks.length, 2, "one block per scope");
  assert.equal(text(withClass(blocks[0], "consent-scope-token")[0]), "rooms:read");
  assert.equal(text(withClass(blocks[1], "consent-scope-token")[0]), "rooms:write");

  const readOnly = text(render(request({ scope: "rooms:read" })));
  const writeOnly = text(render(request({ scope: "rooms:write" })));

  assert.ok(readOnly.includes("Read the rooms you have filed"));
  assert.ok(readOnly.includes("costs nothing, spends no searches, and is never rate-limited"));
  assert.ok(
    !readOnly.includes("spends real money"),
    "a read-only request must not carry the spending copy"
  );

  assert.ok(writeOnly.includes("Build new rooms, and check scenes against them"));
  assert.ok(
    writeOnly.includes("This one spends real money on live web searches"),
    "the cost is stated plainly and first"
  );
  assert.ok(writeOnly.includes("hourly ceiling on your account"));
  assert.ok(writeOnly.includes("daily budget the whole department shares"));
  assert.ok(
    !writeOnly.includes("Read the rooms you have filed"),
    "a write-only request must not claim the read grant's copy"
  );
});

test("the scope copy agrees with what star/mcp/tools.py already tells an agent", () => {
  // The two surfaces describe the same four calls to two different readers.
  // If they drift, one of them is lying to somebody: these are the phrases
  // that pin them together.
  const tools = pythonProse(readFileSync(TOOLS_PY, "utf8"));
  const body = text(render(request())).toLowerCase();
  for (const phrase of [
    "spends no searches, and is never rate-limited",
    "real money on live web searches",
    "daily budget the whole department shares",
  ]) {
    assert.ok(body.includes(phrase), `the consent screen must say "${phrase}"`);
    assert.ok(tools.includes(phrase), `star/mcp/tools.py must still say "${phrase}"`);
  }
});

test("an unrecognised scope is printed verbatim and said to be undescribed", () => {
  const root = render(request({ scope: "rooms:read rooms:destroy" }));
  const blocks = withClass(root, "consent-scope");
  assert.equal(blocks.length, 2);
  assert.equal(text(withClass(blocks[1], "consent-scope-token")[0]), "rooms:destroy");
  assert.ok(text(blocks[1]).includes("The department has no description for this one"));
  assert.ok(
    !text(blocks[1]).includes("costs nothing"),
    "an unknown scope must never inherit a known one's description"
  );
});

test("a scope named after an Object property is undescribed, not silently empty", () => {
  // `SCOPES[name]` with name="constructor" resolves up the prototype chain and
  // would render a block with a title of `undefined` and no copy — an access
  // grant shown as a blank. The lookup is guarded with hasOwnProperty.
  for (const hostile of ["constructor", "__proto__", "toString"]) {
    const root = render(request({ scope: hostile }));
    const blocks = withClass(root, "consent-scope");
    assert.equal(blocks.length, 1, `one block for ${hostile}`);
    assert.ok(
      text(blocks[0]).includes("The department has no description for this one"),
      `${hostile} must be reported as undescribed`
    );
    assert.ok(!text(blocks[0]).includes("undefined"), `${hostile} must not render "undefined"`);
  }
});

test("a request naming no scope says there is nothing to grant", () => {
  const root = render(request({ scope: undefined }));
  assert.equal(withClass(root, "consent-scope").length, 0);
  assert.ok(text(root).includes("names no access at all"));
});

/* --- 3. the redirect hostname, which is the security control -------- */

test("the redirect hostname appears in the rendered text, on its own plate", () => {
  const root = render(request({ redirect_host: "desktop-client.example.org" }));
  const host = withClass(root, "consent-host");
  assert.equal(host.length, 1, "exactly one hostname on the page");
  assert.equal(text(host[0]), "desktop-client.example.org");
  assert.ok(
    text(root).includes("desktop-client.example.org"),
    "and it is in the rendered text, not only in an attribute"
  );
  const said = text(root);
  assert.ok(said.includes("the address is where the answer actually goes"));
  assert.ok(
    said.includes("Any client can claim another client's name and its metadata"),
    "the spec's impersonation warning is stated, not summarised"
  );
});

test("a localhost redirect host is said in plain words", () => {
  for (const host of ["localhost", "127.0.0.1", "::1", "[::1]", "LocalHost", "app.localhost"]) {
    const root = render(request({ redirect_host: host }));
    const body = text(root);
    assert.equal(text(withClass(root, "consent-host")[0]), host, `${host} is shown as itself`);
    assert.ok(
      body.includes("an application running on this computer"),
      `${host} must be explained in words`
    );
    assert.ok(
      body.includes("The department cannot tell you which one"),
      `${host} must not imply the department knows which program it is`
    );
    assert.ok(
      !body.includes("the address is where the answer actually goes"),
      `${host} takes the loopback sentence instead of the general one`
    );
  }
});

test("an ordinary hostname does NOT get the loopback sentence", () => {
  const body = text(render(request({ redirect_host: "notlocalhost.example" })));
  assert.ok(!body.includes("an application running on this computer"));
  assert.ok(body.includes("the address is where the answer actually goes"));
});

test("a request with no redirect host says the missing thing is the one that mattered", () => {
  const root = render(request({ redirect_host: undefined }));
  assert.equal(withClass(root, "consent-host").length, 0);
  const said = text(root);
  assert.ok(said.includes("carried no address to send you back to"));
  assert.ok(said.includes("it is the thing that is missing"));
});

/* --- the account being answered as ---------------------------------- */

test("the signed-in account is named, and its absence is named too", () => {
  assert.ok(text(render(request())).includes("You are answering as writer@example.com."));
  const blind = text(render(request({ account: undefined })));
  assert.ok(blind.includes("was not told which account you are signed in as"));
  assert.ok(!blind.includes("You are answering as"));
});

/* --- deny is as easy to reach as approve ---------------------------- */

test("deny is present, first, and structurally identical to approve", () => {
  const root = render(request());
  const buttons = withClass(root, "decide-btn");
  assert.equal(buttons.length, 2, "two controls, no third");

  assert.equal(buttons[0].getAttribute("data-decision"), "deny");
  assert.equal(buttons[1].getAttribute("data-decision"), "approve");
  assert.equal(text(buttons[0]), "Deny this request");
  assert.equal(text(buttons[1]), "Approve this request");

  for (const button of buttons) {
    assert.equal(button.nodeName, "BUTTON", "a real button, reachable by keyboard");
    assert.equal(button.getAttribute("type"), "button");
  }

  // The same class on both is what makes "neither outranks the other" a
  // property of the stylesheet rather than a promise: no rule can paint one
  // differently without naming the data attribute, which web/consent.css does
  // not do (asserted below).
  assert.equal(
    buttons[0].getAttribute("class"),
    buttons[1].getAttribute("class"),
    "both controls carry the same class"
  );

  const order = walk(root);
  assert.ok(
    order.indexOf(buttons[0]) < order.indexOf(buttons[1]),
    "deny comes first in document order, and so in tab order"
  );
});

test("web/consent.css cannot tell the two controls apart", () => {
  const css = stripCssComments(readFileSync(CONSENT_CSS, "utf8"));
  assert.ok(
    !css.includes("[data-decision"),
    "a rule naming data-decision would let one control outshout the other"
  );
  assert.ok(css.includes(".decide-btn"), "and the shared rule is the one that paints them");
});

test("pressing deny reports deny, and pressing approve reports approve", () => {
  for (const decision of ["deny", "approve"]) {
    const calls = [];
    const root = render(request(), { onDecide: (value) => calls.push(value) });
    const button = withClass(root, "decide-btn").find(
      (node) => node.getAttribute("data-decision") === decision
    );
    button.dispatch("click");
    assert.deepEqual(calls, [decision]);
  }
});

test("an answer in flight disables both controls, and a refusal brings them back", () => {
  let controls = null;
  const root = render(request(), { onDecide: (_decision, given) => (controls = given) });
  const buttons = withClass(root, "decide-btn");
  const status = withClass(root, "consent-status")[0];

  buttons[0].dispatch("click");
  assert.equal(buttons[0].disabled, true, "the pressed control goes down");
  assert.equal(buttons[1].disabled, true, "and so does the other one");
  assert.ok(text(status).includes("Sending your answer"), "and the page says what it is doing");

  controls.fail("The department could not be reached.");
  assert.equal(buttons[0].disabled, false, "both come back");
  assert.equal(buttons[1].disabled, false);
  assert.equal(text(status), "", "the working line is cleared");
  assert.ok(
    text(root).includes("The department could not be reached."),
    "and the refusal is rendered in the department's own words"
  );
});

test("with no state key there is nothing to press, and the page says why", () => {
  const root = render(request({ state_key: undefined }));
  assert.equal(withClass(root, "decide-btn").length, 0, "no dead controls");
  assert.equal(elements(root, "button").length, 0, "no controls of any kind");
  const said = text(root);
  assert.ok(said.includes("without the handle the department needs to record an answer"));
  assert.ok(said.includes("Nothing has been granted."));
  assert.ok(said.includes("Start the connection again from the client that sent you."));
});

test("the page never navigates to a target that is not http or https", () => {
  assert.equal(redirectTarget({ redirect_to: JS_URI }), "");
  assert.equal(redirectTarget({ redirect_to: "data:text/html,<script>1</script>" }), "");
  assert.equal(redirectTarget({}), "");
  assert.equal(redirectTarget(null), "");
  assert.equal(
    redirectTarget({ redirect_to: "https://claude.ai/callback?code=abc" }),
    "https://claude.ai/callback?code=abc"
  );
  // The endpoint's response shape is not pinned anywhere in the repo yet, so
  // four plausible names are accepted rather than one guessed at.
  for (const key of ["redirect_uri", "location", "redirect"]) {
    assert.equal(redirectTarget({ [key]: "http://127.0.0.1:41999/cb" }), "http://127.0.0.1:41999/cb");
  }
});

/* --- nothing here ever becomes markup ------------------------------- */

test("a hostile client_name reaches the DOM as those exact characters", () => {
  const root = render(request({ client_name: XSS }));

  assert.equal(elements(root, "img").length, 0, "no IMG anywhere in the tree");
  assert.equal(elements(root, "script").length, 0, "no SCRIPT anywhere in the tree");

  const handlers = attributeNames(root).filter((name) => /^on/i.test(name));
  assert.deepEqual(handlers, [], "no on* attribute anywhere in the tree");

  const exact = orderedText(root).filter((data) => data === XSS);
  assert.equal(exact.length, 1, "the payload is one text node, verbatim");
  assert.equal(text(withClass(root, "consent-client-name")[0]), XSS);
});

test("every other parameter survives the same payload as characters", () => {
  // The name is the obvious one. These are the four that would be missed.
  for (const key of ["account", "redirect_host", "scope", "client_uri"]) {
    const root = render(request({ [key]: XSS }));
    assert.equal(elements(root, "img").length, 0, `no IMG from ${key}`);
    assert.deepEqual(
      attributeNames(root).filter((name) => /^on/i.test(name)),
      [],
      `no on* attribute from ${key}`
    );
    // Compared against the whole rendered string rather than one node: a
    // scope list is split on whitespace, so this payload lands as three
    // separate tokens in three blocks. What is being proved is that the
    // characters reach the reader and stay characters, not where they land.
    assert.ok(text(root).includes("<img"), `${key} still reaches the reader, as characters`);
  }
});

test("a javascript: client_uri produces no anchor, and is still shown inert", () => {
  const root = render(request({ client_uri: JS_URI }));
  assert.equal(elements(root, "a").length, 0, "nothing on this page links it");
  const said = text(root);
  assert.ok(said.includes("will not turn into a link"), "and the page says why");
  assert.ok(said.includes("nothing on this page opens it"));
  const shown = orderedText(root).filter((data) => data === JS_URI);
  assert.equal(shown.length, 1, "it is printed exactly as it arrived, once");
});

test("every other refused scheme is refused the same way", () => {
  for (const hostile of [
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "JaVaScRiPt:alert(1)",
    "not a url at all",
  ]) {
    const root = render(request({ client_uri: hostile }));
    assert.equal(elements(root, "a").length, 0, `${hostile} must not become an anchor`);
  }
});

test("web/consent.js contains no way to turn a string into markup", () => {
  const source = stripJsComments(readFileSync(CONSENT_JS, "utf8"));
  for (const sink of [
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "createContextualFragment",
    "DOMParser",
  ]) {
    assert.ok(!source.includes(sink), `web/consent.js must not use ${sink}`);
  }
  // No template literal either. Not because a template string is a sink on its
  // own, but because "no string in this module is ever assembled for markup"
  // is a property a reviewer can check with one grep, and a backtick is where
  // that grep would have to start making judgements.
  assert.ok(!source.includes("`"), "web/consent.js must contain no template literal");
  assert.ok(
    source.includes("document.createTextNode"),
    "and every string that reaches the DOM goes through createTextNode"
  );
});

test("the page makes no third-party request and carries nothing inline", () => {
  const html = readFileSync(CONSENT_HTML, "utf8");
  const css = readFileSync(CONSENT_CSS, "utf8");
  const js = stripJsComments(readFileSync(CONSENT_JS, "utf8"));

  // The rule is not "no external origin", it is the app-wide one: zero
  // third-party requests EXCEPT Google's identity endpoints, which is the
  // exception `docs/scope.md` has always carried and the only one it carries.
  // This page reaches them because a decision has to be signed as somebody and
  // finding out who is a call to Firebase.
  //
  // Asserted as an exact allow-list rather than as an absence, so adding a
  // third host fails here. An assertion that no external origin appears at all
  // would have been the stricter-sounding rule and the weaker one: it was true
  // of this page only while the page could not establish an identity, and
  // deleting it to make the flow work would have removed the guard entirely.
  const ALLOWED_ORIGINS = new Set([
    "https://identitytoolkit.googleapis.com",
    "https://securetoken.googleapis.com",
  ]);
  for (const [name, source] of [
    ["web/consent.html", html],
    ["web/consent.css", css],
    ["web/consent.js", js],
  ]) {
    for (const [, origin] of source.matchAll(/(https?:\/\/[^\s"';)]+)/gi)) {
      const root = new URL(origin).origin;
      assert.ok(
        ALLOWED_ORIGINS.has(root),
        `${name} references ${root}, which is not one of Google's identity endpoints`
      );
    }
  }

  // And the two that are allowed appear where they can only be reached by
  // fetch, never as a subresource this document loads.
  assert.ok(
    /connect-src[^;]*identitytoolkit\.googleapis\.com/.test(html),
    "the identity hosts belong in connect-src and nowhere else"
  );

  // Every subresource is an absolute same-origin path.
  const hrefs = [...html.matchAll(/href="([^"]*)"/g)].map((m) => m[1]);
  const srcs = [...html.matchAll(/src="([^"]*)"/g)].map((m) => m[1]);
  assert.ok(hrefs.length > 0 && srcs.length > 0, "the page loads its own styles and module");
  for (const url of [...hrefs, ...srcs]) {
    assert.ok(url.startsWith("/"), `${url} must be an absolute same-origin path`);
  }

  // No inline script and no inline style. The one <script> is the module.
  assert.equal((html.match(/<script/g) || []).length, 1);
  assert.ok(/<script type="module" src="\/consent\.js"><\/script>/.test(html));
  assert.ok(!/<style/.test(html), "no inline style block");
  assert.ok(!/\sstyle="/.test(html), "no inline style attribute");
});

/* --- copy discipline ------------------------------------------------ */

test('no copy on this surface says the bare word "verified"', () => {
  const surfaces = [
    request(),
    request({ scope: "rooms:read" }),
    request({ scope: "rooms:write" }),
    request({ scope: "rooms:unknown" }),
    request({ scope: undefined }),
    request({ redirect_host: "localhost" }),
    request({ redirect_host: undefined }),
    request({ client_name: undefined, client_uri: JS_URI }),
    request({ state_key: undefined, account: undefined }),
  ];
  for (const surface of surfaces) {
    const body = text(render(surface));
    assert.ok(!/verified/i.test(body), `"verified" reached the page: ${body.slice(0, 160)}`);
  }
});

test("the page promises no duration and no expiry", () => {
  // "Hourly ceiling" is deliberately allowed and is not a duration promise:
  // it is the window a rate limit is counted over, and it is the word
  // star/mcp/tools.py already uses for the same limit. What obligation 6
  // forbids is telling a reader how long something will take or last, and
  // docs/spec-oauth-as.md's third open question is explicit that nothing has
  // measured a token lifetime yet.
  const body = text(render(request())).toLowerCase();
  for (const phrase of ["minute", "seconds", "expire", "how long", "for an hour", "lasts for"]) {
    assert.ok(!body.includes(phrase), `"${phrase}" is a duration promise`);
  }
});

test("the reader is told nothing has been granted before they answer", () => {
  const body = text(render(request()));
  assert.ok(body.includes("Nothing has been granted yet."));
  assert.ok(body.includes("Denying grants nothing"));
  assert.ok(
    body.includes("Either answer sends you back to the client"),
    "and that both answers return them to the client"
  );
});

/* ------------------------------------------------------------------ */

/* --- an unattached session cannot approve --------------------------- */
/** `renderConsent` reads `linked` off the params object, and `readParams` does
 *  not produce it: the page discovers it from the reader's own ID token after
 *  the first paint. So these build the params directly rather than through a
 *  query string, which is the shape `start()` actually hands the renderer. */
function session(account, linked, overrides = {}) {
  return { ...readParams(query(request(overrides))), account, linked };
}
test("an unattached session cannot approve, and is told why", () => {
  const root = renderConsent(session("this browser's anonymous session", false), noHandlers());
  const buttons = withClass(root, "decide-btn").filter(
    (b) => b.getAttribute("data-decision")
  );
  const approve = buttons.find((b) => b.getAttribute("data-decision") === "approve");
  const deny = buttons.find((b) => b.getAttribute("data-decision") === "deny");
  assert.equal(approve.disabled, true, "approve is blocked");
  assert.notEqual(deny.disabled, true, "deny is never blocked");
  // Disabled AND explained. A control that is greyed out and silent tells a
  // reader they are stuck without telling them what is missing.
  const why = text(root);
  assert.match(why, /not attached to an account/i);
  assert.match(why, /nobody can recover/i, "says what approving anyway would cost");
  assert.equal(
    approve.getAttribute("aria-describedby"),
    "consent-why-blocked",
    "the reason is wired to the control for a screen reader too"
  );
});
test("a linked session may approve", () => {
  const root = renderConsent(session("writer@example.com", true), noHandlers());
  const approve = withClass(root, "decide-btn").find(
    (b) => b.getAttribute("data-decision") === "approve"
  );
  assert.notEqual(approve.disabled, true);
  assert.doesNotMatch(text(root), /not attached to an account/i);
});
test("the way out is offered beside the refusal, not instead of it", () => {
  let attached = 0;
  const root = renderConsent(session("this browser's anonymous session", false), {
    ...noHandlers(),
    onAttach: () => {
      attached += 1;
    },
  });
  const attach = withClass(root, "consent-attach")[0];
  assert.ok(attach, "an unattached reader is given something to press");
  assert.equal(attach.nodeName, "BUTTON");
  assert.match(text(attach), /attach a google account/i);
  attach.dispatch("click");
  assert.equal(attached, 1, "pressing it starts the link");
  // And the refusal is still on screen. Replacing the reason with the remedy
  // would leave a reader who declines the sign-in with no idea what happened.
  assert.match(text(root), /not attached to an account/i);
});
test("an unattached reader with no attach handler is refused, not stranded silently", () => {
  const root = renderConsent(session("this browser's anonymous session", false), noHandlers());
  assert.equal(withClass(root, "consent-attach").length, 0, "no control that cannot work");
  assert.match(text(root), /not attached to an account/i, "the reason survives anyway");
});

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
