/* THE MORGUE — the counter: a request to reach your rooms.

   The endpoint of an OAuth redirect. Somebody the department has never met
   has sent a reader here to ask for their drawers, and this page is the
   counter clerk: it says who is asking, what they are asking for, and where
   the department will send the answer, and then it takes one word back.

   THE ONE RULE THIS FILE EXISTS TO KEEP, and it is stricter here than
   anywhere else in the app. NOTHING in this module ever becomes markup. No
   innerHTML, no insertAdjacentHTML, no template string, no escaping function
   — because there is nothing to escape when every string becomes a text node.
   web/scriptcheck.js and web/account.js already hold that line for a pasted
   scene and a reader's own token label; this file holds it for values that
   arrive in the query string from a client nobody vetted.

   Read the threat plainly, because it is the reason this page exists at all:
   `client_name` and `client_uri` are chosen by whoever registered the client,
   and this is the one screen in the app where a human presses a control that
   hands something away. It is strictly more attractive to an attacker than
   any other surface here. Assembling an HTML string around either value would
   reopen the H1 XSS through the most valuable door in the building. A
   `<img src=x onerror=...>` in a client name arrives as characters, passes
   through this module as characters, and lands in the DOM as one text node.

   WHAT THIS PAGE SAYS, and why the third one is a security control rather
   than a courtesy (docs/spec-oauth-as.md > The consent screen):

     1. Which client is asking, by the name it registered — and, next to it,
        that the department checked that name against nothing.
     2. What it is asking for, in the language star/mcp/tools.py already uses
        with an agent. `rooms:read` costs nothing. `rooms:write` spends real
        money on live web searches, against an hourly ceiling and a daily
        budget the whole department shares. Said plainly and not softened;
        tests/js/test_consent.mjs pins two of those phrases to tools.py so the
        two surfaces cannot drift apart.
     3. The redirect URI's hostname. Any client can claim another client's
        metadata URL and bind to a loopback port, at which point the reader is
        looking at the LEGITIMATE client's name. The hostname is the only
        thing that tells the two apart, so it is shown rather than summarised,
        and a loopback host is said in words rather than left as `127.0.0.1`.

   DENY IS AS EASY TO REACH AS APPROVE, and that is a structural property
   rather than a promise: both controls carry the same class, so no rule in
   web/consent.css can make one louder without naming a data attribute — which
   that file does not do, and which its own test asserts. Deny is also FIRST,
   in the DOM and on the row, because a stray Enter should land on the answer
   that grants nothing.

   COPY DISCIPLINE:
     - The word "verified" appears nowhere a reader can see it.
     - No duration is promised (obligation 6). In particular this page makes
       no claim about how long an approval lasts: docs/spec-oauth-as.md's
       third open question says one hour is an assumption nothing has
       measured, and a consent screen guessing at it would be the same lie the
       "about four minutes" build estimate was. "Hourly ceiling" is not a
       duration promise; it is the window a rate limit is counted over, and it
       is the word star/mcp/tools.py already uses for it.
     - Nothing is said about revoking an approval, because nothing in this
       repo yet says where that would be done. A sentence that cannot be
       checked against the code is cut, not softened.
     - Nothing here flatters the reader for being careful.

   WHAT THIS MODULE DOES NOT DO. It imports nothing, reads no localStorage,
   holds no bearer token, and sends exactly one request, to one path, carrying
   two fields. The `state_key` is an opaque handle: it is read verbatim, never
   trimmed, never parsed, and posted back exactly as it arrived.
*/

/* ---------------------------------------------------------------------
   Where the answer goes.
--------------------------------------------------------------------- */

const ENDPOINT = "/oauth/authorize/decide";

/* The keys this page will accept a redirect target under, in order.
   The endpoint's response shape is not fixed anywhere in the repo yet, so
   rather than guess one name and fail silently on another, it reads the first
   of these that carries a usable http(s) address. Whatever the server settles
   on, one of these is it; if it settles on a fifth, this list is the one place
   to add it. */
const TARGET_KEYS = ["redirect_to", "redirect_uri", "location", "redirect"];

/* ---------------------------------------------------------------------
   The copy. Kept together so the register can be read in one place rather
   than reconstructed from a dozen call sites — web/account.js's convention,
   and the reason its copy could be reviewed as copy.
--------------------------------------------------------------------- */

const HEADING = "A request to reach your rooms";

const LEDE =
  "Something is asking the department for access to the rooms filed under " +
  "your account. Nothing has been granted yet. Read the three things below, " +
  "then answer.";

const ACCOUNT_UNKNOWN =
  "This page was not told which account you are signed in as, so it cannot " +
  "tell you whose rooms are being asked for.";

/* --- 1. who --- */

const ASKING_LEGEND = "Who is asking";

const NAME_MISSING =
  "This request carried no client name, so the department cannot tell you " +
  "who is asking. Nothing about that is normal.";

/* The whole of what the department knows about that name, said next to it.
   Not a hedge: it is the fact that makes the hostname below worth reading,
   and a consent screen that prints a name without it is the overclaim the
   research obligations exist to prevent. */
const NAME_CAVEAT =
  "That is the name this client registered for itself. The department did " +
  "not check it against anything, and any client can register any name.";

const URI_LABEL = "The address it gave for itself";

/* A scheme this page will not turn into a link, kept on screen anyway.
   Same posture web/scriptcheck.js's UNSOURCED block takes on a URL neither
   ledger holds: dropping it would hide something the client supplied, and
   linking it would put whatever it is one click away from running in this
   page's own origin. It is printed, and it is inert. */
const URI_REFUSED =
  "This client also gave an address for itself that the department will not " +
  "turn into a link, because it is not an ordinary web address. It is " +
  "printed here exactly as it arrived, and nothing on this page opens it.";

/* --- 2. what --- */

const WANTS_LEGEND = "What it is asking for";

/* The two scopes docs/spec-oauth-as.md's Decision 4 defines, in the language
   star/mcp/tools.py already uses with an agent. That is the point of the
   decision: the free-versus-spends split is what every tool description
   already states, so this screen can say something true and specific instead
   of asking for everything. */
const SCOPES = {
  "rooms:read": {
    title: "Read the rooms you have filed",
    lines: [
      "Lists every room filed under your account, and opens any one of " +
        "them: the story profile, the research plan, the four drawers of " +
        "findings with the sources behind them, and the research bible.",
      "It costs nothing, spends no searches, and is never rate-limited.",
    ],
  },
  "rooms:write": {
    title: "Build new rooms, and check scenes against them",
    lines: [
      "This one spends real money on live web searches. A build and a check " +
        "each count against an hourly ceiling on your account, and both " +
        "count against a daily budget the whole department shares.",
      "A scene sent to be checked is stored with the room it was checked " +
        "against, and stays there until it is deleted from the web app.",
      "Nothing at this door removes anything. The department offers four " +
        "calls here, and none of them deletes a room, a check, or a scene.",
    ],
  },
};

const SCOPE_NONE =
  "This request names no access at all, so there is nothing here for the " +
  "department to grant.";

/* An unrecognised scope is printed rather than dropped, and said to be
   unrecognised rather than described. Same call star/mcp/tools.py's
   _room_report makes for a status it has no sentence for: a wrong description
   of an unfamiliar thing is worse than an honest one saying so. Dropping it
   would be worse still — it would hide access being asked for. */
const SCOPE_UNKNOWN =
  "The department has no description for this one. It is printed exactly as " +
  "it arrived rather than explained, because a description invented for it " +
  "would be a claim about access nobody here can account for.";

/* --- 3. where --- */

const WHERE_LEGEND = "Where the department will send you back";

const WHERE_WHY =
  "The department returns you to that address the moment you answer. The " +
  "name above is what this client registered for itself; the address is " +
  "where the answer actually goes. Any client can claim another client's " +
  "name and its metadata, so the address is the part that tells two of them " +
  "apart. If you did not expect it, deny this.";

const WHERE_LOOPBACK =
  "That is not a website. It is an application running on this computer, " +
  "listening on a port. The department cannot tell you which one, and any " +
  "program on this machine can take a port and register any name it likes. " +
  "If you did not just start a client here and ask it to connect, deny this.";

const WHERE_MISSING =
  "This request carried no address to send you back to, so this page cannot " +
  "show you where your answer would go. That is the one thing here worth " +
  "reading, and it is the thing that is missing.";

/* --- the answer --- */

const DENY = "Deny this request";
const APPROVE = "Approve this request";

const DECIDE_NOTE =
  "Either answer sends you back to the client with the department's reply. " +
  "Denying grants nothing, and nothing already filed under your account is " +
  "touched either way.";

/* No handle, no answer. The controls are not drawn at all rather than drawn
   and disabled: web/account.js disables a control AND states its reason
   because there is something the reader can do to enable it, and here there
   is not. A control that can never work is not a refusal, it is a lie about
   what this page can do. */
const NO_STATE_KEY =
  "This page was opened without the handle the department needs to record " +
  "an answer, so there is nothing here to approve or to deny. Nothing has " +
  "been granted. Start the connection again from the client that sent you.";

const WORKING = "Sending your answer to the department.";

/* Said where the blocked control is, not at the top of the page, because a
   reason belongs beside the thing it explains. Names what is missing, what it
   would cost to approve anyway, and what to do instead. */
const UNATTACHED =
  "This browser is not attached to an account, so there is nothing here worth " +
  "granting. Rooms filed by an unattached session live with this browser " +
  "alone, and a client given access to one would hold a lasting credential to " +
  "an account nobody can recover. Attach a Google account and the request " +
  "comes back with your own rooms behind it.";

const ATTACH = "Attach a Google account, then come back";
const ATTACHING = "Sending you to Google. This request is held until you return.";

const UNREACHABLE =
  "The department could not be reached, so your answer was not recorded and " +
  "nothing has been granted. Try again.";

const NO_TARGET =
  "The department recorded your answer but handed back no address this page " +
  "will open. Nothing more happens here. Go back to the client that sent you.";

/* ---------------------------------------------------------------------
   Small shared shapes. The same three-argument element helper
   web/scriptcheck.js and web/account.js use, for the same reason: text goes
   through createTextNode, always, and there is no second way in.
--------------------------------------------------------------------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.setAttribute("class", className);
  if (text !== undefined && text !== null && text !== "") {
    node.appendChild(document.createTextNode(String(text)));
  }
  return node;
}

/** Parse a candidate as an http(s) URL, or null.
 *
 *  The same guard web/scriptcheck.js and web/clip.js make, and here it is not
 *  belt-and-braces: `client_uri` is chosen by the client, so a
 *  `javascript:` URI is one click from executing in this page's origin, on
 *  the page where that click is worth the most. Anything that is not http or
 *  https never reaches an href. */
function httpUrl(raw) {
  try {
    const url = new URL(String(raw));
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/* The hosts that mean "this computer". Matched exactly, plus RFC 6761's
   `.localhost` suffix, which also resolves to loopback and would otherwise
   get the general sentence while being the case the spec warns about by
   name. `redirect_host` is extracted server-side from the redirect URI, so
   this is a comparison against a hostname rather than a parse of one. */
const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

function isLoopback(host) {
  const name = String(host).trim().toLowerCase();
  return LOOPBACK.has(name) || name.endsWith(".localhost");
}

/* ---------------------------------------------------------------------
   The query string, as data.

   Taken as an argument rather than read off `location` inside the renderer,
   so the parameter reading a test exercises is the one that ships and no
   stand-in parser stands between an attacker's characters and the DOM.
--------------------------------------------------------------------- */

/** Read the six parameters the server renders this page with.
 *
 *  Every one of them is attacker-controlled. Nothing below interprets any of
 *  them: `state_key` is taken verbatim because it is opaque and belongs to
 *  the server, and the other five are trimmed only of surrounding whitespace
 *  so an empty value and a value of three spaces are the same absence. */
export function readParams(search) {
  const params = new URLSearchParams(String(search || ""));
  const one = (name) => String(params.get(name) || "").trim();
  return {
    clientName: one("client_name"),
    clientUri: one("client_uri"),
    redirectHost: one("redirect_host"),
    // De-duplicated, because a scope list repeating itself would print the
    // same block twice and read as two different grants.
    scopes: [...new Set(one("scope").split(/\s+/).filter(Boolean))],
    stateKey: String(params.get("state_key") || ""),
    account: one("account"),
  };
}

/* ---------------------------------------------------------------------
   1. Who is asking.
--------------------------------------------------------------------- */

function buildAsking(params) {
  const block = el("section", "consent-block");
  block.appendChild(el("h3", "consent-legend", ASKING_LEGEND));

  if (params.clientName) {
    // The single most dangerous string on this page, and it is one text node
    // inside one <p>. web/consent.css bounds the box and lets it scroll
    // rather than truncating it: a name cut short hides its own tail, and a
    // name of unbounded length would push the deny control off the screen.
    block.appendChild(el("p", "consent-client-name", params.clientName));
    block.appendChild(el("p", "consent-note", NAME_CAVEAT));
  } else {
    block.appendChild(el("p", "consent-refusal", NAME_MISSING));
  }

  const uri = httpUrl(params.clientUri);
  if (uri) {
    block.appendChild(el("p", "consent-sublabel", URI_LABEL));
    // The href and the visible text are the same string, deliberately: a link
    // whose label says one address and whose target is another is the oldest
    // trick on a page like this one. Both are the URL parser's own
    // normalisation of what arrived, so neither can differ from the other.
    const link = el("a", "consent-client-uri", uri.href);
    link.setAttribute("href", uri.href);
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
    block.appendChild(link);
  } else if (params.clientUri) {
    block.appendChild(el("p", "consent-note", URI_REFUSED));
    block.appendChild(el("p", "consent-inert-uri", params.clientUri));
  }

  return block;
}

/* ---------------------------------------------------------------------
   2. What it is asking for.
--------------------------------------------------------------------- */

function buildScope(name) {
  const block = el("div", "consent-scope");
  // The raw token, first and verbatim, so what the reader approves and what
  // the request said are visibly the same string.
  block.appendChild(el("span", "consent-scope-token", name));

  const known = Object.prototype.hasOwnProperty.call(SCOPES, name)
    ? SCOPES[name]
    : null;
  if (!known) {
    block.appendChild(el("p", "consent-line", SCOPE_UNKNOWN));
    return block;
  }

  block.appendChild(el("h4", "consent-scope-title", known.title));
  for (const line of known.lines) block.appendChild(el("p", "consent-line", line));
  return block;
}

function buildWants(params) {
  const block = el("section", "consent-block");
  block.appendChild(el("h3", "consent-legend", WANTS_LEGEND));
  if (!params.scopes.length) {
    block.appendChild(el("p", "consent-refusal", SCOPE_NONE));
    return block;
  }
  for (const name of params.scopes) block.appendChild(buildScope(name));
  return block;
}

/* ---------------------------------------------------------------------
   3. Where the department will send you back.

   The one onionskin slip on this page, and it is here rather than on the
   scopes on purpose: onionskin is the surface this app puts under the thing
   a reader has to read carefully before they act (the intake's retention
   notice, the check panel's, the card's reach notice). If everything on this
   card were a slip, nothing would be.
--------------------------------------------------------------------- */

function buildWhere(params) {
  const block = el("section", "consent-block");
  block.appendChild(el("h3", "consent-legend", WHERE_LEGEND));

  if (!params.redirectHost) {
    block.appendChild(el("p", "consent-refusal", WHERE_MISSING));
    return block;
  }

  const slip = el("div", "consent-where");
  // A plate, not a stamp. It carries the stamp's letterforms because that is
  // what this app sets an address in, and it does not rotate and does not
  // press: docs/design/DIRECTION.md is explicit that the stamp is an EVENT,
  // and nothing about a hostname just happened. web/account.css's revoked
  // stamp makes the same call for the same reason.
  slip.appendChild(el("span", "consent-host", params.redirectHost));
  slip.appendChild(
    el("p", "consent-line", isLoopback(params.redirectHost) ? WHERE_LOOPBACK : WHERE_WHY)
  );
  block.appendChild(slip);
  return block;
}

/* ---------------------------------------------------------------------
   The answer.
--------------------------------------------------------------------- */

/** The two controls, and the guarantee that neither outranks the other.
 *
 *  Both carry the class `decide-btn` and differ only in a data attribute and
 *  their label, so making one louder than the other would take a new
 *  selector in web/consent.css naming that attribute — which is a deliberate
 *  edit somebody has to write, not a drift. Deny is first in document order,
 *  which is also first in tab order.
 *
 *  One press each. No arming, unlike the card's sign-out and revoke: this
 *  page IS the confirmation step, and a consent screen that asks twice is a
 *  consent screen that trains people to click through twice. */
function buildDecide(params, handlers) {
  const block = el("section", "consent-block consent-decide");

  if (!params.stateKey) {
    block.appendChild(el("p", "consent-refusal", NO_STATE_KEY));
    return block;
  }

  const status = el("p", "consent-status");
  const refusal = el("p", "consent-refusal");
  const row = el("div", "decide-row");
  const buttons = [];

  function press(decision) {
    for (const button of buttons) button.disabled = true;
    refusal.replaceChildren();
    status.replaceChildren(document.createTextNode(WORKING));
    handlers.onDecide(decision, {
      /** The department declined, or could not be reached. Both controls come
       *  back, because nothing was granted and the reader still has an answer
       *  to give. */
      fail(message) {
        status.replaceChildren();
        refusal.replaceChildren(document.createTextNode(String(message)));
        for (const button of buttons) button.disabled = false;
      },
    });
  }

  for (const [decision, label] of [["deny", DENY], ["approve", APPROVE]]) {
    const button = el("button", "decide-btn", label);
    button.setAttribute("type", "button");
    button.setAttribute("data-decision", decision);
    // AN UNATTACHED SESSION CANNOT APPROVE, and the reason is not caution.
    //
    // A grant binds to whatever account answers. An anonymous session is one
    // browser's localStorage entry, so approving from it hands a client a
    // durable credential to an account that holds nothing and that nobody can
    // recover — the same argument that stops `POST /api/tokens` issuing to an
    // unlinked uid, arriving at the other end of the same flow.
    //
    // Deny stays live. A reader who did not want this should always be able to
    // say so, and refusing them the answer that grants nothing would be the
    // one asymmetry this screen must never have.
    if (decision === "approve" && params.account && !params.linked) {
      button.disabled = true;
      button.setAttribute("aria-describedby", "consent-why-blocked");
    }
    button.addEventListener("click", () => press(decision));
    buttons.push(button);
    row.appendChild(button);
  }

  block.appendChild(row);

  // The reason, and a way out of it. A control that is disabled and silent
  // tells a reader they are stuck; this one says what is missing and puts the
  // fix in reach, which is the same rule the card follows for its own issue
  // control.
  if (params.account && !params.linked) {
    const why = el("p", "consent-refusal", UNATTACHED);
    why.setAttribute("id", "consent-why-blocked");
    block.appendChild(why);

    if (handlers.onAttach) {
      const attach = el("button", "decide-btn consent-attach", ATTACH);
      attach.setAttribute("type", "button");
      attach.addEventListener("click", () => {
        attach.disabled = true;
        status.replaceChildren(document.createTextNode(ATTACHING));
        handlers.onAttach();
      });
      block.appendChild(attach);
    }
  }

  block.appendChild(el("p", "consent-note", DECIDE_NOTE));
  block.appendChild(status);
  block.appendChild(refusal);
  return block;
}

/* ---------------------------------------------------------------------
   The whole counter, assembled. Detached, so the caller mounts one node and
   a test walks one node.
--------------------------------------------------------------------- */

/** Build the consent screen.
 *
 *  `params` is everything the query string said and `handlers` is everything
 *  this surface can do; this function performs no I/O of its own, which is
 *  what lets it be exercised against a stubbed document with no network and
 *  no HTML parser anywhere in reach. */
export function renderConsent(params, handlers = {}) {
  const root = el("div", "consent-card");

  const heading = el("h2", "consent-heading", HEADING);
  heading.setAttribute("id", "consent-heading");
  root.appendChild(heading);
  root.appendChild(el("p", "consent-lede", LEDE));
  root.appendChild(
    params.account
      ? el("p", "consent-account", "You are answering as " + params.account + ".")
      : el("p", "consent-refusal", ACCOUNT_UNKNOWN)
  );

  root.appendChild(buildAsking(params));
  root.appendChild(buildWants(params));
  root.appendChild(buildWhere(params));
  root.appendChild(buildDecide(params, handlers));
  return root;
}

/* ---------------------------------------------------------------------
   The page's own wiring. Everything below reaches the document by id and
   runs only in a browser, so importing this module in Node costs nothing and
   touches no DOM — the same seam web/account.js and web/scriptcheck.js keep,
   and what lets the renderer above be tested against a stub.
--------------------------------------------------------------------- */

/** One refusal from the department, read the way web/account.js reads one.
 *
 *  An unguarded res.json() surfaces the PARSE failure instead of the request
 *  failure: a proxy answering with an HTML body would put `Unexpected token
 *  '<'` on screen as the department's own sentence. */
async function failureDetail(res) {
  try {
    return (await res.json()).detail || res.statusText || UNREACHABLE;
  } catch {
    return res.statusText || UNREACHABLE;
  }
}

/** Where the server says to go next, if it is somewhere this page will go.
 *
 *  Guarded with the same http(s) check `client_uri` gets, and for a reason
 *  that survives the server being trustworthy: the address the endpoint hands
 *  back is derived from a redirect URI the CLIENT registered, so it is not
 *  the department's own string in any meaningful sense. Nothing that is not
 *  http or https is navigated to. */
export function redirectTarget(body) {
  for (const key of TARGET_KEYS) {
    const url = httpUrl((body || {})[key] || "");
    if (url) return url.href;
  }
  return "";
}

/* The decision is sent AS somebody, and that is not decoration.
 *
 * This module was built credential-free, which was the right instinct and the
 * wrong contract, and the gap was in the brief rather than in the build: a
 * `state_key` proves that this browser was sent here by a real /oauth/authorize
 * request, and proves nothing at all about WHO is pressing the control. The
 * grant being minted is a grant over one reader's rooms. Without an identity on
 * this request the server would have to either bind the grant at redirect time,
 * before anyone has agreed to anything, or take the browser's word for whose
 * rooms these are.
 *
 * So the handle proves the request is real and the ID token proves who answered
 * it, and the server needs both. `authedFetch` is the same helper every other
 * /api call in this app goes through, including its one retry on a 401, which
 * is worth having on the single request this page ever makes.
 *
 * It costs this file its only import, and the import is same-origin. The
 * property that actually mattered is untouched: nothing here becomes markup. */
async function submit(stateKey, decision, controls) {
  let body;
  try {
    const { authedFetch } = await import("/auth.js");
    const res = await authedFetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The handle goes back exactly as it arrived. This page never asked
      // what is inside it and is not the thing that decides whether it is
      // still good.
      body: JSON.stringify({ state_key: stateKey, decision }),
    });
    if (!res.ok) {
      controls.fail(await failureDetail(res));
      return;
    }
    body = await res.json();
  } catch {
    controls.fail(UNREACHABLE);
    return;
  }

  const target = redirectTarget(body);
  if (!target) {
    controls.fail(NO_TARGET);
    return;
  }
  location.assign(target);
}

/** Who the reader is signed in as, read off their own ID token.
 *
 *  The server cannot put this in the query string and should not try. It
 *  redirects here before anyone has answered anything, and it binds a uid only
 *  when the answer comes back — which is what stops a link somebody was tricked
 *  into opening from pre-binding a grant to whoever happened to be signed in.
 *  So the account is this page's to discover, and the only honest source is the
 *  credential the browser is about to sign the decision with.
 *
 *  Claims are read, never verified. Verification is the server's, on the token
 *  this page then sends it. What is printed here is a label telling a reader
 *  whose rooms they are handing over, and a forged label would be a lie told to
 *  the forger about their own screen. */
async function signedInAs() {
  try {
    const { getIdToken } = await import("/auth.js");
    const token = await getIdToken();
    if (!token) return { account: "", linked: false };
    const claims = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
    );
    const identities = (claims.firebase || {}).identities || {};
    // Linked means a federated identity, read the same way and in the same
    // order `web/auth.js`'s linkedProvider and `star/auth.py`'s linked_provider
    // both read it: identities first, provider second. A third place that
    // disagreed with those two about what "attached" means would refuse a real
    // account on one screen and admit it on another.
    const federated = Object.keys(identities).some((k) => k.includes("."));
    const linked = federated || (claims.firebase || {}).sign_in_provider === "google.com";
    return {
      linked,
      account: claims.email || (linked ? "a linked account" : "this browser's anonymous session"),
    };
  } catch {
    return { account: "", linked: false };
  }
}

async function start() {
  const mount = document.getElementById("consent");
  if (!mount) return;
  const params = readParams(location.search);
  const draw = () =>
    mount.replaceChildren(
      renderConsent(params, {
        onDecide: (decision, controls) => submit(params.stateKey, decision, controls),
        /** Sign in without losing the request that sent them here.
         *
         *  `returnTo` is this exact URL, `state_key` and all, so the reader
         *  comes back to the same pending authorization rather than to a page
         *  that has forgotten why they were sent. It survives the round trip
         *  because auth.js stashes it in sessionStorage and app.js navigates to
         *  it when the link completes.
         *
         *  The pending authorization is held for ten minutes, which is more
         *  than a Google round trip costs and is the reason this offer can be
         *  made at all. */
        onAttach: async () => {
          const { beginGoogleLink } = await import("/auth.js");
          await beginGoogleLink({ returnTo: location.pathname + location.search });
        },
      })
    );

  // Drawn twice on purpose. The first pass is synchronous, so the request and
  // the two controls are on screen before any network call resolves; the
  // second fills in the account once Firebase has answered. A page that waited
  // for the network to paint anything would show a reader a blank card while a
  // client sat waiting for a redirect.
  draw();
  if (!params.account) {
    const who = await signedInAs();
    params.account = who.account;
    params.linked = who.linked;
    if (params.account) draw();
  }
}

/* The page starts itself. There is no app.js on this document to call an
   init, and a module script is deferred by definition, so the document is
   already parsed by the time this line runs.
   Guarded on `window` rather than on a flag: this module is imported in Node
   by tests/js/test_consent.mjs, where there is no window, no location, and
   nothing to start. The same seam web/account.js's returnTo() already keeps. */
if (typeof window !== "undefined") start();
