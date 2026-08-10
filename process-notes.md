# Process Notes

Vibe Cartographer cycle **#19** — STAR. Started 2026-08-10.

## /onboard

**Mode:** fully-autonomous (*Autonomous — Self*). Este opted in at the single pacing gate with
"B please." Per the contract, steps 3–11b of the interview were skipped and the run flowed
straight to artifact generation. No further confirmations were requested.

**Persona:** Architect. **Mode:** Builder. **Build-mode preference on file:** iterative-prototype.

### Technical experience

Experienced. TypeScript, Python, JavaScript, Luau, C#, HTML/CSS, C++. FastAPI and Firebase both
already on the frameworks list, which matters — this cycle's substrate is not new ground for him.
Deep AI-agent experience: 18 completed Cart cycles, six shipped Claude Code plugins.

### Project goals

Three-part extension of an already-shipping app, in the order Este set:

1. Google sign-in replacing anonymous Firebase auth.
2. HTTPS MCP server inside `star/server.py` — `list_rooms`, `get_room`, `build_room`, per-user
   bearer tokens, OAuth 2.1 AS deferred.
3. Pipeline B (`check_scene`): ClaimExtractor → Verifier → Annotator, then exposed over MCP.

Wrapping all of it: a hackathon submission that clears Stage One and scores on Stage Two.

### The tradeoff /scope inherits

Surfaced at `/onboard` rather than discovered at `/build`. `docs/HANDOFF.md` puts the deadline at
**Sep 7 2026, 2:00 PM PT**, target submission **Sep 5** — 26 days out. The submission requires a
hosted URL, a public repo with a visible MIT license, and a ≤3-min video. **An MCP server is not
on that list.** Pipeline B is described in the same handoff as "the demo's emotional peak."

This is a sequencing question, not a scope-cut question, and it is `/scope`'s first real fork.
Este's ordering was stated before the deadline was on the table in this session; he may well
keep it, but he should keep it *knowingly*.

### Design direction

Not an open question — decided 2026-08-09 and documented in `docs/design/DIRECTION.md`, backed by
four research files. **THE MORGUE**: the newspaper clipping library, chosen on the test that the
metaphor describes the system rather than dressing it. Palette, type stack, and two make-or-break
rules are all specified. Seven behavioural obligations carry into `/prd` and `/spec`.

One line in that doc lands directly on this cycle: the adversarial critic "assumed Google sign-in.
Ours is silent and anonymous." Part 1 closes that gap — and makes obligation #5 (state treatment
retention in the intake, before the paste) *more* load-bearing, not less, since a real Google
identity will now be attached to a stored treatment.

### Prior SDD experience

Deep. 18 completed cycles. Established pattern, first-person confirmed at the vibe-taker retro:
spec-prep upstream with an agent, then Cart wraps `/checklist` → `/build`. Zero deepening rounds
is the norm when substrate is understood. `/reflect` should skip SDD fundamentals entirely and
target this cycle's strategic calls.

### Engagement style observed this session

High momentum, decisive. Pivoted mid-turn from the vibe-access scan to the MCP question without
waiting for the turn to close — worth reading as tempo, not as impatience. When given a
three-option auth fork he declined to pick blind and instead sent me to verify the 626Labs
dashboard precedent first: *"Let's verify what that is first."* That instinct was correct and
changed the recommendation's evidence base. Chose the tool surface decisively (build_room +
check_scene) in the same breath.

## /onboard — autonomous run

Every value used, with its source. `(default — confirm on next run)` marks inference.

| Field | Value | Source |
|---|---|---|
| name | Estevan | profile `shared.name` |
| identity | 626Labs, Fort Worth, vibe coder, 18 cycles | profile `shared.identity` |
| experience level | experienced | profile |
| languages | 7 listed | profile — **past TTL, deferred** |
| frameworks | 21 listed | profile — **past TTL, deferred** |
| persona | architect | profile (fresh, TTL 180) |
| tone / pacing | terse and direct / brisk | profile (fresh) |
| mode | builder | profile `plugins.vibe-cartographer.mode` |
| build mode | iterative-prototype | profile |
| autonomy | fully-autonomous, self | profile + explicit opt-in this session |
| project origin | extending existing repo | **repo state read live** — not defaulted |
| project goals | three-part extension | Este, stated this session |
| design direction | THE MORGUE + palette + 7 obligations | `docs/design/DIRECTION.md` |
| architecture docs | 7 docs + inventory | `docs/`, read live |
| deployment target | Cloud Run + Devpost | `scripts/deploy.sh`, `docs/INFRASTRUCTURE.md` |
| prior SDD | deep, 18 cycles | profile |

**Nothing was defaulted.** The returning-builder branch plus this repo's own artifacts answered
every beat the interview would have asked. That is the fully-autonomous contract working as
designed rather than a gap being papered over.

### Deviations and findings worth carrying forward

1. **Existing repo, not an empty folder.** `/onboard`'s "Before You Start" wants a fresh
   directory and prescribes a pause. Este pointed Cart at STAR deliberately, so the
   extending-existing-repo path was taken and the pause was collapsed into a statement rather
   than a blocking question. Artifacts still land in `docs/`.

2. **Builder-profile seat divergence — resolved, and worth not re-discovering.** Two
   `builder.json` files exist on this machine. `~/.claude/profiles/builder.json` is
   authoritative (cycles #17 and #18, last written 2026-07-25);
   `~/.claude-personal/profiles/builder.json` is a stale fork two cycles behind (last written
   2026-05-22 at cycle #16). The SKILL hardcodes the `~/.claude` path, so writes land there
   regardless of which seat's plugin cache is executing. **This run read the stale fork first
   and had to correct** — the cycle number was briefly reported as #17 before the authoritative
   file put it at #19. Recorded in the profile as `profile_seat_note_2026_08_10`. The stale copy
   should be reconciled or deleted deliberately, not merged.

3. **Decay deferred, not stamped.** `technical_experience.languages` and `.frameworks` are 107
   days past a 90-day TTL. The autonomous contract defers rather than blocking, and explicitly
   does not stamp — so both will surface on the next interactive `/onboard`. Recorded in the
   profile as `decay_deferred_2026_08_10`.

4. **Session-logger is unwired in this environment.**
   `~/.claude-personal/plugins/data/vibe-cartographer/` does not exist, so no sentinel was
   written and no orphan sweep ran. **This file is the durable record for this run.** When back
   in a Cart-wired session, `/vibe-cartographer:reconnect` can backfill the session log from
   these notes.

5. **Prior-session work folded in rather than re-derived.** A vibe-access agnostic scan ran
   earlier in the same session and its inventory (`.vibe-access/state/inventory.json`, 5 routes,
   4 `token` + 1 `none`, 2 unmapped) is listed as an architecture doc. The auth precedent was
   read live out of the 626Labs dashboard `mcp-server` — sha256-hashed API keys and a
   single-tenant OAuth 2.1 AS running side by side, cheap path shipped first. Both are evidence
   `/spec` should not have to re-gather.

### Complements available (Pattern #13)

Announced, not yet invoked — these fire at their own phases:

- `superpowers:brainstorming` → `/scope` brain-dump.
- `superpowers:writing-plans` → `/spec` and `/checklist` proposals.
- `superpowers:test-driven-development` → every `/build` item.
- `superpowers:systematic-debugging` → `/build` when a step fails.
- `superpowers:verification-before-completion` → `/build` verification.
- `superpowers:requesting-code-review` → `/reflect` project review.
- `mcp__plugin_playwright_playwright__*` → available; STAR already has `.playwright-mcp/`
  artifacts, and the demo video needs screen capture of real runs.
- `gh` CLI → the handoff's open item #1 is verifying the repo is public with the MIT badge
  visible in the About sidebar. That is a Stage One pass/fail and still unverified.

## /scope

**Date:** 2026-08-10. **Outcome:** `docs/scope.md`. **Deepening rounds:** 0.
**Mode:** fully-autonomous (*Autonomous — Self*). **Persona:** Architect. **Complements invoked:** none.

### How the idea evolved

It started as a sequencing question and stopped being one inside the first exchange.

`/onboard` handed `/scope` a fork framed as *"MCP server or Pipeline B first, against a Sep 5
target."* Reading the three parts against each other rather than in sequence exposed a coupling the
brief did not name: **Part 1 exists to serve Part 2.** Google sign-in is near-free on the backend
because `star/auth.py` already accepts any Firebase provider, but its only real justification is a
durable identity behind per-user MCP bearer tokens. An anonymous uid cannot be one. So the ordering
question collapsed into a scope question: is the MCP server in, and Google sign-in rides along with
the answer either way.

Este's answer moved the scope more than the ordering did. Four reasons for the MCP server, three of
which were on the record in some form — impressive next step, desktop-agent future, 626 platform
play. The fourth was not, and it is the one that changed the doc: **agent personas behind separate
runs, using the tools the way different users would, as a synthetic user-test harness.** That
reframes the MCP surface from plumbing to product. If the tools exist so Este can call them, the
schemas and error strings are internal. If they exist so an arbitrary persona can drive a run
blind, every failure message becomes a judged surface, because a persona that cannot tell why a
call failed produced no test. It is also the only one of the four a hackathon judge can verify in
the repo rather than take on faith.

### Pushback, and what it corrected

One, and it was a framing correction rather than a disagreement about substance.

The cut-line question was posed as a hypothetical: *"it's Sep 1 and one of these isn't finished."*
Este's response: **"do you think it's September 1st because we're so far done with the project?"**
Fair, and load-bearing. 2026-08-10 to the hard deadline is 28 days, 26 to the Sep 5 target, with
Pipeline A built, hardened, deployed, and the Morgue serving live. The numbers do not describe a
squeeze, and packaging a scope question in deadline anxiety would have pushed the scope smaller
than the calendar requires.

**Response:** dropped the question as a blocking gate, made the calls, and wrote the cut line into
the doc as a written-down fallback rather than a forecast. The scope is now three parts, all in.

Worth carrying into `/reflect`: the agent generated artificial urgency from a real deadline that was
not yet urgent. The autonomy contract says flow through beats the record answers; it says nothing
about not manufacturing pressure the record contradicts.

### What resonated

No new references surfaced, and none were sought — the design direction was decided 2026-08-09 and
four research files back it. `superpowers:brainstorming` was announced and deliberately **not**
invoked: it is a divergence tool and this idea converged the day before. The web-search "research &
reaction" beat was flowed through for the same reason. Both are surfaced assumptions, not gaps.

What did get pulled forward from the record: the 626Labs dashboard `mcp-server` precedent
(sha256-hashed API keys and a single-tenant OAuth 2.1 AS side by side, cheap path shipped first) as
the token-storage answer, and `.vibe-access/state/inventory.json` as the already-captured
agent-access surface `/spec` should read rather than re-derive.

### Active shaping

Este drove. Two of the three scope-shaping inputs came from him and neither was a pick from a menu:
the four reasons the MCP server matters, and the correction that killed the triage framing. The
agent supplied the coupling analysis, the reorder, and the design argument for narrowing Google
sign-in to account linking; Este has not yet ruled on those three and they are in the doc as
recommendations with their reasoning attached, so overriding any of them is a one-line edit.

### Findings recorded live, not remembered

Three, from reading the repo rather than the docs about it.

1. **20 commits ahead of `origin/main`.** All of Phase 3 exists on one machine. Cloud Run deployed
   from local source via `gcloud run deploy --source .`, so the live URL serving `tokens.css`,
   `drawer.js`, and `shell.js` does **not** prove a push. Carried into `scope.md` under "Open, and
   owned."
2. **The board's "GUI Phase 3" task reads Not Started** while `eec40b2` is in the log and the
   deployed service serves the Morgue. Stale task, not missing work. `/task-meditation` owns it.
   Nothing on the board covers Google sign-in or the MCP server either; `/checklist` owns that.
3. **Repo state verified rather than assumed:** private, and GitHub already detects the MIT license
   (`licenseInfo.key = "mit"`). The handoff's open item #1 said this was unverified. It now is —
   the About badge follows the visibility flip, so submission week is one `gh repo edit` behind a
   credential sweep, not two steps.

### Correction to `/onboard` note #4

`/onboard` recorded that session-logger was unwired because
`~/.claude-personal/plugins/data/vibe-cartographer/` does not exist. **That directory is not where
the log lives.** `skills/session-logger/SKILL.md` hardcodes
`~/.claude/plugins/data/vibe-cartographer/sessions/<date>.jsonl`, that path exists, and
`2026-08-10.jsonl` already carried a `/prd` entry from another project written at 11:10 today.

Same class of error as `/onboard` note #2: the wrong seat was read. The conclusion happened to hold
for `/onboard` itself — no entries were written for that run and it still needs
`/vibe-cartographer:reconnect` to backfill — but the stated reason was wrong, and left uncorrected
it would have suppressed logging for the rest of the cycle.

This run logged natively: sentinel and terminal pair, `sessionUUID`
`6d27a7f4-249f-4a19-8019-caebf0d88d5b`, plus `last_seen_complements` (17 entries, first snapshot,
so `previous_diff_count = 0` and no `notable_change_at` stamp). The profile write was diffed after
the fact and touched exactly `plugins.vibe-cartographer._meta` — `shared` and the `vibe-doc` block
were untouched, per Pattern #11.

## /prd

**Date:** 2026-08-10. **Outcome:** `docs/prd.md`. **Deepening rounds:** 0.
**Mode:** fully-autonomous (*Autonomous — Self*). **Persona:** Architect. **Complements invoked:** none.

### What the PRD added or changed against the scope doc

Six epics, twenty stories, and roughly ninety acceptance criteria against a scope doc that named
three parts. The expansion is mostly edge cases, and most of them came out of reading the code rather
than out of reasoning about the scope.

The single largest change is that **`/prd` read the shipped intake copy and found the scope doc's
premise slightly wrong in a useful direction.** `scope.md` said obligation 5 "does not get softened"
once a real identity attaches. The actual copy in `web/index.html:55-60` is narrower and better than
the scope assumed — it already says the treatment itself is not stored, only the extracted profile
and the research. But two of its clauses go *false* on linking: "kept under this browser's identity"
stops being true when the account is reachable from any browser, and the implication behind "nothing
is visible without your sign-in token" changes character when the token becomes a long-lived string
pasted into an agent config. So obligation 5 does not merely survive Part 1. It forces a copy change,
and that is now a requirement rather than a note.

Second change: `store.py`'s `room_to_document` never persists the treatment, and the GUI spec's
Firestore schema puts `scenes/{sceneId}.text` under the room. **Pipeline B therefore stores something
strictly more sensitive than the thing the shipped copy promises not to store.** Disclosure before
the paste is obligation 5 applied a second time, and it is not sufficient on its own for actual
script pages — so scene delete is in scope. That is the one requirement this PRD adds beyond
`scope.md`, and it is named as an addition in the doc rather than smuggled into a criterion.

### The forks `/scope` handed over, and how they closed

Seven decisions, listed in the PRD with reasoning attached so any of them is a one-line override.
Three were genuine:

- **`get_room` is `build_room`'s poll.** `scope.md` called the long-running-tool problem "the single
  largest unknown in Part 3." It is not much of an unknown once you read `star/server.py:728-766`:
  `get_room` already returns `{status, result}` with the full terminal-status vocabulary. Four tools
  stays four tools, and a fifth would have been a second name for one answer.
- **Per-uid rate limiting on the MCP door.** `scope.md` flagged this and left it to `/spec`. Closing
  it here because it is a product decision, not an implementation one: a desktop agent behind CGNAT
  sharing a limiter with strangers is a broken product, and one address buying an unlimited budget is
  a broken bill. Both are answered by the same key change, and it ships with the server rather than
  after it.
- **The video's MCP shot.** `scope.md` named three exits and wrote "/prd picks." Picked the in-repo
  Gemini-driven client, and the reason is that it was the only exit already required elsewhere: the
  persona harness needs a client regardless, so one artifact does three jobs — harness, video shot,
  and repo-verifiable evidence. The terminal-only shot was cheaper and bought nothing else; the
  repo-and-writeup-only exit forfeits twenty strong seconds for a constraint the in-repo client
  already satisfies.

### The contradiction caught, and reconciled

Tier-1 rule 3 fired once. The GUI design spec (`2026-08-09-star-gui-design.md:266`) specifies Script
Check verdict colors as "confirmed green, anachronism red, unverifiable dim." `DIRECTION.md`'s
palette, decided the same day, contains no green at all, and assigns oxide to "the anachronism
verdict" and pencil to "the **unverifiable** state" explicitly. The Phase 3 plan states DIRECTION
supersedes the spec wherever they disagree, so the spec line is stale rather than competing. Resolved
in the PRD as aniline / oxide / pencil, with the reasoning inline so the next reader does not
re-litigate it against the spec file.

### The one genuinely open mechanism question

Google linking without a third-party browser request. `web/auth.js` runs raw Identity Toolkit REST
deliberately, and the standing rule permits "Google's identity endpoints" — but the obvious mechanism
(Google Identity Services) is a remote *script* from `accounts.google.com`, which is exactly the
silent mid-demo failure the zero-third-party rule exists to prevent. A fetch to an identity API and a
`<script src>` from an identity domain are not the same risk, and the rule as written does not
distinguish them.

Recommendation in the doc: full-page redirect OAuth, so the only external interaction is a
navigation, which fails visibly or not at all. Flagged as answer-before-`/spec`, along with
confirming the `accounts:signInWithIdp` linking shape against the live API rather than assuming it —
the same discipline that caught the ADK response envelope on 2026-08-09.

### Both mechanism questions closed the same session

Este answered both before clearing, so `/spec` inherits decisions rather than a fork.

**Redirect OAuth, confirmed.** No further argument needed; the recommendation held.

**The account surface is a fourth stage state in `web/shell.js`**, entered from the bottom of the
rail in `--pencil`, backed by three `_require_uid`-guarded endpoints (`POST`/`GET /api/tokens`,
`DELETE /api/tokens/{id}`). The alternative considered and rejected was `web/account.html`, which is
free server-side (the StaticFiles mount at `/` already serves any file in `web/`) but costs a cold
auth bootstrap on every visit — and that path carries the intermittent 401 documented at length in
`web/auth.js:145-204`. Fewer surfaces that can hit a known demo-day bug beat cleaner separation.

**The edge case that fell out of answering it.** A full-page redirect leaves the app, and
`{run_id, stream_key}` live in page memory only, so a build in flight returns unstreamable. The run
itself survives — the asyncio task keeps going and `_persist` writes at terminal status, so the room
files and lands in the rail. Only the live view is lost. Fix is `sessionStorage` plus the
`Last-Event-ID` resume the server already serves at `star/server.py:694-712`. Written into the PRD
as a criterion rather than left as a note, because "don't offer the link during a run" is the
tempting weaker answer and it would have cost the writer the thing they were watching.

### Scope guard

One expansion allowed (scene delete, argued above), and one place where the doc deliberately did not
expand: the critic's structural objection that a real department is something you talk back to. It is
correct, it is unanswered, and answering it is a different product. It sits in "what we'd add with
more time" with its reason, rather than being quietly dropped so the metaphor reads clean.

Five things moved to that section rather than into the build: room deletion, a bible-reading pass in
the verifier, room merge/versioning, conversational follow-up, and adaptive categories.

### Active shaping

No live builder input this run — fully-autonomous, and every beat the interview would have asked was
answered by `scope.md`, the seven docs, or the code. The three decisions above are the agent's, and
all three are recorded with their reasoning so overriding any of them costs one line. The two
assumptions marked `(default — confirm on next interactive run)` are the scene character cap (8,000,
matching the treatment cap) and the persona count (three).

### Deviation from the SKILL worth noting

`/prd`'s "no code talk" rule was followed in the *output* — the doc contains no technical decisions —
but not in the *preparation*. Nine source files were read live, and roughly a third of the acceptance
criteria exist because of what was in them rather than what was in `docs/`. On an extending-an-existing-repo
cycle the code is a requirements document, and treating it as off-limits would have shipped a PRD
that contradicted the running system twice.

## /spec

Cycle #19, 2026-08-10, fully-autonomous (*Autonomous — Self*), Architect persona, Builder mode.
Zero deepening rounds, matching the standing pattern. Output: [`docs/spec.md`](docs/spec.md).

### What the preparation actually was

Fourteen source files read live before a line was written: every runtime module in `star/`, the
three browser modules the cycle touches, `index.html`, `tokens.css`, `pyproject.toml`, `Dockerfile`,
`.gcloudignore`, `scripts/deploy.sh`, and `tests/test_js_auth.py`. Architecture docs superseded the
plugin's `default-patterns.md` outright — the builder profile names seven of them and every stack
choice in the spec is inherited rather than proposed. There was nothing to propose: the stack is
built, deployed, and pinned with reasons attached.

Five external facts were researched rather than recalled, because all five are load-bearing and
three of them changed inside the last year: the MCP Streamable HTTP transport requirements, the
2026-07-28 release candidate's stateless turn, the `mcp` PyPI package's current ownership,
Identity Platform's `signInWithIdp` linking field, and which `response_type` values Google's OIDC
endpoint still honours.

### Technical decisions and rationale

**1. Hand-write the MCP server; add no dependency.** The decision looked like a dependency question
and turned out to be four separate ones stacked. The conformance surface for a tools-only server is
small (SSE optional, sessions optional, GET answers 405). The Python SDK has a live
lifespan-initialization bug when mounted inside an existing FastAPI app, and on a single-instance
deploy a broken lifespan takes the demo URL down with it. The dependency set is pinned exactly and
deliberately 26 days out. And the `mcp` package — genuinely an LF project under MIT, genuinely
making no model calls, genuinely allowed — still has an `@anthropic.com` maintainer address and a
name a Stage One reviewer would have to be walked through. Not needing the argument beat winning it.

**2. The annotator is pure Python, not the third agent.** The literal reading of "ClaimExtractor →
Verifier → Annotator" is three model calls. But the PRD requires the check to report *which* of the
room and a fresh search answered each claim, and a model reporting that is a model asserting things
about its own behaviour. Two ledgers reporting it makes it computed. This is the same discipline
`findings.py` and `ledger.py` already enforce for Pipeline A, applied to the second pipeline instead
of being reinvented next to it.

**3. Dependency-inject the MCP router; do not extract `star/service.py`.** The tidier factoring is a
service module holding the run registry and the guards. It is better architecture and it was the
wrong call: that family is the most heavily reviewed code in the repo, its comments carry the
reasoning behind four separate incidents, and moving it churns a 1,406-line test file for zero
behavioural gain. Passing the same function objects to both doors buys the identical "one budget,
one ceiling" property with no movement. Logged as the first refactor after the deadline.

**4. A check is one synchronous request.** The run registry, capability keys, resume cursor, and
four terminal statuses exist because a build runs 146s to 420s+. A check is one extraction and one
verification with at most eight searches. Reusing that apparatus would import all of its complexity
to solve a problem Pipeline B does not have, and it would make `check_scene` a non-blocking MCP tool
where an agent expects a blocking one.

**5. Named the account surface.** `prd.md > Open questions` #5 asked and the spec answers: **"Your
card."** In a morgue the reader has a card — who you are, and what has been issued in your name.
Marked as a one-line override, because it is a naming call rather than a structural one.

### The one thing that could still go wrong

The Google link flow rests on two documented-but-unverified claims: that Google still honours
`response_type=id_token` for this client type, and that `signInWithIdp` accepts a Google ID token
minted outside Firebase's own handler carrying a nonce Firebase did not issue. Google's own copy
steers toward Google Identity Services, which is the remote `<script>` this project forbids, so the
recommended path is closed and the open one is the one Google is quietest about.

Written into the spec as a **build-blocking verification ahead of any code in the Identity epic**,
with a costed fallback (server-side authorization-code exchange, one endpoint, one Secret Manager
entry) that is explicitly not to be built unless the verification fails. Discovering this on day
four would have cost the ordering argument that put Part 1 first.

### What the self-review caught

Four things the first pass had wrong or missing:

- **`pyproject.toml` uses an explicit package list, not `find`.** Adding `star/mcp/` without adding
  `"star.mcp"` works locally and 500s on Cloud Run. Highest-value line in the spec per character,
  and it only surfaced from grepping the sibling config rather than assuming the convention.
- **`GOOGLE_OAUTH_CLIENT_ID` must stay out of `validate_env()`.** That function fails the boot on
  anything whose absence is silent. This one's absence is loud by design, and keeping it out is what
  makes the PRD's "linking unavailable, everything still works" criterion true by construction
  rather than by a code path someone remembers to write.
- **The per-uid limiter needs `max_keys` for the same reason `_ip_limiter` does.** The O(n) stale-key
  sweep runs on the single-threaded loop every open SSE stream shares. Copying the class without
  copying the bound would have re-opened Finding 3b through a new door.
- **`_daily_cap.check()` increments on the allow path**, so the cheap per-caller check has to run
  first on the MCP door too. Getting that order backwards once already cost a whole day's budget in
  about two seconds; the spec states the order rather than leaving it to be rediscovered.

### Deepening rounds

Zero, and the reason holds: the substrate is understood, the PRD closed nine forks with reasoning
attached, and the architecture docs decide the stack. Rounds earn their cost when scope is fluid.
Where the spec found a genuine fork the PRD had not closed — the transport, the annotator's nature,
the router's wiring, the check's execution model — it closed it with a named decision and a stated
tradeoff rather than asking a question the record could already answer.

### Active shaping

No live builder input this run. Five decisions are the agent's, each recorded with its reasoning so
overriding any of them costs one line. Two assumptions stay marked `(default — confirm on next
interactive run)`: the 8,000-character scene cap and the three-persona count, both inherited
unchanged from `/prd`. Nine open issues are enumerated with owners; none block `/checklist`.

## /checklist

Cycle #19, 2026-08-10, fully-autonomous (*Autonomous — Self*), Architect persona, Builder mode.
Zero deepening rounds. Output: [`docs/checklist.md`](docs/checklist.md). **13 items, five gates,
four checkpoints.**

### Sequencing decisions

**The order is 1 → 2 → 3 and the reason is mechanical.** `check_scene` over MCP requires Pipeline B
to exist, so an MCP-first build ships three tools and then reopens the server for the fourth. This
was settled at `/scope`; `/checklist` only had to hold it.

**Item 1 is a verification with no code in it, and it is first.** The Google link flow rests on two
documented-but-unverified claims, and Google's own copy steers toward the remote `<script>` this
project forbids — so the recommended path is closed and the open one is the one Google is quietest
about. Two round trips prove or kill it. A build that discovers this on day four has lost the
ordering argument that put Part 1 first, which is the single most expensive thing this checklist can
prevent.

**Identity precedes MCP because the coupling is mechanical, not thematic.** A token can only be
issued to a linked identity, since an anonymous account's only proof of ownership is a
`localStorage` entry. That is `prd.md > Decisions this PRD makes` #3, and it is why items 2-4 sit
ahead of items 10-11 rather than beside them.

**The anchor matcher (8) is pure and precedes the surface that consumes it (9).** It is the one piece
with real algorithmic risk and it needs no pixels to test. Same instinct that put `star/findings.py`
and `star/ledger.py` ahead of the drawers in Phase 1.

**The transport (10) precedes the tools (11)** so wire conformance is proved before four descriptions
are written on top of it. The tools are where the product lives for an agent; the transport is where
a client either connects or does not.

### Checkpoint placement, and why it tightens

Checkpoints after items 4, 7, 9, 11 — spacing 4 → 3 → 2 → 2. The guide's default is every 3-4, and
the last two are deliberately tighter:

- **4** closes identity. Everything downstream assumes a linked uid can mint a credential.
- **7** closes Pipeline B end to end, against a real room with a planted anachronism. This is the
  demo's emotional peak; if it does not work here, the schedule changes, not the scope.
- **9** is the marked scene — the surface that carries the design score and the one place the H1 XSS
  can return through a different door.
- **11** is the wire contract. A judge cannot see it, which is exactly why it needs its own gate.

### Granularity calls

Two merges and one split, all deliberate:

- **Models and the session-driven search budget folded into item 5** rather than standing alone.
  Each piece is small, and splitting them would have produced an item whose only verification was
  "the file imports." `McpToken` went to item 3 and the claim models to item 5, so each item adds the
  models it needs and no ordering constraint is created between them.
- **The live-run stash and `Last-Event-ID` resume folded into item 2** rather than its own item. The
  redirect is what causes the problem, so the fix belongs with the redirect.
- **MCP transport and MCP tools kept split** (10 and 11) even though they ship together. The
  transport is ~250 lines of conformance with a checkable wire contract; the tools are four
  descriptions and eleven error strings that have to be *read* rather than asserted. Different
  verification methods means different items.

13 items against a 26-day runway with Pipeline A already built, hardened, and deployed. Precedent
says that is the right size: 12 items on Sanduhr, 13 on vibe-Keystone, 14 on the readiness plugin.

### The documentation and security item

Item 13 is the standard final item plus the submission surface, which for this project are the same
work: the credential sweep is not hygiene, it is the pre-flight for an irreversible visibility flip.
Three project-specific verifications were written in rather than inherited from the template:

- **Sweep the whole history, not the working tree.** Once public, a leaked secret is leaked.
  `.mcp.json` held a live bearer token in this repo once already.
- **No Firestore ruleset is deployed, and that is the correct posture** — deploying permissive
  test-mode rules would silently void the one security boundary. The item verifies the *absence*.
- **Check `maxScale` on the serving revision, not the service YAML.** Grepping the YAML lies
  (`INFRASTRUCTURE.md:213-236`), and `--max-instances=1` is load-bearing rather than tuning.
- **`pip-audit` findings get a written call, not a silent bump.** No pin moves before 2026-09-07.

### Board tasks created

`scope.md > Open, and owned` assigned this to `/checklist`: nothing on the 626Labs board covered
Google sign-in or the MCP server, both new this cycle. Two tasks created against project
`w9SoKLLYy7m80eXDTF19`. The stale "GUI Phase 3 — Not Started" entry is `/task-meditation`'s, not
this command's, and was left alone.

### Methodology preferences

Autonomous build mode, verification on, commit per item, no comprehension checks. None of these were
asked — the profile and the record answer all four (`mode: builder`, experience `experienced`, "runs
Claude Code as an autonomous build system with structured checklists and subagent delegation," and
three prior Cart cycles choosing autonomous at `/checklist`). Commit subject lines follow this repo's
existing voice rather than the estate's conventional-commit default; the log is declarative
sentence-case throughout and there is no repo keystone overriding it.

### Deepening rounds

Zero, and the reason is narrower than at `/spec`: there was nothing left to deepen. The PRD closed
nine forks with reasoning attached, the spec closed five more and enumerated nine open issues with
owners, and `/checklist` found no fork the record could not already resolve. The three genuine calls
here — checkpoint placement, the two merges, and whether the transport and tools ship as one item or
two — are sequencing judgments, which is this command's own job rather than a question for the
builder.

### Active shaping

No live builder input this run. Two assumptions stay marked `(default — confirm on next interactive
run)`: the 8,000-character scene cap and the three-persona count, both inherited unchanged from
`/prd` and `/spec` rather than re-inferred. The cut line was copied into the checklist verbatim from
`scope.md` so it is never re-decided under deadline pressure.

## /build

Autonomous mode, verification on, checkpoints after items 4, 7, 9, and 11, commit
per item. Baseline before the first item: 175 tests green, 20 commits ahead of
`origin/main`.

### Sequencing deviation, taken on purpose

Item 1 is a browser sign-in and a Cloud Console step, so it is the builder's to run
rather than the agent's. Its failure reshapes items 2, 3, and 4 and nothing else, and
items 5, 6, and 8 declare no dependency on Gate A. So Gate B ran in parallel with item
1 rather than idling behind it. The ordering argument `/checklist` made is intact: item
1 still landed before a single line of Gate A code was written.

### Item 1 — the Google link flow, proved against the live API

Both claims **PASS**. Recorded here because the item's Verify asks for both round trips
either way, and because a documented-but-unverified claim is what this item existed to
convert into a measured one.

**Claim 1 — `response_type=id_token` is still honoured for this client.** Confirmed. The
authorize URL returned a `#id_token=` fragment, and `state` round-tripped byte-identical.
Google's own copy steers toward Google Identity Services here, which is the remote
`<script>` this project forbids; the implicit flow it steers away from still works.

**Claim 2 — `signInWithIdp` accepts a Google ID token minted outside Firebase's handler,
carrying a nonce Firebase did not issue.** Confirmed, `HTTP 200` on the **first** attempt.
The `&nonce=<raw nonce>` retry the spec names as the first fallback was never needed, and
the server-side authorization-code exchange named as the second is therefore **not built**.

**The uid survived.** `uid_before` and `uid_after` are byte-identical (`ROfFQgQW…j6i1`).
Linking preserves the uid, so the rail lists the same rooms across the link. That is
`prd.md > Identity That Outlives The Browser`'s first linking criterion, and it is now a
property this cycle measured rather than one it read off a doc page.

**Request shape** (`accounts:signInWithIdp?key=<FIREBASE_API_KEY>`), credentials elided:

    { "postBody": "id_token=<google id_token, 1305 chars>&providerId=google.com",
      "requestUri": "https://star-390753828501.us-central1.run.app",
      "idToken": "<the anonymous Firebase ID token, 856 chars>",
      "returnSecureToken": true,
      "returnIdpCredential": true }

**Response shape**, values elided, field names verbatim:

    federatedId, providerId="google.com", email, emailVerified=true, firstName,
    fullName, lastName, photoUrl, localId, displayName, idToken (1006 chars),
    refreshToken (482 chars), expiresIn="3600", oauthIdToken (1274 chars),
    rawUserInfo (621 chars), kind="identitytoolkit#VerifyAssertionResponse"

Three things in that shape item 2 depends on. `expiresIn` is a **string**, so
`web/auth.js:48`'s `remember()` already does the right thing with it via `Number()`.
`localId` is the uid to assert against. And there is **no `oauthAccessToken`** — the
implicit ID-token flow returns no access token at all, so nothing in this exchange
produces a Google credential with API reach, which narrows what a leaked fragment could
ever be worth.

### `spec.md > Open issues` #2, closed

The client id in play is `390753828501-vmm840999…`, the web client Firebase
auto-provisions for its own Google provider. Because it is the client the provider
already trusts, the token's `aud` matched with **no whitelist step**. Using any other
client id would have required adding it to the provider's allowed list; that path exists
and was not needed.

### The failure that actually cost the round trip, and it was not either claim

The first attempt died on `Error 400: redirect_uri_mismatch`, and the diagnosis took a
detour worth writing down because the console invites it. Google's credentials page has
two sections with **opposite rules**: *Authorized JavaScript origins* rejects a path or a
trailing slash, and *Authorized redirect URIs* requires the full URL and accepts both. The
two redirect URIs went into the origins box first, where the console refused them with a
message about trailing slashes that reads like the URIs are wrong rather than like the
box is.

`https://star-390753828501.us-central1.run.app/` and `http://localhost:8000/`, trailing
slashes intact, belong in **Authorized redirect URIs**, alongside the
`__/auth/handler` entry Firebase put there. The localhost registration is the one worth
naming twice: skipping it is the failure that works in production and looks like a broken
button on a laptop, which is a rehearsal-week discovery rather than a day-one one.

This is precisely what `/checklist` put item 1 first to find. It cost one browser round
trip and a console edit. Discovered on day four, it costs the ordering argument.

### One live artifact this left behind

The throwaway anonymous account minted by the prover is now permanently linked to a real
Google identity in `star-research-dept`. It is not a leak and it is useful — it is the
linked uid items 3 and 4 need to exercise the allow path, and the only one that exists.

### Checkpoint 2 — Pipeline B, run live against a real room

Room `92f7835a` built from a fictional 1962 Memphis treatment in **135s**, status `complete`.
One check against it, with a Compact Cassette planted as the anachronism and a cell phone
planted as the blatant one. **25 seconds**, well inside the 180s ceiling.

**`search_count: 1`. Pipeline B genuinely called `parallel_search`.** This is the
partner-track pass/fail and it is now measured rather than asserted, independently of
Pipeline A.

**`parse_rate: 1.0`, `field_notes` empty.** `spec.md > Open issues` #3 asked whether the
verifier's prose grammar would hold, with a schema'd-structurer fallback waiting if it
came in under 70% across five runs. First run: every line parsed. The fallback stays
unbuilt.

**The room answered six of eight claims; one search covered the rest.** `citation_sources`
reads `room` for the Satellite Record Shop, McLemore Avenue, acetates, lacquer practice,
WDIA, and union scale, and `search` only for the cassette deck. The department consulting
its own files before spending is not a slogan here, it is what the payload says happened.

**The planted anachronism landed with a real citation.** `cassette deck` came back
`ANACHRONISM`, sourced to Philips' own 1963 announcement, with the note "Compact cassette
technology was introduced by Philips in August 1963." That is the demo's centrepiece and it
works.

**`budget_exhausted: false`, `unsourced_count: 0`, `cover_note: ""`** — all three correct
for a room with files and a scene with claims.

Cross-uid isolation, replay, and delete all confirmed against the live service. A stranger
asking for this room and a stranger asking for a room that never existed both receive
`{"detail":"Unknown run"}`, byte-identical. `DELETE` returned 204, the subsequent `GET`
404, and the list came back empty.

### The defect the checkpoint found, and it is a prompt, not a pipeline

`cell phone` in a 1962 scene came back **`UNVERIFIABLE`**, not `ANACHRONISM`.

Nothing malfunctioned. The verifier issued a verdict with **zero citations**, and
`star/verdicts.py`'s downgrade rule did exactly what it was built to do: a `confirmed` or
`anachronism` carrying no hydrated citation has nothing behind it, so it is downgraded and
the reason is stated. The guard fired correctly on its first live encounter with the case
it exists for.

The cause is upstream. `verifier`'s instruction says to search only for the claims the
room's files do not answer, and the model read its own certainty as an answer — it spent
**1 of 8** available searches. A verdict from memory is exactly the unearned confidence this
design exists to refuse, and the downgrade is the system refusing it correctly.

What that leaves on screen is honest and bad: the most obvious anachronism in the scene
reads as unverifiable, under a note that says there was nothing to check it against and
then asserts the fact anyway.

The fix is one instruction line in `star/agents/script_check.py`: a verdict requires a
source actually read, so search for anything the room's files do not carry, **even when
certain**. The pipeline needs no change and `verdicts.py` needs no change. Recorded here
rather than fixed silently, because the honest reading is that the annotator passed its
first live test by catching its own pipeline.

### Checkpoint 1 — Your card, measured rather than judged

The card is a fourth stage state (`#account-panel`, `showAccount()`), entered only from
`Your card` at the foot of the rail. Measured in headless Chrome against the real
stylesheets and the real `renderAccountCard()`, at five viewports:

| Viewport | Manila, room filed state | Without the rail entry | Card's own state |
| --- | --- | --- | --- |
| 1440x900 | **62.1%** | 62.1% | 50.4% |
| 1024x800 | **55.9%** | 55.9% | 59.8% |
| 900x800 | **73.4%** | 76.3% | 70.6% |
| 560x900 | **72.3%** | 74.9% | 79.9% |
| 390x844 | **68.2%** | 70.9% | 71.3% |

Union area of the manila rectangles clipped to the viewport, by a coordinate sweep, so
overlapping surfaces are not double-counted. The rule is >40% and the floor is 55.9%.
Above 900px this item costs the room's filed state **nothing** — its only addition there
is a rail entry, and the rail is not manila. Below 900px the rail is a top bar and the
entry takes a row, which pushes the stage down by 2.6-2.9 points. Still 68% at the worst
width. No horizontal overflow at any width, and no descendant wider than its own box.

**The headless window clamp, which nearly produced a false alarm.** `--window-size=390`
on Windows lays the page out at **504px** and then crops the screenshot to 390 — which
looks exactly like a horizontal overflow and is not one. Every narrow number above was
taken inside an iframe of the honest width instead. Task 9's `check-390.png` was captured
the same way and should be re-read with that in mind.

### Two `.rail-*` collisions, one new and one shipped

`rail-` means two different rails in this app: the cabinet's rail of saved rooms
(`web/shell.css`) and the citation rail beside a marked scene (`web/scriptcheck.js`,
styled in `web/scene.css`, which owns about twenty `.rail-*` names). `scene.css` loads
after `shell.css`, so on a tie the citation rail wins.

- **New, caught before it shipped.** The card's entry was called `.rail-card`, which is
  `scene.css:341` — the verdict card. It rendered with an onionskin background inside the
  dark rail (`backgroundColor: rgb(233, 226, 210)`, read off the engine). Renamed to
  `.rail-foot`, which is not in that set.
- **Shipped in Task 9, and fixed here.** `.rail-head` is declared in both files. The
  cabinet rail's brand block was computing `align-items: baseline` with a **0px** column
  gap instead of `center` and `0.7rem`, putting the ✶ flush against the wordmark with
  their centres 7px apart. `shell.css` now scopes its rule to `.rail > .rail-head`
  (0,2,0), which wins without touching `scene.css`, whose rule is right for the surface it
  was written for. Measured before and after: `baseline / 0px` -> `center / 11.2px`.

This is the `.tab` / `.drawer-tab` collision of Task 5 for the second and third time. Any
new `.rail-*` name in `shell.css` has to be checked against `scene.css` first.

### The retention copy, re-verified against post-link truth

Two clauses of the four changed, and the rule applied was the Task 2 rule — a clause that
cannot be verified from the code is cut, never softened.

- **Kept:** "Your treatment itself is not stored — only the profile the department
  extracts from it, and the research it produces." `star/store.py`'s `room_to_document`
  writes twelve fields and none of them is the treatment; `StoryProfile` carries six
  extracted fields and none of them is the text.
- **Changed:** "kept under this browser's identity" -> "filed under the identity you are
  signed in with." The old clause goes false the moment an account is attached, which is
  the entire point of attaching one. The new one is true before and after, and names no
  account, because this path must not.
- **Cut:** "Nothing is visible without your sign-in token." True of the server today —
  every `/api` read goes through `_require_uid` — but what a reader takes from it is *only
  this browser can see this*, and an issued MCP token is a long-lived credential pasted
  into an agent's config that reads the same rooms. The whole of it is now stated on the
  card, before the link and before the token, where a reader can act on it.

The intake path's silence is asserted rather than assumed: `tests/js/test_intake_silence.mjs`
strips comments and tags out of `index.html`, folds the reader-visible attributes back in,
and proves zero occurrences of "account" and exactly one of "Google" — the footer's build
credit, pinned by exact string. The card's copy is not in the document at all:
`#account-panel` ships empty and `web/account.js` fills it only when the rail's entry is
used.

### Checkpoint 4 — the agent door, driven live

`initialize` → `notifications/initialized` → `tools/list` → `list_rooms` → `get_room`, over
HTTPS against the running service with a real bearer token. `GET /mcp` answers 405,
`POST /mcp` with no credential answers 401 before the body is read, and
`notifications/initialized` answers **202 with a zero-byte body**.

Every refusal was read as an agent with no screen, and every one names what failed, why,
and what to do next:

- A room id that does not exist says to call `list_rooms`, and volunteers that a room under
  somebody else's account answers identically, so the caller is told the answer is not an
  oracle rather than being left to infer it.
- A 9-character treatment names the 40-character floor, the count sent, and the three things
  the planner actually needs: when it is set, where it happens, what the characters do.
- **`{"roomId": …}` is refused by name** — "does not take an argument called `roomId`. It
  takes one argument, `run_id`" — rather than as a missing-argument error about an argument
  the agent is certain it sent. That is the loop a persona would otherwise never escape.
- An unknown **tool** returns `isError: true` and lists the four; an unknown **method**
  returns JSON-RPC `-32601`. The split the error posture turns on, holding on the wire.

### A harness gotcha worth writing down

The first bearer token minted for this walkthrough resolved perfectly in the minting process
and was refused by the server. The token was fine. The **script that wrote it never called
`load_dotenv()`**, so its Firestore client fell back to the ADC default project — which is
whatever `gcloud config get-value project` happens to be, here `project-626labs` — while the
server reads `GOOGLE_CLOUD_PROJECT=star-research-dept` out of `.env` at import.

Two stores, two databases, one silently empty. Nothing raised: the write succeeded and the
read succeeded, both against the wrong project, and the only symptom was a generic refusal
at the door. **Any maintenance script that touches this repo's Firestore must call
`load_dotenv()` before importing `star.store`**, or it is talking to a different database
than the service is. `star/server.py` gets this right at line 21 and that is the only reason
the service does.

## Item 12 — the persona harness, and the audit that is the point

Three personas, three committed transcripts in `harness/runs/`, driven by `gemini-3.6-flash`
through `google-genai` against the live service on `http://127.0.0.1:8000`. The client is
`harness/client.py` on `urllib.request` and the standard library: no new dependency, nothing
third-party in the frame, and nothing on screen a Google-track submission has to explain.

The personas differ in the two things that actually change what an agent experiences here —
**what it already has** and **how well it is wired**. A third persona that only asked
different questions would have been one persona run three times.

| Persona | Wiring | Account | Turn cap | Turns used | What it did |
| --- | --- | --- | --- | --- | --- |
| `writer` | real `inputSchema` from `tools/list` | one filed room | 8 | 5 | `list_rooms`, `get_room`, two `check_scene` calls, then reported |
| `fumbler` | one generic passthrough; it writes its own argument JSON | one filed room | 12 | 3 | guessed `room_id`, was corrected, got it right, reported |
| `newcomer` | real `inputSchema` | a real uid with nothing filed | 8 | 2 | `list_rooms` on an empty account, `get_room` on somebody else's id, reported |

**The `fumbler`'s wiring is the load-bearing design call.** A model handed a correct
`FunctionDeclaration` cannot easily send `roomId` — the API fences it into the declared
shape — so the wrong-arguments posture is unreachable through the front door. Taking the
schema away and making the model write its own argument JSON is what a lot of real MCP
integrations look like anyway, and it is the only way to put the argument refusals under
load. It worked on the first turn of both runs.

**The `newcomer`'s account is real.** A fresh anonymous account was created through the same
`accounts:signUp` call `web/auth.js` makes, and its token was minted straight through
`star/tokens.py`. `POST /api/tokens` refuses an anonymous `sign_in_provider` by design and
that refusal is correct for the browser; the thing under test here is the MCP door, not the
issuing policy, so the token was written directly. Building a room and deleting it to
manufacture an empty state would have spent money to produce a worse fixture.

### The audit — every failure a persona hit, and what happened to it

Six failures across the runs. **Five were diagnosable from the response alone, and each
persona said so in its own closing report without being asked which ones were.** The sixth
was the harness's, not the department's.

| # | Persona | What it called | What came back | Diagnosable alone? |
| --- | --- | --- | --- | --- |
| 1 | `newcomer` | `list_rooms` on an empty account | "No rooms are filed under this account yet. That is not an error: the account is real and the token works, there is just nothing in it." | Yes. It reported the account as valid-and-empty rather than as broken |
| 2 | `newcomer` | `get_room` with a colleague's id | `ROOM_NOT_FOUND`, including the sentence saying a room under somebody else's account answers identically | Yes, and it restated the no-oracle property back in its report unprompted |
| 3 | `fumbler` | `check_scene` with `room_id` | "`check_scene` does not take an argument called `room_id`. It takes arguments `run_id` and `scene`." | Yes. Corrected on the next turn and succeeded |
| 4 | `fumbler` (first run) | `get_room` with `room_id` | Same shape, naming the one argument that tool takes | Yes |
| 5 | `writer` | `check_scene` on a scene from a different story | Four claims, four `confirmed`, and nothing saying the room had answered none of them | **No. Fixed, see below** |
| 6 | `fumbler` (first run) | `check_scene`, second attempt | A **harness** block, not a service response | N/A. Harness defect, fixed in `harness/run.py` |

**Failure 5 is the finding, and it is fixed in `star/mcp/tools.py`.** An off-story scene
checked against a room that knows nothing about it comes back four-for-four `confirmed`,
because the verifier falls through to a live search and answers correctly about the world.
Nothing malfunctioned and the answer was worthless: the room is what supplies the era, so
with the room contributing nothing, a phone released in 1998 is `confirmed` in a scene that
never says what year it is. The tally line read as a clean pass. The per-citation `source`
fields said `search`, `search`, `search`, `search`, and only a model that parsed 10KB of
JSON would have known.

`_cover_note` does not cover this. It fires when the room filed **no sources at all**, and
its own docstring hands the per-claim question to `citation_sources`. A room full of sources
that answer none of this scene is the case neither of them was watching.

The fix is `_provenance()` in `star/mcp/tools.py`: one sentence in the `check_scene` summary
counting the sources behind the verdicts by which ledger produced them, with a distinct
sentence for the zero-from-the-room case that names what it means. Exercised directly
against both stored results:

- on-story: *"Of the 6 sources behind these verdicts, 5 came out of this room's own files
  and 1 from a search this check ran just now."*
- off-story: *"None of the 8 sources behind these verdicts came out of this room's own
  files. Every one of them is from a search this check ran just now, so the room contributed
  nothing. That happens when a scene covers ground the room does not hold, including when the
  scene belongs to a different story than the room was built for, and it means these claims
  were judged against the world at large rather than against this room's era and setting."*

It lands in the tool layer and not in `star/server.py`, deliberately. The browser has a
citation rail that shows provenance next to every source; the agent has a paragraph, and
this is the half of the department that only the agent was missing.

**Verified by direct exercise rather than by a live re-run**, because the server on port 8000
runs without `--reload` and restarting it was out of bounds for this item. `_check_scene` was
driven against both persisted `ScriptCheckResult` documents with a stub `Calls`, which proves
the string deterministically and spends nothing. It reaches the wire at item 13's deploy, and
the three committed transcripts are honest records of the string as it stood when they ran.

**Failure 6 was the harness's own, and the way it failed is worth keeping.** The spend guard
originally charged a persona's `check_scene` allowance on the *attempt*. The `fumbler`'s
first attempt was refused on `room_id`, which never reaches the pipeline and buys nothing, so
the one call it was going to get right was the one it was denied. Told it could not call the
tool, the persona **wrote five verdicts straight off the research bible instead**, three of
them flatly contradicting what the real check returned, under headings reading "Research
Bible Grounding". That is exactly the unearned confidence this project's whole architecture
exists to refuse, produced in one turn by a model with a room payload in its context and no
way to check. The guard now charges only when the department accepts the call
(`harness/client.py`'s `was_refused`), and the re-run went fumble, correction, success in
three turns.

### The `check_scene` fix from Checkpoint 2 held

Checkpoint 2 left a defect open: the verifier read its own certainty as an answer, spent 1 of
8 searches, and the most obvious anachronism in the scene came back `unverifiable` because
the downgrade rule correctly refused a verdict with nothing behind it. The instruction fix
landed before this item. Under the harness the same shape came back right: the planted Moog
synthesizer in a 1962 scene returned **`anachronism`, cited, noted "invented in 1964 and
first commercially produced in 1965"**, on runs that spent 3 and 5 searches rather than 1.

### Open issue #4 — can any MCP client other than the harness connect?

**Answered: yes for any client configurable with a static bearer header, no for a client that
insists on OAuth discovery, and browser-based clients are additionally gated by `Origin`.**
Measured against the live service rather than reasoned about:

| Probe | Answer |
| --- | --- |
| `GET /.well-known/oauth-protected-resource` | 404 from the static mount |
| `GET /.well-known/oauth-protected-resource/mcp` | 404 |
| `GET /.well-known/oauth-authorization-server` | 404 |
| `GET /.well-known/openid-configuration` | 404 |
| `POST /mcp` with no credential | 401, `WWW-Authenticate: Bearer` with **no `resource_metadata` parameter** |
| `POST /mcp` with a foreign `Origin` | 403 |
| `POST /mcp` with `Origin: http://127.0.0.1:8000` | **403**. The default allow list is the Cloud Run URL and `http://localhost:8000`, and `127.0.0.1` is not `localhost` as an origin |
| `tools/list` with no prior `initialize` | 200, the four tools. The 2026-07-28 handshake-free shape is served |
| `MCP-Protocol-Version: 2026-07-28` | 200 |
| `MCP-Protocol-Version: 2024-11-05` | 400, naming the four revisions it does speak |
| `resources/list`, `prompts/list` | `-32601`, naming what it does offer |
| `Accept: text/event-stream` alone | 200 with JSON. `Accept` is not inspected at all |

A discovery-first client stops at the challenge: there is no `resource_metadata` to follow
and nothing at any of the four well-known paths. A static-header client connects, and the
proof is that the harness is one and there is nothing harness-shaped in the server.
`star/mcp/router.py` reads one header and never looks at `clientInfo`.

**No third-party client was configured, and that is a decision rather than a gap.** Every
route to one puts a live bearer token into a plaintext client config on disk. This repo has
already shipped a live token in `.mcp.json` once, the environment keystone bars the pattern
outright, and `prd.md > The Submission Surface` requires no third-party client chrome
anywhere near this artifact. The probes above answer the question mechanically without buying
that risk, so the risk was not bought.

Two things fell out of the probes and neither is a defect in the deployed path. `127.0.0.1`
being refused where `localhost` is allowed is correct per RFC 6454 and only reachable by a
browser-based client on a dev origin; the deployed browser's origin matches. `Accept` going
uninspected is within the transport spec, which requires the client to accept both content
types and lets the server pick.

### Open issue #5 — room payload size over MCP

**Answered, and the estimate in `spec.md` was low by an order of magnitude. `get_room` on the
complete room returns 152,007 bytes.**

| Section | Bytes |
| --- | --- |
| `categories`, four drawers, 31 findings | 127,090 |
| `research_bible` | 16,183 |
| `research_plan` | 3,898 |
| `story_profile` | 523 |

The open issue framed this around the bible at 11,000 to 17,000 characters. The bible is
16,183 bytes and is **not the problem**: the drawers are five sixths of the payload, and the
reason is citation excerpts. One finding runs about 2,700 bytes because its excerpt is a real
slab of the page a search returned, which is exactly the property that makes a citation
trustworthy and exactly what makes it large.

What that costs an agent, measured rather than guessed: roughly 37,000 tokens for one read,
re-sent on every subsequent turn of a tool loop. The `writer` run pulled 184,810 bytes from
the department in total and 152,007 of it was one call. Both personas that read a room did it
once and worked from context afterwards, and neither degraded, so this is a cost and not a
break today.

The decision it was supposed to inform: **`get_room` does not get a way to ask for less
before 2026-09-07.** A room read is the one call that carries the whole point of the product,
an agent that gets a summary has to call again for the thing it wanted, and the shape that
would fix it properly is a `detail` argument plus a per-finding read, which is a fifth tool by
another name and is ruled out by both `spec.md` and `prd.md`. Recorded here so the number is on
the record and the successor has it. If it is ever paid down, the cut is the citation
excerpts, not the bible.

### Open issue #6 — `check_scene` against a scene from a different story

**Answered, and the prediction in `spec.md` was wrong in a more interesting direction.** The
issue expected every claim to come back unverifiable-by-way-of-irrelevant. What actually
happens is the opposite: an Icelandic trawler scene checked against the 1962 Memphis room came
back **4 claims, 4 `confirmed`, 0 anachronism, 0 unverifiable**, `search_count: 2`,
`cover_note: ""`, every `citation_sources` entry reading `search`.

The verifier falls through to a live search, answers correctly about the world, and every
verdict is defensible on its own terms. The bad answer is not irrelevance, it is **a clean
pass that means nothing about the story**. The room is what supplies the era; with the room
contributing nothing, "Nokia 5110" is `confirmed` in a scene that never stated a year, and the
tally reads like a scene that checked out.

The `writer` persona reached that on its own, *"it cannot check whether your Icelandic trawler
story is set in the right year for that phone"*, and it reached it from the story profile it
had read earlier rather than from the check's own answer. That is the gap `_provenance()` now
closes. **Not fixed beyond the sentence, and the reason stands:** refusing an off-story scene
would require the department to judge whether a scene belongs to a room, which is a model's
opinion about a writer's intent and precisely the kind of judgment this project keeps out of
the pipeline. Naming what the check actually leaned on lets the reader draw the conclusion
from a fact instead.

### What item 12 spent

- **3 `check_scene` calls** that the department accepted, against a ceiling of 5: two in the
  `writer` run (3 and 2 searches) and one in the `fumbler` re-run (5 searches). **10 live
  searches, about $0.05.** Two further `check_scene` calls were refused on their arguments and
  spent nothing.
- **0 `build_room` calls.** The personas ran against room `92f7835ac882`, built before this
  item, which is `spec.md > Open issues` #7's own mitigation.
- **13 Gemini turns** across four persona runs (5 + 5 + 3, plus the 5-turn first `fumbler` run
  that the guard fix retired), on `gemini-3.6-flash`. Turn caps were 8 / 12 / 8 and none was
  reached.
- Three scenes stored with room `92f7835ac882` by the checks, as `check_scene`'s own
  description says they would be. Deletable from the room's script-check panel.

### Item 13 — what was verified, and what is deliberately not done

**Verified by probe, not by assertion.** These were run rather than reasoned about:

- **Credential sweep over the whole history**, not the working tree, because the visibility
  flip is irreversible in the sense that matters. `.env` and `.mcp.json` never entered
  history and both are gitignored. No credential-shaped file is tracked. Two pattern hits,
  both benign: a synthetic token fixture in `tests/js/test_account_card.mjs`, and the
  Firebase web key in `.env.example`, which is public by design and already served to every
  visitor by `/config.js`.
- **`pip-audit`: zero vulnerabilities in the pinned runtime set.** Six findings, all in
  `pip` itself in the local venv — the installer, not a runtime dependency, and not what the
  image ships, since the Dockerfile takes whatever `python:3.12.12-slim` carries. **No pin
  moves before 2026-09-07**, and none needed to.
- **`maxScale` and `minScale` both read `1`** on the serving revision `star-00004-4nq`,
  read off the *revision* rather than the service YAML, which lies (`INFRASTRUCTURE.md:213-236`).
- **`/docs`, `/redoc`, `/openapi.json` all answer 404.** Secrets come from Secret Manager
  via `--set-secrets`; only public identifiers are in `--set-env-vars`.
- **No Firestore ruleset is deployed**, which is the correct posture rather than an omission.
- **Every `/api` route is guarded.** One correction to my own first audit: it reported
  `stream_events` as `_require_uid`-guarded, which was a grep matching a docstring. That
  route cannot read an Authorization header — an `EventSource` sends none — and is guarded by
  `compare_digest` on a per-run capability key. The code was right; the audit was naive, and
  it is worth recording that the audit was the thing that nearly shipped a false clean.
- **A fresh clone of `HEAD`** carries 122 files, an MIT `LICENSE` GitHub will detect, no
  `.env`, and a `pyproject.toml` whose explicit package list includes `star.mcp`.

**Deliberately not done, and not because it was forgotten.** Push, visibility flip, deploy,
video, and Devpost submission are outward-facing or irreversible, and the builder's approval
of "items 12 and 13" is not the same as authorising a private repo to go public. Every gate
in front of them is verified and the evidence is above; the acts themselves are the
builder's. The README screenshot needs a logged-in browser session that owns a filed room,
which is the builder's session and a ten-second job there.

### /build — autonomous run summary

**12 of 13 items complete.** Item 13's ship half (push, visibility flip, deploy, video,
Devpost) is the builder's and is deliberately not done. 473 tests green,
`ruff check star tests scripts harness` at 0, 36 commits ahead of `origin/main`.

**The checklist was not revised.** Its sequence held from first item to last, with one
scheduling deviation taken on purpose: item 1 is a browser-and-console step only the builder
can run, and its failure reshapes items 2-4 and nothing else, so Gate B ran in parallel with
it rather than idling. Item 1 still landed before a line of Gate A code was written, which is
the whole of the ordering argument `/checklist` made.

**Four checkpoints, all passed.** Checkpoint 2 was the one that earned its place: Pipeline B
ran live against a real room, `parallel_search` genuinely executed (`search_count > 0`, the
partner-track pass/fail), and `parse_rate` came back 1.0, which retired the schema'd-structurer
fallback the spec had held in reserve.

**Six defects found that no unit test would have caught**, each in a different way:

1. **The search budget inverted at its safest setting.** `state.get(...) or default` meant
   `STAR_MAX_SEARCHES_PER_CHECK=0` handed a run the build's 30. Found by reading a subagent's
   own honest flag rather than by a test.
2. **The anchor matcher silently lost a mark.** An occurrence scan advancing by the needle's
   length cannot find a repeat hiding under an accepted span. Found by mutation-testing a
   suite that had passed on the first run.
3. **A partial room threw a `ReferenceError`** and took the whole docket with it, because
   `renderDocket` read a free variable on the one branch that evaluates it. Shipped, and
   invisible to every complete run.
4. **The verifier answered from memory.** It spent 1 of 8 searches and stamped nothing on the
   most obvious anachronism in the scene. Found by a live run, not by a fixture.
5. **An off-story scene read as a clean pass.** Four confirmed, nothing saying the room had
   answered none of them. Found by a persona, which is exactly what the harness is for.
6. **The harness's own spend guard charged refusals**, and the starved persona wrote five
   verdicts off the research bible, three of them wrong. The single sharpest artifact this
   cycle produced: the failure mode the whole architecture exists to refuse, reproduced in one
   turn by the same class of model the pipeline runs on.

**Three claims in the written record turned out to be false**, all of the same shape — copy
asserting a control the code did not have. `.env.example` said security came from "Firestore
rules" this project deliberately does not deploy. The README said STAR "verifies" claims, in
the first paragraph a judge reads. The intake said "nothing is visible without your sign-in
token", which a long-lived MCP credential makes false. Each was cut or corrected rather than
softened.

**And one of mine.** The first route audit reported the SSE stream as `_require_uid`-guarded
by matching a docstring. The code was right; the audit nearly shipped a false clean.
