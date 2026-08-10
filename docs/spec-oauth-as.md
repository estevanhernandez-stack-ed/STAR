# STAR — OAuth 2.1 authorization server for the agent door

> Successor epic to cycle #19, scoped 2026-08-10. `prd.md > What we'd add with more time`
> named this as the successor to bearer tokens; `scope.md > What's Explicitly Cut` cut it at
> "a week of work that no judging criterion asks for." Both still true about the judging. The
> reason it is being built anyway is that the cut is felt every time a desktop client tries to
> connect, and the builder's call is that v1 is a checkpoint rather than a terminus.
>
> Read live for this document: the MCP authorization spec (revision `2025-11-25`), fetched
> rather than recalled, plus `star/tokens.py`, `star/auth.py`, `star/mcp/router.py`,
> `star/mcp/protocol.py`, `star/server.py`, `web/auth.js`.

## What this buys, stated precisely

An MCP client that begins by asking "where is your authorization server?" can complete a
connection. Today four `/.well-known/oauth-*` paths answer 404 and the `401` carries a bare
`WWW-Authenticate: Bearer` with no `resource_metadata`, so a discovery-first client has
nothing to follow.

It does **not** change the demo video. `prd.md > Decisions this PRD makes` #4 put the in-repo
persona client in the MCP shot because a third-party desktop client in frame violates
`HANDOFF.md:44`, and that reasoning is unaffected.

## The requirement list, from the spec rather than from memory

| Requirement | Source | Today |
| --- | --- | --- |
| Protected Resource Metadata | RFC 9728, **MUST** | missing |
| AS metadata via RFC 8414 **or** OIDC Discovery | **MUST** (at least one) | missing |
| `resource_metadata` on the 401 challenge | RFC 9728 §5.1, one of two discovery routes | missing |
| PKCE `S256`, advertised via `code_challenge_methods_supported` | OAuth 2.1 §4.1.1, **MUST**; clients **MUST** refuse without it | missing |
| `resource` parameter honoured, tokens audience-bound | RFC 8707, **MUST** | missing |
| Token audience validated on every MCP request | **MUST**; tokens for other resources **MUST** be rejected | missing |
| Client registration: pre-registration, CIMD, or DCR | CIMD **SHOULD**, DCR **MAY** | missing |
| Short-lived access tokens; refresh rotation for public clients | **SHOULD** / **MUST** | tokens never expire |
| All AS endpoints over HTTPS; redirect URIs HTTPS or `localhost` | **MUST** | n/a |

**The authorization server may be hosted with the resource server.** It cannot be Google:
the spec requires STAR to validate that a token was issued *for STAR*, and Google will not
mint a token carrying STAR's canonical URI as its audience. So STAR is both roles, and Google
is what `/authorize` delegates *user authentication* to.

## What already exists, and is the reason this is not a week

- **User authentication is solved.** The Google redirect flow was proved against the live API
  at cycle #19 item 1: `response_type=id_token` honoured, `signInWithIdp` linking on the first
  attempt, uid preserved byte-for-byte. `/authorize` needs to know *which human* is approving;
  that machinery is built and deployed.
- **Credential issuance, hashing, and revocation exist.** `star/tokens.py` mints
  `star_<12 hex>.<32 hex>`, stores sha256, resolves in six steps with one generic refusal and
  a distinct revoked one, and soft-revokes. Access tokens need **expiry** and **audience**
  added to that shape, not a new scheme.
- **The refusal posture exists.** `star/mcp/router.py` already checks bearer auth before any
  JSON-RPC parsing and answers `401` with `WWW-Authenticate: Bearer`. One parameter is added
  to a header that is already correct.

## Decisions

### Decision 1 — access tokens stay opaque, not JWT

Reuse `star/tokens.py`'s two-part shape with `expires_at`, `audience`, `scope`, and
`client_id` added to the stored document. Audience validation becomes a string comparison
against the canonical URI, done at the same step that already resolves the token.

**Why not JWT.** A JWT needs a signing key, a rotation story, a JWKS endpoint, and a decision
about what happens when the key changes mid-flight. Opaque tokens need a database read, which
this door already performs on every call. The one thing JWTs buy — stateless validation
across instances — is worth nothing on a deployment pinned to `--max-instances=1`.

### Decision 2 — authorization codes live in memory, with a bound

Single-use, PKCE-bound, 60-second TTL, in a dict with a `max_keys` ceiling and a stale sweep,
matching `star/guards.py`'s existing posture and for the same documented reason.

**Accepted cost, named:** a deploy or restart inside the ~30 seconds between redirect and
token exchange drops the code and the user restarts the flow. The alternative is a Firestore
write and read on a path that is already two round trips, to protect a window that closes in
under a minute. Revisit if this ever runs on more than one instance — at which point `_runs`,
both limiters, and this all move together, exactly as `star/guards.py` says.

### Decision 3 — support both CIMD and DCR

The spec's client priority is pre-registered → Client ID Metadata Documents → Dynamic Client
Registration → prompt the user. Which of these a given desktop client reaches for is not
something to guess at, and implementing both is cheaper than measuring which one is needed and
being wrong. DCR is one endpoint. CIMD is an HTTPS fetch plus validation that the document's
`client_id` matches its URL exactly.

**The SSRF warning is not optional.** CIMD makes the AS fetch a URL an unknown client chose.
The fetch must refuse non-HTTPS, refuse private and loopback address ranges after DNS
resolution, cap the response size, and cap the time. The spec calls this out and it is the one
place in this epic where getting it wrong hands out a request forgery primitive.

### Decision 4 — two scopes, mapping to what the tools already say they cost

`rooms:read` covers `list_rooms` and `get_room`. `rooms:write` covers `build_room` and
`check_scene`. That is the free-versus-spends split every tool description already states, so
the consent screen can say something true and specific rather than asking for everything.

### Decision 5 — personal access tokens keep working, unchanged

`/mcp` accepts **both** a card-issued `star_` token and an OAuth-issued access token. The
harness depends on the first, `harness/runs/*.md` are transcripts of it, and
`claude mcp add --header` uses it. A card token has no audience and no expiry and stays that
way; an OAuth token has both and is checked for both.

**Why not migrate everything to OAuth.** The card token is the one credential a human can
issue, read once, and paste somewhere. Removing it to reach protocol purity would break the
one path that is currently proven to work.

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /.well-known/oauth-protected-resource` | RFC 9728. Names the canonical resource URI and `authorization_servers` |
| `GET /.well-known/oauth-authorization-server` | RFC 8414. Advertises `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, `code_challenge_methods_supported: ["S256"]`, `scopes_supported`, `client_id_metadata_document_supported: true` |
| `GET /oauth/authorize` | Identifies the human via the existing Google flow, renders consent, issues a code |
| `POST /oauth/token` | `authorization_code` + PKCE verifier → access token; `refresh_token` → rotated pair |
| `POST /oauth/register` | RFC 7591 dynamic client registration |
| `POST /mcp` | Unchanged shape; token resolution gains audience, expiry, and scope checks |

`401` gains `resource_metadata="https://star.626labs.dev/.well-known/oauth-protected-resource"`
and a `scope` parameter. `403` with `error="insufficient_scope"` becomes reachable.

**Both `/.well-known/` routes must be registered before `app.mount("/")`,** for the same
reason `/mcp` is: the StaticFiles mount at `/` swallows everything declared after it.

## The consent screen

A real page, in the Morgue's own vocabulary rather than a bare form. It has to name three
things, and the third is a security requirement rather than a courtesy:

1. Which client is asking, by the name it registered.
2. What it is asking for, in the language the tool descriptions already use — reading rooms
   costs nothing, building and checking spend real money against a shared daily budget.
3. **The redirect URI's hostname, displayed plainly.** The spec requires this and warns
   specifically about `localhost` impersonation: any client can claim another client's
   metadata URL and bind to a loopback port, and the user sees the legitimate client's name.
   The hostname is the only thing distinguishing them, so it is shown rather than summarised.

## What must not regress

- The Python suite green, `ruff check star tests scripts harness` at 0.
- Card-issued tokens keep working, and `harness/` runs unchanged against them.
- `--max-instances=1 --min-instances=1` stays; nothing here moves module state to a shared
  store, so nothing here may scale past one instance.
- No copy anywhere says the bare word "verified" about a source.
- Zero third-party browser requests. The consent screen is served from `web/` like everything
  else.
- No new runtime dependency, and no pin moves before 2026-09-07.

## Open questions

1. **Which registration path a real desktop client actually takes.** CIMD and DCR are both
   built, so this is a measurement rather than a blocker — but it should be recorded from a
   real connection attempt rather than assumed, the way Open issue #4 was.
2. **Whether the existing `_uid_limiter` keys correctly for an OAuth-issued token.** It keys
   on uid, and an OAuth token still resolves to one, so the answer is probably yes. Probably
   is not a word this repo accepts about a spend ceiling; it needs a test.
3. **Token lifetime.** One hour is the default assumption. Nothing has measured how often a
   long-running agent session would trip a refresh.
