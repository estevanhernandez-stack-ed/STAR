# STAR — Technical Spec, cycle #19

> Vibe Cartographer cycle **#19**, `/spec`, 2026-08-10. Mode: fully-autonomous (*Autonomous — Self*).
> Persona: Architect. Deepening rounds: 0, per the builder's standing pattern when the substrate is
> understood. Primary inputs: [`docs/prd.md`](prd.md), [`docs/scope.md`](scope.md), and the
> architecture docs named in [`docs/builder-profile.md`](builder-profile.md) — which supersede the
> plugin's `architecture/default-patterns.md` and were used instead of it.
>
> Read live for this document: `star/server.py`, `star/auth.py`, `star/models.py`, `star/guards.py`,
> `star/config.py`, `star/store.py`, `star/ledger.py`, `star/findings.py`, `star/agents/*.py`,
> `star/tools/parallel_search.py`, `web/auth.js`, `web/shell.js`, `web/index.html`, `web/tokens.css`,
> `tests/test_js_auth.py`, `pyproject.toml`, `Dockerfile`, `.gcloudignore`, `scripts/deploy.sh`,
> [`.vibe-access/state/inventory.json`](../.vibe-access/state/inventory.json).
>
> Researched live rather than recalled: the MCP Streamable HTTP transport spec, the MCP `2026-07-28`
> release candidate, the `mcp` PyPI package's current ownership, Identity Platform's
> `accounts:signInWithIdp`, and Google's OpenID Connect response types. Links are in
> [Dependencies & external services](#dependencies--external-services).

## The line every component answers

*Every studio has a research department. Now every writer has one, and so does every agent they run.*

Two doors, one department, one ledger. If a component makes the two doors behave differently, it is
built wrong.

---

## Stack

Unchanged from what is built and deployed. No framework is added by this cycle, and **no dependency
is added to `pyproject.toml` at all** — see [Decision 1](#decision-1--the-mcp-server-is-hand-written-against-the-transport-spec-no-new-dependency).

| Layer | Choice | Why it stays |
| --- | --- | --- |
| Language | Python 3.12 (`FROM python:3.12.12-slim`) | Pinned to the interpreter both verified room builds ran on |
| Agents | `google-adk==2.6.2`, `google-genai==2.17.0` | Runtime AI is Google Cloud only. ADK's other-provider adapters are never used |
| Search | `parallel-web==1.1.0` | Partner-track pass/fail. Must genuinely execute at runtime |
| Web | `fastapi==0.141.1`, `uvicorn[standard]==0.52.1` | Already serving Pipeline A, SSE, and the static app |
| Identity | `firebase-admin==7.5.0` server-side; raw Identity Toolkit REST in the browser | No SDK in the browser, no CDN request |
| Persistence | `google-cloud-firestore==2.28.1` via ADC | Server owns every read and write. One security boundary |
| Frontend | Native ES modules, plain CSS, `web/vendor/` | No build step. No third-party browser request |
| Tests | `pytest`, `pytest-asyncio`, `ruff`, plus Node for `tests/js/*.mjs` | Established; `tests/test_js_auth.py` already shells out to Node |

Every version above is pinned exactly, and `pyproject.toml:9-14` records why: a Cloud Build runs a
fresh install and would otherwise take whatever shipped that morning. **This cycle does not move a
single pin.** Revisit after 2026-09-07.

### The one packaging change

`pyproject.toml` uses an **explicit** package list, not `find`:

```toml
[tool.setuptools]
packages = ["star", "star.agents", "star.tools", "research_dept"]
```

Adding `star/mcp/` means adding `"star.mcp"` to that list. Miss it and `pip install .` inside the
Cloud Build silently omits the package — the local venv keeps working (editable/source path), the
deployed image 500s on import. This is the single highest-value line in this document per character.

---

## Runtime & deployment

Unchanged shape: one Cloud Run service, one instance, serving the API, the SSE stream, the static
app, and now the MCP endpoint from the same process on the same origin.

| | |
| --- | --- |
| Service | `star`, project `star-research-dept`, region `us-central1` |
| Live URL | `https://star-390753828501.us-central1.run.app` |
| Deploy | `FIREBASE_API_KEY=$(...) bash scripts/deploy.sh` |
| Instances | `--max-instances=1 --min-instances=1 --no-cpu-throttling`, `--timeout=900` |

### Why the MCP server lives inside `star/server.py`

Not a preference. `_runs`, `_ip_limiter`, and `_daily_cap` are module-level in-memory state
(`star/server.py:55,80,85`), and `star/guards.py`'s module docstring plus `scripts/deploy.sh`'s
comment block both record what breaks when more than one process holds them. A second Cloud Run
service is a second process: the daily cap doubles, the per-caller limit doubles, and a live build's
SSE stream can land on an instance that never ran it. Anything that scales past one instance moves
all three to a shared store **in the same change**, and nothing this cycle needs justifies that.

So: one process, one FastAPI app, one set of counters. The MCP endpoint is a router on the app that
already exists.

### New environment variables

| Var | Kind | Where | Required? |
| --- | --- | --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` | Public identifier | `--set-env-vars`, served to the browser via `/config.js` | **No** — absent means linking is unavailable and the card says so |
| `STAR_MAX_SCENE_CHARS` | Tuning, default `8000` | Code default | No |
| `STAR_MAX_SEARCHES_PER_CHECK` | Tuning, default `8` | Code default | No |
| `STAR_CHECK_TIMEOUT_SECONDS` | Tuning, default `180` | Code default | No |
| `STAR_MCP_ALLOWED_ORIGINS` | Comma-separated, default = the service's own URL | `--set-env-vars` only if a second origin is needed | No |

**`GOOGLE_OAUTH_CLIENT_ID` deliberately does not join `config.validate_env()`.** That function
fails the boot on anything whose absence would be *silent* (`star/config.py:120-147`). This one's
absence is loud by design: `/config.js` serves `""`, the card renders the linking offer as
unavailable and says why, and every existing path still works. That is
`prd.md > Identity That Outlives The Browser`'s fourth criterion, satisfied by construction rather
than by a code path someone has to remember to write.

---

## Architecture overview

```
                        ┌───────────────────────────────────────────┐
   browser              │        Cloud Run · one instance           │
   (no build step)      │        uvicorn star.server:app            │
        │               │                                           │
        │  Bearer        │   ┌───────────────────────────────────┐   │
        │  Firebase ID   │   │  FastAPI routes                   │   │
        ├──────────────► │   │  /api/rooms      (browser door)   │   │
        │                │   │  /api/rooms/{id}/events  (SSE)    │   │
        │                │   │  /api/tokens     (card)           │   │
        │                │   │  /api/rooms/{id}/scenes  (check)  │   │
        │                │   │  /config.js                       │   │
        │                │   │  /mcp            (agent door) ────┼───┼──► MCP client
        │                │   └──────────────┬────────────────────┘   │    (harness /
        │                │                  │                        │     any agent)
        │                │        ┌─────────▼──────────┐             │    Bearer star_…
        │                │        │  shared admission  │             │
        │                │        │  _uid_limiter      │             │
        │                │        │  _ip_limiter       │             │
        │                │        │  _daily_cap        │             │
        │                │        └─────────┬──────────┘             │
        │                │                  │                        │
        │                │   ┌──────────────▼───────────────────┐    │
        │                │   │  _runs  (in-memory run registry) │    │
        │                │   │  ADK InMemoryRunner              │    │
        │                │   └──────┬──────────────┬────────────┘    │
        │                │          │              │                 │
        │                │   Pipeline A      Pipeline B              │
        │                │   build_room      check_scene             │
        │                └──────────┼──────────────┼─────────────────┘
        │                           │              │
   Identity Toolkit          Gemini (AI Studio)   Parallel Search
   accounts:signUp           via google-adk       via parallel-web
   accounts:signInWithIdp
   securetoken (refresh)                    Firestore (ADC, server-only)
                                            /users/{uid}/rooms/{run_id}
   accounts.google.com                      /users/{uid}/rooms/{id}/scenes/{sceneId}
   (OIDC, redirect only)                    /mcp_tokens/{token_id}
```

Three properties this diagram is asserting, each verifiable in code:

1. **Both doors converge before they spend.** `POST /api/rooms` and the MCP `build_room` tool call
   the *same* admission helper and the *same* run starter. They differ only in which limiter key
   they present.
2. **The browser never touches Firestore.** Unchanged from Phase 2, and the MCP door does not change
   it — an agent's bearer token is useful only against STAR's own API.
3. **The only permitted external browser calls are Google's identity endpoints.**
   `accounts.google.com` joins `identitytoolkit.googleapis.com` and `securetoken.googleapis.com` on
   that list. It is a *navigation*, not a fetch, and nothing is loaded from it — see
   [Decision 3](#decision-3--google-linking-is-a-full-page-oidc-redirect-with-responsetypeidtoken).

---

## Identity: linking without a gate

PRD ref: `prd.md > Identity That Outlives The Browser`.

### The flow

Anonymous stays the front door and nothing about `signUpAnonymously()` /`refresh()` in
`web/auth.js:27-46` changes. Linking is offered in exactly two places — the card, and the moment of
issuing a token — and never on the intake.

```
  card: "Attach a Google account"
        │
        │ 1. mint nonce + state, stash in sessionStorage with returnTo
        │    (and, if a run is live, stash {run_id, stream_key} too)
        ▼
  location.assign(
    https://accounts.google.com/o/oauth2/v2/auth
      ?client_id=<GOOGLE_OAUTH_CLIENT_ID>
      &response_type=id_token
      &scope=openid%20email%20profile
      &redirect_uri=<origin>/
      &nonce=<nonce>&state=<state>&prompt=select_account )
        │
        │ 2. Google redirects back with #id_token=…&state=…
        ▼
  web/auth.js completeGoogleLink()
        │  · compare state against sessionStorage; mismatch → abort, say so
        │  · history.replaceState to strip the fragment BEFORE anything else
        │
        │ 3. POST identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=<FIREBASE_API_KEY>
        │      { postBody: "id_token=<google>&providerId=google.com",
        │        requestUri: <origin>,
        │        idToken:    <current anonymous Firebase ID token>,   ← this is what links
        │        returnSecureToken: true, returnIdpCredential: true }
        ▼
  response { localId, idToken, refreshToken, … }
        │  · ASSERT localId === the uid we held before the redirect.
        │    A mismatch means we did not link, we switched. Abort, restore, say so.
        │  · remember(idToken, refreshToken, expiresIn)  ← existing web/auth.js:48
        │  · if a run was stashed, resume its EventSource via Last-Event-ID
```

`idToken` in the request body is the whole mechanism: *"If passed, the user's account at the IdP
will be linked to the account represented by this ID token."* The uid (`localId`) is preserved, so
the rail lists byte-identical rooms across the link — which is
`prd.md > Identity That Outlives The Browser`'s first linking criterion, and it is a property of
this one field.

### Build-blocking verification, before the epic's first line of code

Two claims above are read off documentation, not off a round trip. Both are load-bearing and both
are cheap to prove. This is the same discipline that caught the ADK response envelope on 2026-08-09
and it is a **checklist item, not a note**:

1. **Google still honours `response_type=id_token` for this client.** Documented under OpenID
   Connect as an implicit-flow response type; Google's own copy recommends Google Identity Services
   instead, which is precisely the remote `<script>` this project forbids. Prove it: open the
   authorize URL by hand against the real client id, confirm a `#id_token=` fragment comes back.
2. **`signInWithIdp` accepts a Google ID token minted outside Firebase's own handler, carrying a
   nonce Firebase did not issue.** Prove it: one `curl` with a real anonymous `idToken` and that
   `id_token`, and confirm `localId` comes back unchanged.

If (2) fails on the nonce, the first retry is adding `&nonce=<raw nonce>` to `postBody`. If both
fail, the named fallback is the **server-side authorization-code exchange**: register the client as
a Web application, put `GOOGLE_OAUTH_CLIENT_SECRET` in Secret Manager, add
`GET /api/auth/google/callback` which exchanges `code` at `https://oauth2.googleapis.com/token` and
redirects to `/#g=<google id token>` — a fragment, so it never reaches an access log or a `Referer`.
The browser then completes `signInWithIdp` exactly as above. One endpoint, one secret, one extra
redirect. **Do not build it unless the verification fails.**

Rejected without building: driving Firebase's hosted `__/auth/handler` by hand. It is the JS SDK's
private plumbing, it is undocumented as a public contract, and a silent change to it during
submission week is exactly the class of failure the no-CDN rule exists to prevent.

### Error mapping

Every branch below produces its own message. `prd.md` requires the message to name *which* failure
happened, so a generic "linking failed" fails the criterion.

| Signal | What the reader is told | Session state after |
| --- | --- | --- |
| `FEDERATED_USER_ID_ALREADY_LINKED` | This Google account is already attached to a different set of rooms. Offer to sign in as that account instead, and say in the same breath that the rooms currently on screen would not come along | Untouched. Never switch silently |
| `EMAIL_EXISTS` | Same shape as above | Untouched |
| `CREDENTIAL_TOO_OLD_LOGIN_AGAIN` | The sign-in took too long. Start the link again | Untouched |
| `INVALID_IDP_RESPONSE` / bad state / no fragment | The sign-in did not come back cleanly. Nothing changed | Untouched |
| Network failure on `signInWithIdp` | The department could not reach the sign-in service. Nothing changed | Untouched |
| `localId` ≠ pre-link uid | Hard abort. This is a switch, not a link | Restore prior refresh token; never persist the new one |
| Redirect never returns (user backs out) | Nothing. No error state on screen | Untouched |

### Sign-out

A linked user signing out returns to a fresh anonymous session with an empty rail. The card says so
*before* it happens — this is the one destructive-looking control on the surface and it must not
read as data loss. Implementation: `safeRemoveStored()`, clear in-memory `idToken`/`expiresAt`, then
`getIdToken()` mints a new anonymous account on the next call.

### The redirect that abandons a live run

`{run_id, stream_key}` live in `web/app.js` page memory only, so a redirect during a build comes
back unstreamable. The run itself survives: the asyncio task keeps going and `_persist` writes at
terminal status. Fix, per `prd.md`:

- Before `location.assign`, stash `{run_id, stream_key, last_event_id}` in `sessionStorage`.
- On load, if the stash is present and the run is not terminal, reopen the `EventSource` and let
  `Last-Event-ID` resume — `star/server.py:694-712` and `_resume_cursor` already serve exactly this,
  and `_resume_cursor` already clamps a cursor past the tip rather than going dark.
- `EventSource` sets `Last-Event-ID` itself on *automatic* reconnects, but not on a fresh
  construction after a page load. So the stashed id is passed explicitly and the client replays from
  it. Track the last seen id in `app.js`'s existing event handler.

Declining to offer the link during a run is the weaker alternative and is explicitly not the
requirement.

---

## The card: the account surface

PRD ref: `prd.md > Identity That Outlives The Browser`, third story.

### Naming

`prd.md > Open questions` #5 asks what this surface is called; "account settings" is the wrong
register. **Proposal: "Your card."** In a morgue the reader has a card — who you are, and what has
been issued in your name. It is the vocabulary already in force (drawer plates, folder tabs,
receipts, stamps) and it describes the surface literally rather than dressing it. Rail entry reads
`Your card`, in `--pencil`, at the bottom of the rail below the room list.
*One line to override — this is a naming call, not a structural one.*

### Structure

A **fourth stage state**, not a page and not a modal. `web/shell.js` gains `showAccount()` alongside
`showIntake()` / `showRunning()` / `showRoom()`, and `index.html` gains `#account-panel` as a fourth
`.panel` inside `<main class="stage">`.

The reason a separate `web/account.html` was rejected is worth keeping visible: the StaticFiles
mount at `/` (`star/server.py:783`) would serve it for free, but every visit would pay a cold auth
bootstrap, and that path carries the intermittent 401 documented at length in `web/auth.js:145-204`.
One fewer surface that can hit that bug is worth more than the separation.

Reachable from every stage state including mid-run, and reaching it does not disturb a live run's
stream — `showAccount()` only toggles panel visibility; the `EventSource` in `app.js` is untouched.

### What it shows

```
+---------------------------------------------------------------+
|  YOUR CARD                                                    |
|                                                               |
|  IDENTITY                                                     |
|  Not attached to an account.                                  |
|  Your rooms live with this browser. Attach a Google account   |
|  and they stop doing that — reachable from any browser, and   |
|  from any agent holding a token you issue.                    |
|                          [ Attach a Google account ]          |
|                                                               |
|  ISSUED TOKENS                                                |
|  A token lets an agent reach this department as you. The      |
|  token is shown once, here, and never again.                  |
|                                                               |
|  desktop agent      ISSUED 2026-08-14   LAST USED 2026-08-19  |
|                                              [ Revoke ]       |
|                                                               |
|  [ Issue a token ]   (disabled while unattached, with the     |
|                       reason stated, not just greyed out)     |
+---------------------------------------------------------------+
```

Copy rules that bind here as everywhere: never the bare word "verified" about a source; never a
duration promise; state what is stored before the reader acts.

### Endpoints

Three, each guarded by `_require_uid` (`star/server.py:88`). Linking needs no endpoint — it is
client-side against Identity Toolkit.

| Route | Returns | Notes |
| --- | --- | --- |
| `POST /api/tokens` | `{token_id, token, label, created_at}` | `token` is the plaintext, **the only time it exists on the wire**. 403 if the uid is not linked |
| `GET /api/tokens` | `{tokens: [{token_id, label, created_at, last_used_at, revoked_at}]}` | Metadata only. Never the token, never the hash |
| `DELETE /api/tokens/{token_id}` | `204` | Soft revoke. 404 if the token is not this uid's — no oracle, matching `get_room` |

**A token can only be issued to a linked identity.** `POST /api/tokens` reads the verified claims,
not just the uid: `firebase_auth.verify_id_token` returns `firebase.sign_in_provider`, and
`anonymous` is refused with a message naming the reason. This is the coupling that puts Part 1 ahead
of Part 3 — an anonymous account's only proof of ownership is a `localStorage` entry, so a
long-lived token pointing at one is a credential to an account nobody can recover.

This requires one addition to `star/auth.py`: a `verify_claims(header) -> dict | None` that returns
the claim dict, with `verify_token` reduced to `verify_claims(...)["uid"]`. Same swallow-everything
contract, same log line, no behaviour change to any existing caller.

---

## MCP tokens

PRD ref: `prd.md > The Department Over MCP`, first story.

### Format

```
star_<token_id>.<secret>
      12 hex      32 hex
```

Two parts, deliberately. `token_id` is an identifier that appears in URLs, logs, and the card;
`secret` is a credential. They should not have the same entropy or the same exposure, which is the
same argument `star/server.py:601-620` already makes for `run_id` versus `stream_key`.

### Storage

One document, not two. `/mcp_tokens/{token_id}`:

| Field | Type | Notes |
| --- | --- | --- |
| `uid` | string | The account this token acts as |
| `secret_sha256` | string | `hashlib.sha256(secret.encode()).hexdigest()`. The plaintext is never stored |
| `label` | string | Reader-supplied, capped, escaped on render |
| `created_at` | ISO string | |
| `last_used_at` | ISO string \| null | Written at most once per 60s per token — see below |
| `revoked_at` | ISO string \| null | Soft delete, because a revoked token must be *told* it was revoked |

**Why a top-level collection and not `/users/{uid}/tokens/{id}`.** Authentication has only the token
in hand; it does not know the uid yet. A top-level collection makes the auth lookup a single
`get()` by document id — O(1), no query, no index, no collection-group scan. Listing the card's
tokens is `where("uid", "==", uid)`, which Firestore's automatic single-field index already serves;
sorting is done in Python because N is small and a composite index is a deploy artifact this project
does not otherwise have. The mirrored-document alternative (`/users/{uid}/tokens` **and** a hash
index) was rejected: two documents means revoke can half-apply, and a half-revoked credential is
worse than a slow list.

**`last_used_at` throttling.** A Firestore write per MCP call is a write per agent poll, and
`get_room` is a polling endpoint by design. Write only when the stored value is more than 60s old.
Off the event loop via `asyncio.to_thread`, same as every other Firestore call in the server
(`star/server.py:641,724,750`).

### Verification

```python
def resolve(header: str | None) -> TokenIdentity | Refusal
```

1. `extract_bearer(header)` — reuse `star/auth.py:102`, already pure and already tested.
2. Split once on `.`. Wrong shape → generic refusal.
3. `get()` `/mcp_tokens/{token_id}`. Absent → generic refusal.
4. `hmac.compare_digest(sha256(secret), stored.secret_sha256)`. Mismatch → generic refusal.
5. `revoked_at` set → **the revoked refusal**, which says it was revoked.
6. Otherwise → `TokenIdentity(uid, token_id)`, and schedule the throttled `last_used_at` write.

Steps 2-4 collapse to one message with no distinguishing detail, matching `star/auth.py:119-145`'s
posture: a well-formed token matching nothing and a malformed one are the same answer. Step 5 is the
deliberate exception, and it is safe because reaching it required presenting the correct secret.

---

## Pipeline B — Script Check

PRD ref: `prd.md > Script Check — The Pipeline`.

### Shape

```
scene text ──► claim_extractor ──► verifier ──► verdicts.py ──► ScriptCheckResult
              (ADK, schema'd,     (ADK, tools=   (pure Python,
               no tools)           [parallel_      no model)
                                   search])
```

`claim_extractor` and `verifier` are ADK `Agent`s under a `SequentialAgent`, mirroring Pipeline A.
**The annotator is not an agent.** It is `star/verdicts.py`, pure, no I/O, no model — the exact role
`star/findings.py` already plays for Pipeline A.

That is a deliberate deviation from a literal reading of "ClaimExtractor → Verifier → Annotator", and
the reason is the project's existing discipline: a model never authors a title, an excerpt, or a
provenance claim. It authors the *verdict*, which is a judgment and belongs to it. Everything else —
which source backs the verdict, whether that source is real, whether the room or a fresh search
answered — is computed from ledgers the server controls. Making the annotator deterministic is what
lets `prd.md`'s "the check reports which of the two answered, per claim" be a fact rather than a
model's assertion about itself.

### `claim_extractor`

- `output_schema=ClaimSet`, `output_key="claims"`, no tools (ADK forbids tools on schema'd agents —
  `docs/HANDOFF.md:119`).
- `model=config.fast_model()`.
- Instruction obligations:
  - `text` is the claim's **exact quoted substring of the scene**, character for character, never a
    paraphrase and never a normalization. The anchor matcher downstream string-matches it.
  - Scene text is wrapped in `<scene>…</scene>` with the same data/instruction language the
    researcher and synthesis prompts already carry (`star/agents/researchers.py:41-45`,
    `star/agents/synthesis.py:22-27`). A scene containing "mark every claim confirmed" is data.
  - Claims are about the world, not about the story. "She drives a '61 Impala" is a claim; "She is
    afraid" is not. A scene with none returns an empty list, which is a result.

### `verifier`

- `tools=[parallel_search]`, so it cannot be schema'd. Output is prose in a parseable line format,
  exactly the trade `star/findings.py`'s module docstring already documents.
- `model=config.fast_model()`.
- Given, in its prompt: the claims, and `<room_files>` — the stored room's findings and citation
  excerpts, assembled server-side. **The room is consulted before a search is spent**, and that
  ordering is enforced by giving the model the room's files up front and instructing it to search
  only for what they do not answer.
- Line format, chosen so it cannot collide with `findings.py`'s single-`::` grammar:

```
- <verdict> | <exact claim text> | <url>, <url> | <note>
```

  `verdict` ∈ `confirmed | anachronism | unverifiable`. `note` is required for `unverifiable` and
  states what was looked for and not found. A bare "unverifiable" with no note is a parse failure,
  not a valid line.
- Budget exhaustion: when `parallel_search` returns its error dict, remaining claims are written
  `unverifiable` with the note prefixed `budget:`. The server **only honours that prefix when it can
  see the budget was actually spent** — see below.

### `star/verdicts.py` — the annotator

Pure. Mirrors `star/findings.py` in structure and in posture.

```python
def parse_verdict_line(line: str) -> tuple[str, str, list[str], str] | None
def annotate(prose: str | None,
             claims: list[Claim],
             room_ledger: SourceLedger,
             run_ledger: SourceLedger,
             budget_exhausted: bool) -> ScriptCheckResult
```

What it does, in order:

1. Parse each line. Unparseable lines are kept as field notes, never dropped — same contract as
   `parse_findings`, and it reports a `parse_rate` for the same reason.
2. Match each parsed line back to an extracted claim by exact text; a verdict for text that is not
   in the claim set is field notes, not a claim.
3. Hydrate every cited URL through `_resolve_citation` (reused verbatim from `findings.py`, so the
   truncated-URL recovery ladder applies here too) against **`room_ledger` first, then
   `run_ledger`**. Whichever ledger answers is recorded per citation as `source: "room" | "search"`.
4. A URL in **neither** ledger is not a citation. It becomes `unsourced_urls`, the claim is stamped
   `UNSOURCED` in oxide, and the claim stays on screen. A verdict never leans on a citation that
   came from nowhere.
5. A `confirmed` or `anachronism` with zero hydrated citations is downgraded to `unverifiable` with
   a note saying the source it named could not be checked. `prd.md` requires every one of those two
   verdicts to carry at least one real citation; this is where that becomes true rather than hoped
   for.
6. `budget:`-prefixed notes are honoured only when `budget_exhausted` is true. Otherwise the prefix
   is stripped and the note stands as an ordinary not-found. Conflating "we ran out of money" with
   "we looked and it isn't there" is the same class of overclaim the ledger check exists to prevent,
   and the model is not the authority on which one happened.
7. Every claim that received no verdict line at all comes back `unverifiable` with a note saying the
   check did not reach it. Nothing is silently dropped.

### The two ledgers

`room_ledger` is reconstructed from the stored room document. `star/ledger.py` gains one function:

```python
def ledger_from_room(document: dict) -> SourceLedger
```

It walks `categories[*].findings[*].citations[*]` and calls the existing `SourceLedger.record()` with
`agent=f"room:{category}"` and `[{"url":…, "title":…, "excerpts":[excerpt]}]`. No new accumulation
logic; `record()` already merges by URL and dedupes excerpts.

`run_ledger` is a fresh `SourceLedger` fed by the same server-side path Pipeline A uses: the check's
event loop records `event.get_function_responses()` into it (`star/server.py:353-358`). Identical
mechanism, identical trust properties.

### Budget and time

| Knob | Value | Why |
| --- | --- | --- |
| `config.max_searches_per_check()` | 8 | A check is not a build. Eight live searches is generous for a scene |
| `config.check_timeout_seconds()` | 180 | Under Cloud Run's 900s request timeout with room to spare |
| `config.max_scene_chars()` | 8000 | Matches the treatment cap at `star/server.py:570-575`, roughly four script pages. *(default — confirm on next interactive run)* |

`parallel_search`'s budget is currently read straight from `config.max_searches_per_build()`
(`star/tools/parallel_search.py:87-100`). One two-line change makes it session-driven:

```python
budget = tool_context.state.get("search_budget") or config.max_searches_per_build()
```

and the check pipeline seeds `state={"search_budget": config.max_searches_per_check()}` when it
creates its ADK session. The module-level fallback path for direct script calls is untouched.

### Synchronous, not streamed

A check runs in one request. `POST /api/rooms/{run_id}/scenes` awaits the pipeline under
`asyncio.wait_for(..., check_timeout_seconds())` and returns the result. No `run_id`, no
`stream_key`, no SSE, no entry in `_runs`.

The reason: a build is 146s to 420s+ and would break any client that waited; a check is one
extraction plus one verification with at most eight searches. Making it synchronous keeps the entire
run-registry, capability-key, resume-cursor surface out of Pipeline B — that surface is the most
intricate thing in `server.py` and it exists to solve a problem Pipeline B does not have. It also
makes `check_scene` a normal, blocking MCP tool, which is what an agent expects.

The browser shows a working state with no ETA (obligation 6). `--no-cpu-throttling` already keeps
CPU allocated for the whole open request.

### Endpoints

| Route | Guard | Notes |
| --- | --- | --- |
| `POST /api/rooms/{run_id}/scenes` | `_require_uid` | Body `{scene}`. Runs the check, persists it, returns `ScriptCheckResult` |
| `GET /api/rooms/{run_id}/scenes` | `_require_uid` | Summaries for the room |
| `GET /api/rooms/{run_id}/scenes/{scene_id}` | `_require_uid` | A filed check, replayable without re-running |
| `DELETE /api/rooms/{run_id}/scenes/{scene_id}` | `_require_uid` | Deletes the document, and with it the stored scene text |

A room belonging to another uid returns the same not-found answer as a room that does not exist —
the read goes through `_store.get(uid, run_id)`, which is already scoped by uid, so this holds by
construction rather than by an added check.

**Scene retention is disclosed above the input, before the paste.** The scene text *is* stored,
which is strictly more sensitive than the treatment the intake copy promises not to store. Delete is
the reason this is defensible, and it is one endpoint and one control.

---

## The marked scene

PRD ref: `prd.md > Script Check — The Marked Scene`. This is GUI Phase 4 from
`docs/superpowers/specs/2026-08-09-star-gui-design.md:387-389`.

### Where it lives

A mode toggle in the room header, not a separate place — its value is being checked *against this
room*. Same stage state as the room (`showRoom()`), a new section below the docket.

### Verdict colours

| Verdict | Token | Source of truth |
| --- | --- | --- |
| `confirmed` | `--aniline` `#5C3D91` | `DIRECTION.md:111` — filed and verified |
| `anachronism` | `--oxide` `#B3341F` | `DIRECTION.md:112` — "and later the anachronism verdict" |
| `unverifiable` | `--pencil` `#7E8B7F` | `DIRECTION.md:113` — "a clip nobody got around to stamping" |
| `UNSOURCED` stamp | `--oxide` | Same stamp Pipeline A already presses |

The GUI spec's line "confirmed green, anachronism red, unverifiable dim"
(`2026-08-09-star-gui-design.md:265`) is stale — `DIRECTION.md`'s palette contains no green, and the
Phase 3 plan established that DIRECTION supersedes the spec wherever they disagree. Tokens are
already defined in `web/tokens.css:55-83`; nothing new is added to the palette.

### `web/anchor.js` — pure, and the one piece with real algorithmic risk

```js
export function anchor(scene, claims) -> { segments, unanchored }
```

`segments` is a flat, ordered list of `{text}` and `{text, claim}` — never HTML. The renderer walks
it with `document.createTextNode` and real `<mark>` elements. **Never** by building an HTML string
from scene text: this is where the H1 XSS returns through a different door
(`2026-08-09-star-gui-design.md:312-318`).

Algorithm:

1. **Exact pass.** For each claim, find *every* occurrence of `claim.text` in the raw scene.
2. **Normalized pass**, only for claims with zero exact hits. Build a normalized scene (collapse
   runs of whitespace to one space, casefold) alongside an index map from each normalized character
   back to its raw index. Search the normalized claim text in it, then map matches back to raw
   spans. This is what makes whitespace and case misses recoverable without trusting offsets.
3. **Overlap resolution.** Collect all candidate spans, sort by length descending, and accept a span
   only if it does not intersect an already-accepted one. Longest match wins the mark; the loser
   goes to `unanchored`. Nested or broken spans are a defect, not a degraded state.
4. **Unanchored.** Anything with no span at all is returned in `unanchored` and rendered in the rail
   without a mark. A verdict is never lost because it could not be placed.

Every occurrence of a repeated quote gets marked, per `prd.md > Decisions this PRD makes` #6 — the
extractor gives text, not offsets, so marking one occurrence would assert a position we do not know.

### The citation rail

Follows the selected mark. Each citation clicks through to the real ledger excerpt, with
`target="_blank" rel="noopener noreferrer"` — the same treatment `web/app.js`'s `makeLinksSafe`
already applies. Every citation carries whether the **room** or a **fresh search** answered, because
that distinction is the department consulting its own files and it is worth showing.

Keyboard focus is visible on every mark. `prefers-reduced-motion` is honoured — `web/tokens.css:110`
already zeroes `--stamp-duration` under it, so the stamp press inherits it for free. Below 900px the
scene and rail stack to one column, matching the room's existing collapse.

---

## The department over MCP

PRD ref: `prd.md > The Department Over MCP`.

### Transport

A single endpoint, `POST /mcp` (plus `GET`/`DELETE` for spec conformance), served by the same
FastAPI app on the same origin. Streamable HTTP, JSON responses only.

What the transport spec requires of a server that exposes tools and nothing else:

| Requirement | What STAR does |
| --- | --- |
| Single endpoint supporting POST and GET | `POST /mcp` answers; `GET /mcp` returns **405**, which the spec names as the correct answer for a server offering no server-initiated SSE stream |
| POST of a JSON-RPC *request* | Responds `Content-Type: application/json` with one JSON object. SSE is explicitly optional and STAR does not use it |
| POST of a JSON-RPC *notification* or *response* | **202 Accepted, no body.** This is what `notifications/initialized` gets |
| `Origin` validation | If present and not in `STAR_MCP_ALLOWED_ORIGINS`, **403**. Non-browser clients send no `Origin` and pass |
| `MCP-Protocol-Version` header | Absent → assume `2025-03-26`, per the spec's backwards-compatibility rule. Present and unsupported → **400** |
| Session management | Optional (`MAY`). STAR issues no `MCP-Session-Id` and requires none — the server is stateless per request, which is also what the `2026-07-28` release candidate assumes |
| `DELETE /mcp` | **405**, which the spec names as the correct answer for a server that does not let clients terminate sessions |

Accepted protocol versions: `2025-03-26`, `2025-06-18`, `2025-11-25`, `2026-07-28`. STAR advertises
`2025-11-25` — the current stable revision — in its `InitializeResult`. Because the tool surface
carries no resources, prompts, sampling, roots, or logging, a stateless tools-only server satisfies
both the stable revision and the `2026-07-28` release candidate that removes the handshake
altogether: a client that sends `initialize` gets a correct result, and a client that never sends
one is served anyway.

### Methods implemented

| Method | Response |
| --- | --- |
| `initialize` | `{protocolVersion, capabilities:{tools:{}}, serverInfo:{name,version}, instructions}` |
| `notifications/initialized` | 202, no body |
| `ping` | `{}` |
| `tools/list` | The four tools |
| `tools/call` | `CallToolResult` |
| anything else | JSON-RPC error `-32601`, method not found |

`instructions` on the initialize result is not filler — it is where the department explains itself
to a reader with no screen: that a build takes minutes and returns a `run_id` to poll, that citations
are hydrated from what search actually returned, and that a scene is stored with its room.

### Authorization

`Authorization: Bearer star_<token_id>.<secret>`, checked **before** any JSON-RPC parsing, including
before `initialize`. A refusal is `401` with `WWW-Authenticate: Bearer` and a JSON-RPC error body.

The honest limitation, stated because it constrains which clients can connect: MCP's authorization
spec expects OAuth 2.1 with protected-resource metadata discovery, and STAR ships none — `prd.md`
cuts the authorization server explicitly, following the estate precedent where the cheap path
shipped first. So STAR works with any client that can be configured with a static bearer header,
which includes the in-repo persona harness that is this surface's primary consumer, and does not
work with a client that insists on discovering an authorization server. That is a known cost, not an
oversight, and the successor is named in `prd.md > What we'd add with more time`.

### The four tools

Descriptions are written for a reader who cannot see a screen: what it does, what it needs, what it
returns, what it costs.

**`list_rooms`** — *Lists the research rooms filed under your account, newest first. Returns each
room's id, title, era, status, filing date, and how many searches it cost. Costs nothing and is not
rate-limited. Start here when you do not already have a room id.*

**`get_room`** — *Reads one filed room by id: the story profile, the research plan, the four
category drawers with their findings and citations, and the research bible. Also the poll for
`build_room` — a room still being built returns `status: "running"` with the progress so far, never
an error and never a blocking wait. Statuses are `running`, `complete`, `partial`, `error`,
`interrupted`. Costs nothing and is not rate-limited.*

**`build_room`** — *Starts a research build from a treatment and returns a `run_id` immediately. The
build takes several minutes; poll `get_room` with the `run_id` about every 15 seconds until the
status is not `running`. Treatments must be between 40 and 8000 characters. Each build spends real
money on live web searches and counts against both your hourly limit and the department's shared
daily budget.*

**`check_scene`** — *Checks a scene's real-world claims against a room you have already built.
Returns each claim with a verdict of `confirmed`, `anachronism`, or `unverifiable`, the sources
behind it, and whether the room's own files or a fresh search answered. **The scene text is stored
with the room** and can be deleted later. Requires a room id from `list_rooms` or `build_room`.
Spends a small number of live searches.*

There is **no fifth tool.** `get_room` is `build_room`'s poll, which resolves the largest unknown
`scope.md` named, using the shape `star/server.py:728-766` already serves.

### Error strings

Every refusal an agent will actually hit gets its own message naming what failed and what to do
next. A bare status code, a bare "invalid request", or a stack trace fails the criterion.

| Refusal | Message shape |
| --- | --- |
| No token | Authorization header missing. Issue a token from Your card in the web app and send it as `Authorization: Bearer star_…` |
| Bad or unknown token | This token was not recognised. Issue a new one from Your card |
| Revoked token | This token was revoked. Issue a new one from Your card |
| Room not found | No room with that id is filed under this account. Call `list_rooms` for the ids you can read |
| Treatment too short | Names the 40-character floor and asks for era, place, and what the characters do |
| Treatment too long | Names the 8000-character cap and the number of characters that were sent |
| Scene too long | Same shape, naming `max_scene_chars` |
| Per-user limit reached | Names the ceiling and the window, and says reads are still free |
| Daily cap reached | Names the shared budget and says to try tomorrow. Reads are still free |
| Run still building | Not an error. `get_room` returns `running` with progress |
| Run interrupted | The run did not survive a restart and will not finish. Its filed findings, if any, are readable |

Tool-level failures come back as `CallToolResult{isError: true}` so the calling model can read and
act on them. JSON-RPC error objects are reserved for protocol-level failures — unknown method,
malformed params — which are a client bug, not something a model should try to recover from.

### Rate limiting: per uid, not per IP

PRD ref: `prd.md > The Department Over MCP`, fourth story.

`_ip_limiter`'s key comes from `X-Forwarded-For`'s rightmost entry (`star/server.py:105-141`). For an
MCP client that is one address, and a desktop agent behind CGNAT could share it with strangers. So
the MCP door keys on uid:

```python
_uid_limiter = RateLimiter(
    max_per_window=config.max_rooms_per_ip_per_hour(),   # same ceiling, 5/hour
    window_seconds=3600,
    max_keys=config.max_rate_limiter_keys(),
)
```

Same class, same ceiling, same `max_keys` bound — and `max_keys` matters here for the reason
`star/guards.py:31-54` documents: the stale-key sweep is O(n) on every `check()` and runs on the
single-threaded loop every open SSE stream shares.

Both doors then hit the **same** `_daily_cap`. One budget, one ceiling, one kill switch.

**Order is load-bearing and is the same order Finding 3 established** (`star/server.py:576-590`): the
free in-memory per-caller check runs first, and `_daily_cap.check()` — which *increments* on the
allow path — is the last thing before the build is admitted. Getting this backwards once already
cost a whole day's budget in about two seconds.

Reads (`list_rooms`, `get_room`) are not build-rate-limited. They cost nothing to answer.

### How the two doors share one code path

The MCP tools do not reimplement anything. `star/server.py` grows four transport-free helpers next
to the handlers that already use them, and the router receives them by injection:

```python
# star/server.py, declared BEFORE app.mount("/")
from star.mcp.router import build_mcp_router

app.include_router(build_mcp_router(
    start_build   = _start_build,     # (uid, treatment, gate) -> run_id
    read_room     = _read_room,       # (uid, run_id) -> {status, result}
    list_rooms_for= _list_rooms_for,  # (uid) -> [summary]
    run_check     = _run_check,       # (uid, run_id, scene) -> ScriptCheckResult
    resolve_token = tokens.resolve,
))
```

`POST /api/rooms` becomes `_require_uid` + `_start_build(uid, treatment, gate=ip_gate)`. The MCP
tool is `_start_build(uid, treatment, gate=uid_gate)`. They are the *same function object*, so
"one budget, one ceiling" is mechanical rather than asserted.

**The rejected alternative, and why.** The tidier factoring is a new `star/service.py` holding
`_runs`, the guards, the runner, and the whole `_execute` / `_run_pipeline` / `_salvage` /
`_persist` / `_evict_old_runs` family, with `server.py` reduced to handlers. It is better
architecture and it is the wrong call 26 days out: that family is the most heavily reviewed code in
the repo, its comments carry the reasoning behind four separate incidents, and moving it churns a
1,406-line test file for zero behavioural gain. Injection buys the same property with no movement.
Revisit after 2026-09-07, when it is a refactor rather than a risk.

---

## The persona harness

PRD ref: `prd.md > The Persona Harness`. This is the only part of the MCP surface a judge can verify
in the repo rather than take on faith, and it is also the video's MCP shot.

- **`harness/client.py`** — a minimal MCP client over HTTPS. `urllib.request` from the standard
  library; no new dependency, and nothing third-party in the frame. Sends `initialize`,
  `tools/list`, `tools/call`; carries the bearer token; records every request and response.
- **`harness/personas.py`** — three postures, per `prd.md`: a writer who knows what they want, an
  agent that gets the arguments wrong, and one starting from an empty account with no rooms.
  *(default — confirm on next interactive run)*
- **`harness/run.py`** — drives a persona with Gemini via `google-genai`, translating `tools/list`
  into `types.FunctionDeclaration`s and looping tool calls. Runtime AI stays Google-only.
- **`harness/runs/*.md`** — committed transcripts: calls made, errors hit, verdicts returned.

The bar this exists to measure: **every failure a persona could not diagnose from the response alone
is either fixed or written down with the reason it stands.** That is the tool-description criterion
made checkable.

`harness/` is not part of the deployed service. The `Dockerfile` copies only `star/`,
`research_dept/`, and `web/`, so it is excluded already — but add `harness/` to `.gcloudignore`
alongside `tests/` and `scripts/` so the source upload does not carry it either.

---

## Data model

### Firestore

```
/users/{uid}/rooms/{run_id}                      ← unchanged
    run_id, status, created_at, title, era, genre,
    story_profile, research_plan, research_bible,
    search_count, source_count, categories

/users/{uid}/rooms/{run_id}/scenes/{scene_id}    ← NEW
    scene_id       str
    created_at     ISO str
    scene          str      the pasted text. Deletable, and disclosed before the paste
    claims         [ClaimResult]
    parse_rate     float
    unsourced_count int
    field_notes    str
    search_count   int
    budget_exhausted bool

/mcp_tokens/{token_id}                            ← NEW, top-level
    uid, secret_sha256, label, created_at, last_used_at, revoked_at
```

### New Pydantic models in `star/models.py`

`Claim` and `Verdict` already exist at `star/models.py:83-98` and are still unused by anything that
runs. This cycle is what uses them.

```python
class ClaimSet(BaseModel):          # claim_extractor's output_schema
    claims: list[Claim]

class ClaimResult(BaseModel):       # one annotated claim
    text: str                       # exact scene substring
    claim_type: str
    verdict: Verdict
    note: str = ""
    citations: list[Citation] = []
    citation_sources: list[str] = []   # "room" | "search", parallel to citations
    unsourced_urls: list[str] = []
    reason: str = ""                   # "" | "budget" | "unreached"

class ScriptCheckResult(BaseModel):
    scene_id: str
    created_at: str
    claims: list[ClaimResult]
    parse_rate: float = 0.0
    unsourced_count: int = 0
    field_notes: str = ""
    search_count: int = 0
    budget_exhausted: bool = False

class McpToken(BaseModel):          # metadata only. Never carries the secret
    token_id: str
    label: str
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None
```

`ClaimResult.verdict` is non-optional where `Claim.verdict` is optional: a claim before verification
has no verdict, a claim after it always does. Two types, because they are two states.

---

## File structure

```
STAR/
├── star/
│   ├── server.py            ~1100 lines after this cycle. FastAPI app, SSE, and now:
│   │                          POST/GET/DELETE /api/tokens
│   │                          POST/GET/DELETE /api/rooms/{id}/scenes
│   │                          _start_build / _read_room / _list_rooms_for / _run_check
│   │                          _uid_limiter, and the injected MCP router (before the mount)
│   ├── auth.py              + verify_claims(); verify_token becomes a thin wrapper
│   ├── tokens.py            NEW  mint / hash / resolve / list / revoke. Pure shaping + store calls
│   ├── verdicts.py          NEW  parse verifier prose, hydrate against two ledgers. Pure
│   ├── ledger.py            + ledger_from_room(document) -> SourceLedger
│   ├── findings.py          unchanged; _resolve_citation and _best_excerpt are imported by verdicts
│   ├── models.py            + ClaimSet, ClaimResult, ScriptCheckResult, McpToken
│   ├── store.py             + scene CRUD, token CRUD. Still the only module touching Firestore
│   ├── guards.py            unchanged. RateLimiter is instantiated a second time, not modified
│   ├── config.py            + max_scene_chars, max_searches_per_check, check_timeout_seconds,
│   │                          mcp_allowed_origins
│   ├── agents/
│   │   ├── script_check.py  NEW  claim_extractor, verifier, check_scene SequentialAgent
│   │   ├── pipelines.py     + export check_scene
│   │   └── (intake, planner, researchers, synthesis — unchanged)
│   ├── tools/
│   │   └── parallel_search.py  budget read from session state, falling back to the build default
│   └── mcp/                 NEW package — add "star.mcp" to pyproject's packages list
│       ├── __init__.py
│       ├── protocol.py      Pure: JSON-RPC envelope, version negotiation, error objects
│       ├── tools.py         The four tool schemas + dispatch onto the injected callables
│       └── router.py        APIRouter: bearer auth, Origin check, POST/GET/DELETE /mcp
├── web/
│   ├── index.html           + #account-panel, + script-check section, + rail card entry
│   ├── auth.js              + beginGoogleLink / completeGoogleLink / signOut / linkedProvider
│   ├── shell.js             + showAccount(); rail gains the card entry at its foot
│   ├── account.js           NEW  the card: identity, link offer, token issue/list/revoke
│   ├── scriptcheck.js       NEW  paste, run, render the marked scene and the citation rail
│   ├── anchor.js            NEW  pure. Exact → normalized → overlap resolution
│   ├── app.js               + sessionStorage run stash, + Last-Event-ID resume on load
│   ├── account.css          NEW
│   ├── scene.css            NEW
│   └── (tokens, shell, drawer, clip, bible .css — unchanged)
├── harness/                 NEW — not deployed; added to .gcloudignore
│   ├── client.py            urllib-based MCP client
│   ├── personas.py          three postures
│   ├── run.py               Gemini-driven loop via google-genai
│   └── runs/                committed transcripts, the repo-verifiable evidence
├── tests/
│   ├── test_tokens.py       NEW  mint/hash/resolve/revoke, generic-vs-revoked refusals
│   ├── test_verdicts.py     NEW  parse, hydrate, provenance, downgrade, budget honesty
│   ├── test_mcp_protocol.py NEW  envelope, version negotiation, 202/405/400/403 conformance
│   ├── test_scenes.py       NEW  scene endpoints, cross-uid isolation, delete removes text
│   ├── test_server.py       + token, scene, and MCP route coverage
│   └── js/
│       ├── test_anchor.mjs  NEW  paraphrase, whitespace, case, repeat, overlap
│       └── test_account.mjs NEW  link error mapping, uid-mismatch abort
├── docs/
│   ├── scope.md  prd.md  spec.md  builder-profile.md
│   ├── HANDOFF.md  INFRASTRUCTURE.md  adversarial-review-2026-08-06.md
│   ├── design/  superpowers/
├── scripts/deploy.sh        + GOOGLE_OAUTH_CLIENT_ID in --set-env-vars
├── pyproject.toml           + "star.mcp" in [tool.setuptools] packages. No new dependency
├── .gcloudignore            + harness/
└── process-notes.md
```

---

## Key technical decisions

### Decision 1 — the MCP server is hand-written against the transport spec, no new dependency

**What:** `star/mcp/` implements Streamable HTTP directly. The `mcp` PyPI package is not added.

**Why.** Four reasons, in descending weight:

1. **The conformance surface is small enough to hold in one file.** A tools-only server needs
   `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, a 405 on GET, a 202
   on notifications, an Origin check, and version negotiation. SSE is explicitly optional. Sessions
   are explicitly optional. That is roughly 250 lines against a spec section that was read, not
   recalled — and it is fully unit-testable with no network.
2. **Mounting an ASGI sub-app inside a running FastAPI app has a live lifespan-initialization bug
   class** (`modelcontextprotocol/python-sdk#1367`, "Task group is not initialized"). On a
   single-instance deployment a broken lifespan does not degrade the MCP endpoint, it takes the
   whole service down — the same process serves the demo URL.
3. **The dependency set is pinned exactly and deliberately, 26 days out.** `pyproject.toml:9-14`
   argues that a floating install would break Pipeline A. Adding a package with its own transitive
   tree to a Cloud Build that runs a fresh install is the risk that argument exists to avoid.
4. **It removes a Stage One ambiguity that costs nothing to remove.** `docs/HANDOFF.md:30-32` bars
   other AI frameworks. The `mcp` package is in fact published by *"Model Context Protocol, a Series
   of LF Projects, LLC"* under MIT and makes no model calls — it is a protocol library, and on the
   merits it is clearly allowed. But its maintainer address is `@anthropic.com`, and the argument
   above is one a judge would have to be walked through. Not having the line in `pyproject.toml` is
   worth more than winning the argument.

**Tradeoff accepted.** No free conformance for future protocol revisions, and no free client
implementation. Mitigated by the tool surface being four tools with no resources, prompts, sampling,
roots, or logging — and by `tests/test_mcp_protocol.py` asserting the wire contract directly. If the
spec moves before 2026-09-07, the endpoint stays on `2025-11-25` and says so.

### Decision 2 — the annotator is pure Python, not an agent

**What:** `star/verdicts.py` does the hydration, provenance, downgrade, and unsourced stamping.
Only the verdict itself comes from a model.

**Why.** The project's core claim is that no title, excerpt, or provenance statement is ever authored
by a model — `star/findings.py`'s module docstring, `star/ledger.py`'s, and
`star/agents/synthesis.py:41-48` all enforce it from different angles. `prd.md` requires the check to
report *which* of the room and a fresh search answered, per claim. If the model reports that, the
report is a model's assertion about its own behaviour. If two ledgers report it, it is computed.

**Tradeoff accepted.** A prose format between the verifier and the parser, with the parse-drift risk
`2026-08-09-star-gui-design.md:281-291` already names and already measures. Same mitigation applies:
unparseable lines are kept as field notes, `parse_rate` is reported, and the schema'd-structurer
fallback stays available if the rate sits low.

### Decision 3 — Google linking is a full-page OIDC redirect with `response_type=id_token`

**What:** `location.assign` to `accounts.google.com/o/oauth2/v2/auth`, ID token returned in the URL
fragment, then `signInWithIdp` with the anonymous `idToken` to link.

**Why.** Google Identity Services is a remote `<script>` from `accounts.google.com`, and a remote
script is exactly the silent mid-demo failure the zero-third-party rule exists to prevent
(`prd.md > Decisions this PRD makes` #8, confirmed by the builder). A redirect's only external
interaction is a navigation: it either goes or it visibly does not. It also dodges popup blockers.
The fragment never reaches an access log or a `Referer` header, and it is stripped with
`history.replaceState` before anything else runs.

**Tradeoff accepted.** The implicit flow is the shape Google's own docs steer away from, and it
rests on two claims that are documented but unverified against the live API. Both are named above as
a build-blocking verification with a costed fallback, rather than discovered mid-build.

### Decision 4 — the MCP router receives its dependencies, rather than the run registry moving

**What:** `build_mcp_router(start_build=…, read_room=…, …)`, called from `star/server.py` before the
StaticFiles mount. `_runs`, `_ip_limiter`, `_daily_cap`, and the run lifecycle do not move.

**Why.** "One budget, one ceiling, one kill switch" is only true if there is one code path, and
passing the same function objects to both doors gets that mechanically. The alternative that reads
better — extracting `star/service.py` — churns the most heavily reviewed code in the repo and a
1,406-line test file for no behavioural gain, 26 days from a deadline.

**Tradeoff accepted.** `server.py` grows past a thousand lines and keeps doing two jobs. Noted as the
first refactor after 2026-09-07.

### Decision 5 — a check is one synchronous request

**What:** `POST /api/rooms/{run_id}/scenes` runs the pipeline inline under a 180s ceiling. No
`run_id`, no `stream_key`, no SSE, no `_runs` entry.

**Why.** The entire run-registry apparatus exists because a build is 146s to 420s+ and no client can
hold that. A check is one extraction plus one verification with at most eight searches. Reusing that
apparatus would import its capability keys, its resume cursor, its eviction rules, and its four
terminal statuses to solve a problem this pipeline does not have. It also makes `check_scene` a
normal blocking MCP tool, which is what an agent expects.

**Tradeoff accepted.** No live progress on a check, and a check that outruns 180s fails rather than
salvaging. Acceptable: there is nothing partial worth salvaging from a scene check, and the failure
message names the cap.

---

## Dependencies & external services

Nothing new is installed. Two new external interactions, both Google identity endpoints.

| Service | Used for | Docs | Cost / limits |
| --- | --- | --- | --- |
| Gemini via AI Studio | Every agent, both pipelines | [ai.google.dev/gemini-api/docs](https://ai.google.dev/gemini-api/docs) | `GOOGLE_API_KEY`, Secret Manager. Pinned to `gemini-3.6-flash` |
| Parallel Search API | `parallel_search`, both pipelines | [docs.parallel.ai](https://docs.parallel.ai/) | ~$0.005/search. 30/build, 8/check |
| Google ADK 2.6.2 | Agent orchestration | [google.github.io/adk-docs](https://google.github.io/adk-docs/) | Pinned; `SequentialAgent`/`ParallelAgent` deprecation has no migration path today |
| Firebase Auth / Identity Toolkit | Anonymous sign-in, token refresh, **and now linking** | [`accounts:signInWithIdp`](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/accounts/signInWithIdp) · [REST overview](https://docs.cloud.google.com/identity-platform/docs/use-rest-api) | Free tier. `FIREBASE_API_KEY` is public by design |
| Google OpenID Connect | **New.** The link redirect | [developers.google.com/identity/openid-connect/openid-connect](https://developers.google.com/identity/openid-connect/openid-connect) | Free. `GOOGLE_OAUTH_CLIENT_ID` is public |
| Firestore | Rooms, scenes, tokens | [firebase.google.com/docs/firestore](https://firebase.google.com/docs/firestore) | Free tier. **No rules deployed, and that is correct** |
| Cloud Run | Hosting | [cloud.google.com/run/docs](https://cloud.google.com/run/docs) | One instance, always warm |
| MCP Streamable HTTP | The agent door | [Transports, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) · [2026-07-28 RC](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/) | Spec only. No package |

---

## Deployment — identity & signing

Target: **Google Cloud Run** (the primary artifact) plus a **Devpost submission** (the certification
surface). Neither is in the plugin's per-target table, so the fields the release actually needs are
enumerated here for `/checklist` to sequence.

### Cloud Run

| Field | Value |
| --- | --- |
| Project / region / service | `star-research-dept` / `us-central1` / `star` |
| Runtime identity | `390753828501-compute@developer.gserviceaccount.com` |
| IAM held | `roles/secretmanager.secretAccessor` on the two secrets individually; `roles/datastore.user` on the project |
| Secrets (`--set-secrets`) | `GOOGLE_API_KEY=star-google-api-key:latest`, `PARALLEL_API_KEY=star-parallel-api-key:latest` |
| Public env (`--set-env-vars`) | `GOOGLE_CLOUD_PROJECT`, `FIREBASE_PROJECT_ID`, `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, `FIREBASE_API_KEY`, **`GOOGLE_OAUTH_CLIENT_ID` (new)** |
| Scaling flags | `--max-instances=1 --min-instances=1 --no-cpu-throttling --timeout=900 --memory=2Gi` |
| Deploy | `FIREBASE_API_KEY=$(grep '^FIREBASE_API_KEY=' .env \| cut -d= -f2-) bash scripts/deploy.sh` |
| Post-deploy check | `autoscaling.knative.dev/maxScale` on the serving revision must read `1` — see `INFRASTRUCTURE.md:213-236` for why grepping the service YAML lies |

**One new console step, not scriptable:** the OAuth client's **Authorized redirect URIs** must
include both `https://star-390753828501.us-central1.run.app/` and `http://localhost:8000/`. The
client id then goes into `scripts/deploy.sh`'s `--set-env-vars`. Missing dev-origin registration is
the failure that looks like a broken link button on a laptop and works fine in production.

### Devpost / GitHub

| Field | Value |
| --- | --- |
| Repo slug | `estevanhernandez-stack-ed/STAR` |
| Visibility | Private today. `gh repo edit --visibility public`, **after** a credential sweep |
| License | MIT, already detected by GitHub. The About-sidebar badge follows the visibility flip |
| Push | 20 local commits ahead of `origin/main`. Cloud Run deploys from local source, so the live URL does not prove a push |
| Video | ≤3 min, English, public, no third-party logos or brands on screen. MCP shot is the in-repo persona client in a terminal |
| Dates | Target Sep 5; hard deadline Sun Sep 7 2026, 2:00 PM PT |
| Stage One | License visible; SDKs imported **and called** — `google-adk`/`google-genai` and `parallel-web` both execute at runtime in both pipelines |

**Credential sweep before the visibility flip.** `.env` and `.mcp.json` are gitignored and
`.gcloudignore`d, but the flip is irreversible in the sense that matters: once public, a leaked
secret is leaked. Sweep the whole history, not the working tree.

---

## Testing

Everything below runs with no network and no spend, except where the cost column says otherwise.

| Target | Kind | Cost |
| --- | --- | --- |
| `tokens.py` mint / hash / resolve | Unit — generic refusal vs revoked refusal, `compare_digest` path | none |
| `tokens.py` revoke | Unit — revoked token yields the revoked message, not the generic one | none |
| `verdicts.py` parse | Unit, golden fixtures captured from a real verifier run | none |
| `verdicts.py` hydration | Unit — room-ledger hit, run-ledger hit, neither → `UNSOURCED` | none |
| `verdicts.py` downgrade | Unit — `confirmed` with zero real citations becomes `unverifiable` | none |
| `verdicts.py` budget honesty | Unit — `budget:` prefix honoured only when the budget was actually spent | none |
| `ledger_from_room` | Unit — round-trips a stored room document into a ledger | none |
| MCP protocol | Unit — `initialize`, `tools/list`, `tools/call`, `-32601`, 202 on notification, 405 on GET/DELETE, 400 on bad version, 403 on bad Origin | none |
| MCP auth | Unit — no token, malformed, unknown, revoked, valid | none |
| Per-uid limiting | Unit — MCP builds refused at the ceiling; reads never refused; both doors decrement one `_daily_cap` | none |
| Scene endpoints | Unit — cross-uid isolation returns not-found, delete removes the stored text | none |
| Anchor matcher | Node, `tests/js/test_anchor.mjs` — paraphrase, whitespace, case, repeat, overlap | none |
| Link error mapping | Node, `tests/js/test_account.mjs` — each Identity Toolkit error maps to its own message; uid mismatch aborts | none |
| Google link, live | Manual, once, **before writing the epic** — see the verification gate above | none |
| Pipeline B end to end | Manual, once — a scene with a planted anachronism against a real room | one check |
| Persona harness | Manual, three runs, committed | three runs |

`tests/js/*.mjs` are picked up automatically by `tests/test_js_auth.py`'s glob, and that file already
asserts the glob is not silently empty — adding a scenario file is the whole integration step.

Ruff must stay at 0 findings over `star tests scripts`. Add `harness` to that invocation.

---

## What must not regress

Carried from `prd.md > What must not regress`, restated as the properties this architecture is
responsible for keeping true:

- The seven behavioural obligations hold on the card, the script-check surface, **and the MCP tool
  descriptions.** An agent-facing surface is still a surface.
- Manila owns more than 40% of the room's pixel area in the filed state. The card and the marked
  scene are new pixels and must not dilute it.
- The stamp stays typographic. No gradient anywhere. Aniline appears only as flat stamp ink.
- Zero third-party browser requests. The Google OIDC redirect is a *navigation*, not a fetch, and
  nothing is loaded from `accounts.google.com`.
- Runtime AI is Google Cloud only, and `parallel_search` genuinely executes in **both** pipelines.
- No build step in `web/`.
- `--max-instances=1 --min-instances=1` stays. Nothing here moves `_runs`, `_ip_limiter`, or
  `_daily_cap` out of memory, so nothing here may scale past one instance.
- The Python suite green, `ruff check star tests scripts harness` at 0.
- No copy anywhere, on any surface including tool descriptions and error strings, says the bare word
  "verified" about a source.

---

## Open issues

From the architecture self-review, plus what `prd.md` left open. None block `/checklist`.

1. **The Google link flow is unverified against the live API.** The single largest risk in this
   document. Two claims, two round trips, one costed fallback. It is the **first** item in the
   Identity epic, ahead of any code — a build that discovers this on day four has lost the ordering
   argument that put Part 1 first.
2. **`google_client_id` must be whitelisted in Firebase's Google provider.** `signInWithIdp` accepts
   a Google ID token whose `aud` matches an OAuth client the Firebase project trusts. Firebase
   auto-provisions a web client for its Google provider; using a *different* client id requires
   adding it to the provider's allowed list. Verify which client id is in play as part of item 1.
3. **Verifier parse rate is unmeasured.** Pipeline A's parse rate was measured before the fallback
   decision was made. Pipeline B's format is new and its rate is unknown until real output exists.
   The fallback (schema'd structurer, legal because it carries no tools) stays available, and the
   trigger is the same shape: below 70% across five runs after one round of prompt tuning.
4. **Whether MCP clients other than the harness can connect at all.** STAR ships no OAuth
   authorization server, so a client that insists on discovery will refuse. The harness does not, and
   the harness is the evidence the PRD asks for. Worth one attempt with a real client during harness
   week, and worth recording the result either way rather than leaving it as an assumption.
   **ANSWERED, item 12** — yes for any client configurable with a static bearer header, no for a
   discovery-first client, and browser-based clients are additionally gated by `Origin`. The 401
   challenge is a bare `WWW-Authenticate: Bearer` with no `resource_metadata`, and all four
   well-known discovery paths 404. No third-party client was configured, on purpose: every route to
   one writes a live token into plaintext config, which this repo has shipped once already. Probe
   table in `process-notes.md`.
5. **Room payload size over MCP.** Bibles have run 11,000-17,000 characters, and `get_room` returns
   the bible plus four drawers. Measure during harness runs before deciding whether `get_room` needs
   a way to ask for less. `prd.md > Open questions` #2, unchanged.
   **ANSWERED, item 12** — **152,007 bytes** on the complete room, roughly 37,000 tokens. The bible
   is 16,183 of it and is not the problem; the four drawers are 127,090, and citation excerpts are
   why. `get_room` gets no way to ask for less before 2026-09-07: the shape that would fix it is a
   fifth tool by another name. Breakdown in `process-notes.md`.
6. **`check_scene` against a scene from a different story than the room.** Every claim comes back
   unverifiable-by-way-of-irrelevant, which is technically correct and probably a bad answer. Not
   blocking; watch it during harness runs. `prd.md > Open questions` #4, unchanged.
   **ANSWERED, item 12, and this prediction was wrong.** Every claim came back *`confirmed`*, on
   fresh searches, because the verifier falls through to search and answers correctly about the
   world. The bad answer is a clean pass that means nothing about the story: the room supplies the
   era, so with the room contributing nothing a 1998 phone is confirmed in a scene that never stated
   a year. Fixed as far as it should be by `_provenance()` in `star/mcp/tools.py`, which says in
   words how many sources came from the room and how many from a search, and names the
   zero-from-the-room case. Refusing an off-story scene outright is not on the table: it would make
   the department judge whether a scene belongs to a room, which is a model's opinion about a
   writer's intent.
7. **The harness spends real money against a cap shared with the live demo.** Three personas driving
   real builds against a 100/day ceiling. The cap is a real ceiling in the meantime; if harness week
   collides with rehearsal week, the personas run against already-built rooms and only `check_scene`
   spends. `prd.md > Open questions` #3, with that mitigation added.
8. **`server.py` past a thousand lines with two jobs.** Accepted cost of Decision 4. First refactor
   after 2026-09-07, not before.
9. **Two assumptions carried forward unconfirmed**, both marked in `prd.md` and both still marked
   here: the 8,000-character scene cap, and three personas.
   *(default — confirm on next interactive run)*
