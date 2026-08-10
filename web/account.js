/* THE MORGUE — Your card: who you are, and what has been issued in your name.

   THE NAME. spec.md > The card: the account surface proposed "Your card" and
   marked it a naming call. It is kept. In a morgue the reader has a card, and
   the word is already in force alongside drawer plates, folder tabs, receipts
   and stamps. It also does the one job "account settings" could not: the rail
   entry has to sit on the intake path, and "Your card" says nothing about
   accounts to a writer who will never sign in to anything.

   THE ONE RULE THIS FILE INHERITS FROM web/scriptcheck.js, and for the same
   reason: NOTHING here ever becomes markup. No innerHTML, no template string
   that reaches the DOM, and no escaping function either, because there is
   nothing to escape when every string becomes a text node. That matters most
   on one field — a token's `label` is reader-supplied text, stored verbatim
   and read back on every render, which is the exact shape of a stored XSS. It
   arrives as characters and reaches the DOM as a text node, and the property
   is structural rather than remembered.

   WHERE THE CARD'S COPY LIVES, and why it is here rather than in index.html.
   prd.md's first identity story is a writer who will never sign in to
   anything: "the intake path from landing to a filed room contains zero
   mentions of Google or of accounts." A fourth <section> carrying the link
   offer with `hidden` on it would still carry that copy in the document, so
   #account-panel ships empty and every sentence below reaches the DOM only
   when the rail's entry is used.

   WHAT THIS FILE DOES NOT DO, stated because it is an acceptance criterion:
   it never touches web/app.js's EventSource, never opens or closes a stream,
   and never re-fetches a room. Opening the card mid-build is web/shell.js's
   showAccount() toggling panel visibility and this module drawing into an
   empty section. A run streaming into #progress-panel's DOM keeps streaming
   into it while the panel is hidden.

   COPY DISCIPLINE:
     - The word "verified" appears nowhere a reader can see it.
     - No clause that cannot be verified from the code, softened. Cut instead.
       The intake's retention copy was re-verified against post-link truth in
       this same task; see the comment above #intake-panel in web/index.html
       for the clause-by-clause result, and see LINK_REACH below for the
       sentence the intake cut and this surface now carries.
     - Sign-out says what it will do BEFORE it happens. web/auth.js ships
       signOutNotice() for exactly this and its docstring makes it a
       requirement rather than a suggestion; the control here arms first, shows
       the notice, and only calls signOut() on a second press.
     - A token's plaintext appears exactly once, and the sentence saying so is
       standing copy in the ISSUED TOKENS block — it is on screen before the
       reader can press the control, not after.
*/

import {
  authedFetch,
  beginGoogleLink,
  completeGoogleLink,
  linkedProvider,
  linkingAvailable,
  signOut,
  signOutNotice,
} from "/auth.js";
import { refreshRail } from "/shell.js";

/* ---------------------------------------------------------------------
   The copy. Kept together so the register can be read in one place rather
   than reconstructed from a dozen call sites — web/scriptcheck.js's
   convention, and the reason its copy could be reviewed as copy.
--------------------------------------------------------------------- */

const HEADING = "Your card";

const IDENTITY_LEGEND = "Identity";
const TOKENS_LEGEND = "Issued tokens";

const UNATTACHED = "Not attached to an account.";

/* The offer, in one line, without flattery. prd.md asks for exactly this: what
   linking buys, which is that the rooms stop living with this browser. */
const LINK_OFFER =
  "Your rooms live with this browser. Attach a Google account and they stop " +
  "doing that.";

/* THE SENTENCE THE INTAKE CUT, standing here instead, before the link.
   prd.md requires the account surface to state, before the link, that a linked
   account can read these rooms from any browser and from any agent holding a
   token. The intake used to end on "Nothing is visible without your sign-in
   token", whose plain reading — only this browser can see this — goes false
   the moment either of those two things is true. It was cut there rather than
   softened, and the whole of it is said here, where the reader is about to
   act. */
const LINK_REACH =
  "Once attached, these rooms are readable from any browser you sign in to " +
  "with that account, and by any agent holding a token you issue below. That " +
  "is what attaching one buys, and it is the whole of what it costs.";

const LINK_ACTION = "Attach a Google account";

/* The fourth criterion of prd.md's first identity story, in the form the
   reader meets it. GOOGLE_OAUTH_CLIENT_ID deliberately does not join
   star/config.py's validate_env(), so an unset variable is not an outage: it
   is this sentence, and every other path in the app works untouched. */
const LINK_UNAVAILABLE =
  "Attaching an account is not available on this deployment. Everything else " +
  "here works exactly as it does now, and your rooms stay with this browser.";

/* Said after the link as well as before it, because it is still true and a
   fact a reader is owed once is a fact they are owed twice. */
const LINKED_REACH =
  "These rooms are readable from any browser you sign in to with this " +
  "account, and by any agent holding one of the tokens below.";

const SIGN_OUT = "Sign out";
const SIGN_OUT_CONFIRM = "Sign out for good";

/* Standing copy, on screen before the control can be pressed. Three facts, and
   the middle one is the announcement the plaintext is required to carry: it is
   shown once. "Cannot be recovered" is not a promise about a duration or about
   a source, it is a statement about star/tokens.py, which stores sha256 of the
   secret and never the secret. */
const TOKENS_INTRO =
  "A token lets an agent reach this department as you: read your filed rooms, " +
  "build new ones, and check scenes against them. The token itself is shown " +
  "once, on this screen, at the moment it is issued. The department stores " +
  "only a hash of it, so it cannot be shown again or recovered later — if you " +
  "lose it, revoke it and issue another.";

/* The disabled control's reason, stated rather than left to a grey button.
   Deliberately the same argument star/server.py's 403 makes, because the card
   refusing for one reason while the server refuses for another is two
   departments. */
const ISSUE_BLOCKED =
  "You cannot issue a token yet: this session has no account attached. A token " +
  "issued to a browser-only session would be a key to rooms nobody could ever " +
  "sign back in to, so the department refuses to mint one. Attach an account " +
  "above first.";

const ISSUE_ACTION = "Issue a token";
const ISSUE_LABEL = "Name it, so you can tell it from the next one";

/* The one moment the plaintext exists on a screen. */
const PLAINTEXT_LEGEND = "This is the only time this token is shown";
const PLAINTEXT_USE =
  "Send it to the department as an Authorization header, in the form " +
  "“Bearer” followed by the token. Copy it now.";

const NO_TOKENS = "No tokens have been issued from this account.";

/* An empty list and a list that could not be read are different facts, and
   printing the first when you mean the second is the defect this phase has
   caught four times (web/shell.js's renderRail carries the same pair). */
const TOKENS_UNREADABLE =
  "Your issued tokens could not be reached just now. They are not gone — " +
  "reload to try again.";

const REVOKE = "Revoke";
const REVOKE_CONFIRM = "Revoke it for good";
const REVOKE_NOTICE =
  "Revoking is immediate and cannot be undone. Any agent still holding this " +
  "token is told it was revoked, and stops being able to read your rooms.";

const WORKING = "Reading your card";

/* ---------------------------------------------------------------------
   Small shared shapes. Same three-argument element helper web/scriptcheck.js
   uses, for the same reason: text goes through createTextNode, always.
--------------------------------------------------------------------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.setAttribute("class", className);
  if (text !== undefined && text !== null && text !== "") {
    node.appendChild(document.createTextNode(String(text)));
  }
  return node;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** DD MON YYYY, the stamp's slug face — the same format web/app.js's stampDate
 *  and web/scriptcheck.js's filedDate produce, always from the payload's own
 *  timestamp and never from this clock. Empty for a value that is missing or
 *  unparseable, and every caller drops the line rather than filling it. */
function slugDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const month = d.toLocaleString("en-US", { month: "short" }).toUpperCase();
  return `${pad2(d.getDate())} ${month} ${d.getFullYear()}`;
}

/** A two-press control: the first press says what the second one will do.
 *
 *  The pattern web/scriptcheck.js's delete control already uses, lifted here
 *  because the card carries the app's two genuinely irreversible actions. The
 *  notice is a node this function puts on the page, not a browser dialog: the
 *  department says it in its own voice, and a test can read it.
 *
 *  `notice` is a string held before the first press, never fetched on it. That
 *  is what makes "says what it does BEFORE it happens" a property of the code
 *  rather than of the network. */
function armedButton({ className, label, confirmLabel, notice, onConfirm }) {
  const wrap = el("div", `${className}-wrap`);
  const button = el("button", className, label);
  button.setAttribute("type", "button");
  button.setAttribute("data-armed", "false");
  const line = el("p", `${className}-notice`);

  button.addEventListener("click", () => {
    if (button.getAttribute("data-armed") !== "true") {
      button.setAttribute("data-armed", "true");
      button.replaceChildren(document.createTextNode(confirmLabel));
      line.replaceChildren(document.createTextNode(notice));
      return;
    }
    button.disabled = true;
    onConfirm();
  });

  wrap.appendChild(button);
  wrap.appendChild(line);
  return wrap;
}

/* ---------------------------------------------------------------------
   IDENTITY.
--------------------------------------------------------------------- */

function buildIdentity(state, handlers) {
  const block = el("section", "account-block");
  block.appendChild(el("h3", "account-legend", IDENTITY_LEGEND));

  if (state.linked) {
    // The address is the identity the reader recognises; the provider is the
    // fallback when the token carried no email claim. Never both, and never a
    // display name standing in for either — a name is not what signs in.
    const who = state.linked.email || state.linked.provider;
    block.appendChild(el("p", "account-line", `Attached to ${who}.`));
    block.appendChild(el("p", "account-line", LINKED_REACH));
  } else {
    block.appendChild(el("p", "account-line", UNATTACHED));
    if (state.linkingAvailable) {
      block.appendChild(el("p", "account-line", LINK_OFFER));
      block.appendChild(el("p", "account-reach", LINK_REACH));
      const link = el("button", "account-link-btn", LINK_ACTION);
      link.setAttribute("type", "button");
      link.addEventListener("click", () => handlers.onLink());
      block.appendChild(link);
    } else {
      block.appendChild(el("p", "account-line", LINK_UNAVAILABLE));
    }
  }

  // Whatever the redirect brought back, if it brought back a refusal. Six of
  // spec.md's seven error rows have their own sentence in web/auth.js and the
  // seventh — a reader who backed out — deliberately has none, so this renders
  // only what that table produced and never a sentence of its own.
  if (state.linkMessage) {
    block.appendChild(el("p", "account-refusal", state.linkMessage));
  }

  block.appendChild(
    armedButton({
      className: "account-signout-btn",
      label: SIGN_OUT,
      confirmLabel: SIGN_OUT_CONFIRM,
      notice: state.signOutNotice,
      onConfirm: () => handlers.onSignOut(),
    })
  );

  return block;
}

/* ---------------------------------------------------------------------
   ISSUED TOKENS.
--------------------------------------------------------------------- */

/** One issued token, as metadata and nothing else.
 *
 *  star/models.py's McpToken has no field for the secret and no field for its
 *  hash, and this renderer names the four fields it draws one at a time rather
 *  than iterating the payload — so a field added to the stored document later
 *  cannot arrive on this surface by accident. That is the same argument the
 *  model itself makes, kept on both ends of the wire. */
function buildToken(token, handlers) {
  const item = el("li", "token");
  const revoked = String(token?.revoked_at || "");
  if (revoked) item.setAttribute("data-revoked", "true");

  // An unlabelled token is a truthful blank rather than a name the department
  // made up: star/server.py's TokenRequest defaults `label` to "" for exactly
  // this reason, so the card has to have a way to say "you did not name it".
  const label = String(token?.label || "").trim();
  item.appendChild(
    label
      ? el("span", "token-label", label)
      : el("span", "token-label token-label-blank", "Unnamed token")
  );

  const meta = el("p", "token-meta");
  const issued = slugDate(token?.created_at);
  if (issued) meta.appendChild(el("span", "token-fact", `ISSUED ${issued}`));
  // "Never used" is a fact the payload proves — star/tokens.py writes
  // last_used_at only when the token authenticates a call — where a blank
  // would read as a field this page failed to fetch.
  const used = slugDate(token?.last_used_at);
  meta.appendChild(el("span", "token-fact", used ? `LAST USED ${used}` : "NEVER USED"));
  const id = String(token?.token_id || "").trim();
  if (id) meta.appendChild(el("span", "token-fact token-id", id));
  item.appendChild(meta);

  if (revoked) {
    // The soft delete stays on the card, because the soft delete is what lets
    // the next call carrying this token be TOLD it was revoked rather than
    // refused as though it were malformed (star/tokens.py's step 5). The card
    // showing the same fact is the reader's half of that.
    const stamp = el("span", "token-revoked-stamp", "Revoked");
    item.appendChild(stamp);
    const when = slugDate(revoked);
    if (when) item.appendChild(el("p", "token-meta", `REVOKED ${when}`));
    return item;
  }

  item.appendChild(
    armedButton({
      className: "token-revoke-btn",
      label: REVOKE,
      confirmLabel: REVOKE_CONFIRM,
      notice: REVOKE_NOTICE,
      onConfirm: () => handlers.onRevoke(id),
    })
  );
  return item;
}

/** The plaintext, once.
 *
 *  Rendered BELOW TOKENS_INTRO in document order, which is the requirement
 *  rather than a layout choice: "the surface says so before issuing" means the
 *  sentence about the token being shown once is already on the page when the
 *  reader presses the control, and still above the token when it appears. */
function buildPlaintext(issued) {
  const block = el("div", "token-plaintext");
  block.appendChild(el("p", "token-plaintext-legend", PLAINTEXT_LEGEND));
  block.appendChild(el("code", "token-plaintext-value", String(issued.token || "")));
  block.appendChild(el("p", "token-plaintext-use", PLAINTEXT_USE));
  return block;
}

function buildTokens(state, handlers) {
  const block = el("section", "account-block");
  block.appendChild(el("h3", "account-legend", TOKENS_LEGEND));
  block.appendChild(el("p", "account-line", TOKENS_INTRO));

  // Immediately after the standing copy and before the list, so the one moment
  // the plaintext exists on a screen is directly under the sentence that
  // warned about it.
  if (state.issued) block.appendChild(buildPlaintext(state.issued));

  const issue = el("div", "token-issue");
  const field = el("label", "token-issue-label", ISSUE_LABEL);
  field.setAttribute("for", "token-label");
  const input = el("input", "token-issue-input");
  input.setAttribute("id", "token-label");
  input.setAttribute("type", "text");
  input.setAttribute("autocomplete", "off");
  // No maxlength on purpose. star/tokens.py's MAX_LABEL_CHARS is the one place
  // that cap is defined, and a number copied here would be a second place for
  // it to drift; the server's refusal already names the cap and the count that
  // was sent, and this surface shows that sentence verbatim.
  input.value = "";
  const button = el("button", "token-issue-btn", ISSUE_ACTION);
  button.setAttribute("type", "button");

  if (state.linked) {
    button.addEventListener("click", () => handlers.onIssue(String(input.value || "")));
  } else {
    // Disabled AND explained. A greyed control with no reason is the refusal a
    // reader reads as a bug in the department; the sentence below says which
    // of the two things it is and what to do next.
    button.disabled = true;
    input.disabled = true;
    button.setAttribute("aria-describedby", "token-issue-blocked");
  }

  issue.appendChild(field);
  issue.appendChild(input);
  issue.appendChild(button);
  block.appendChild(issue);

  if (!state.linked) {
    const reason = el("p", "token-blocked", ISSUE_BLOCKED);
    reason.setAttribute("id", "token-issue-blocked");
    block.appendChild(reason);
  }

  if (state.issueError) {
    block.appendChild(el("p", "account-refusal", state.issueError));
  }

  const tokens = Array.isArray(state.tokens) ? state.tokens : [];
  if (state.tokensUnreadable) {
    block.appendChild(el("p", "account-line", TOKENS_UNREADABLE));
  } else if (!tokens.length) {
    block.appendChild(el("p", "account-line", NO_TOKENS));
  } else {
    const list = el("ul", "token-list");
    for (const token of tokens) list.appendChild(buildToken(token, handlers));
    block.appendChild(list);
  }

  return block;
}

/* ---------------------------------------------------------------------
   The whole card, assembled. Detached, so the caller mounts one node and a
   test walks one node.
--------------------------------------------------------------------- */

/** Build the card.
 *
 *  `state` is everything the surface knows and `handlers` is everything it can
 *  do; this function performs no I/O of its own, which is what lets it be
 *  exercised against a stubbed document with no network at all. */
export function renderAccountCard(state, handlers = {}) {
  const root = el("div", "account-card");
  root.appendChild(el("h2", "account-heading", HEADING));
  root.appendChild(buildIdentity(state, handlers));
  root.appendChild(buildTokens(state, handlers));
  return root;
}

/* ---------------------------------------------------------------------
   The surface's own wiring. Everything below reaches index.html by id and is
   inert until initAccount() runs, so importing this module in Node costs
   nothing and touches no DOM — the same seam web/scriptcheck.js keeps, and
   what lets the renderer above be tested against a stub.
--------------------------------------------------------------------- */

let panel = null;
let card = null;

export function initAccount() {
  panel = document.getElementById("account-panel");
}

/** Read the card, then draw it.
 *
 *  Called on every entry from the rail rather than once, because everything on
 *  this surface can change from outside it: a link resolves on a page load, a
 *  token is used by an agent between two visits, and a sign-out mints a new
 *  session. There is no cache to go stale because there is no cache. */
export async function openAccount() {
  if (!panel) return;
  panel.replaceChildren(working());
  card = await readCard();
  draw();
}

function working() {
  const line = el("p", "account-working", WORKING);
  line.appendChild(el("span", "ellipsis"));
  return line;
}

async function readCard() {
  // Resolved rather than assumed: completeGoogleLink() caches its result for
  // the life of the page, so this reads the outcome of the redirect web/app.js
  // already resolved at load rather than starting a second exchange.
  let outcome = null;
  try {
    outcome = await completeGoogleLink();
  } catch {
    outcome = null;
  }

  let linked = null;
  try {
    linked = await linkedProvider();
  } catch {
    linked = null;
  }

  let notice = "";
  try {
    notice = await signOutNotice();
  } catch {
    notice = "";
  }

  const { tokens, unreadable } = await readTokens();

  return {
    linkingAvailable: linkingAvailable(),
    linked,
    // Only a refusal earns a line. "none" and "abandoned" are non-events by
    // design — prd.md requires no error state on screen for a link nobody
    // completed — and "linked" is already said by the identity above.
    linkMessage: outcome && outcome.status === "failed" ? outcome.message : "",
    signOutNotice: notice,
    tokens,
    tokensUnreadable: unreadable,
    issued: null,
    issueError: "",
  };
}

/** The list, from the server rather than inferred from a decoded claim.
 *
 *  An unattached session cannot have issued a token — star/server.py refuses —
 *  so skipping this request would usually be right and occasionally be a lie:
 *  linkedProvider() decodes the ID token locally, and a token this page cannot
 *  read reads as "not attached", which would then print "no tokens have been
 *  issued" over an account holding several. The list is the server's answer,
 *  and a request that fails says so instead of claiming an empty account. */
async function readTokens() {
  try {
    const res = await authedFetch("/api/tokens");
    if (!res.ok) return { tokens: [], unreadable: true };
    const body = await res.json();
    return Array.isArray(body?.tokens)
      ? { tokens: body.tokens, unreadable: false }
      : { tokens: [], unreadable: true };
  } catch {
    return { tokens: [], unreadable: true };
  }
}

function draw() {
  if (!panel || !card) return;
  panel.replaceChildren(renderAccountCard(card, HANDLERS));
}

/** Draw again after something the reader did.
 *
 *  `issued` is cleared on the way through, and that clearing is what makes
 *  "the plaintext appears exactly once" true rather than intended: the only
 *  render that carries it is the one immediately after the issue, and every
 *  subsequent draw — a revoke, a second issue, a fresh visit — rebuilds the
 *  card without it. There is nowhere else it is held. */
function redraw(patch = {}) {
  card = { ...card, issued: null, issueError: "", ...patch };
  draw();
}

async function failureDetail(res) {
  try {
    return (await res.json()).detail || res.statusText;
  } catch {
    return res.statusText;
  }
}

const HANDLERS = {
  async onLink() {
    // Comes back only if the page could not leave. A "redirecting" result
    // means the navigation is under way and anything drawn now would be drawn
    // on a page that is already going.
    const result = await beginGoogleLink({ returnTo: returnTo() });
    if (result && result.status === "failed") {
      redraw({ linkMessage: result.message });
    }
  },

  async onSignOut() {
    signOut();
    // The rail is redrawn because it is on screen beside this card and it
    // lists the previous session's rooms. refreshRail() goes back to the
    // server, which mints a fresh anonymous account on the way, so what comes
    // back is the new session's rail rather than a cleared copy of the old
    // one. The results panel is left alone: it is hidden behind this card and
    // the only route back into it is a rail room, which the redraw removes.
    await refreshRail(null);
    card = await readCard();
    draw();
  },

  async onIssue(label) {
    let body;
    try {
      const res = await authedFetch("/api/tokens", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: String(label || "").trim() }),
      });
      if (!res.ok) {
        redraw({ issueError: await failureDetail(res) });
        return;
      }
      body = await res.json();
    } catch {
      redraw({
        issueError:
          "The department could not be reached, so no token was issued. " +
          "Nothing here has changed.",
      });
      return;
    }

    // The new token is put at the head of the list this page already holds
    // rather than re-fetched, and that is deliberate: a re-fetch would be a
    // second render, and the plaintext lives on exactly one. The response
    // carries the same metadata shape GET returns, plus the one field that
    // will never appear again (star/server.py's create_token).
    const tokens = Array.isArray(card?.tokens) ? card.tokens : [];
    redraw({ issued: body, tokens: [body, ...tokens], tokensUnreadable: false });
  },

  async onRevoke(tokenId) {
    if (!tokenId) return;
    try {
      const res = await authedFetch(`/api/tokens/${encodeURIComponent(tokenId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        redraw({ issueError: await failureDetail(res) });
        return;
      }
    } catch {
      redraw({
        issueError:
          "The department could not be reached, so nothing was revoked. This " +
          "token still works.",
      });
      return;
    }
    // Re-read rather than patched locally: the revocation timestamp is the
    // server's, and stamping this browser's clock on it would be a fabricated
    // fact on the one row whose whole job is to record when something stopped
    // being usable.
    const { tokens, unreadable } = await readTokens();
    redraw({ tokens, tokensUnreadable: unreadable });
  },
};

/** Where beginGoogleLink is told to come back to.
 *
 *  Handed to web/auth.js, which filters it to a same-origin absolute path
 *  before stashing it, so a value from here can never become an open redirect.
 *  Guarded anyway: this module is imported in Node by its tests, where
 *  `location` does not exist. */
function returnTo() {
  try {
    return `${location.pathname}${location.search}`;
  } catch {
    return "/";
  }
}
