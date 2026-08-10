# STAR — Cycle #19 scope

> Vibe Cartographer cycle **#19**, `/scope`, 2026-08-10. Mode: fully-autonomous (*Autonomous —
> Self*). Persona: Architect. Inputs: [`docs/builder-profile.md`](builder-profile.md),
> [`docs/HANDOFF.md`](HANDOFF.md), [`docs/design/DIRECTION.md`](design/DIRECTION.md), the four
> design-research files, [`docs/INFRASTRUCTURE.md`](INFRASTRUCTURE.md),
> [`docs/adversarial-review-2026-08-06.md`](adversarial-review-2026-08-06.md), the four
> `docs/superpowers/` plans, [`.vibe-access/state/inventory.json`](../.vibe-access/state/inventory.json),
> the 626Labs board, and the repo read live.

## Idea

**STAR stops being a website and becomes a research department an agent can call.**

Pipeline A ships, is deployed, and reads as THE MORGUE. This cycle adds the second half of the
thesis: the same department, reachable over MCP by a desktop agent or a test persona, with a real
identity behind every call, and a second pipeline that checks a scene against the room it belongs to.

The one-sentence version, for the monitor: *every studio has a research department, now every
writer has one and so does every agent they run.*

## Who It's For

Three users this cycle, where there was one.

**The screenwriter.** Unchanged and still primary. Hostile to AI, burned by slop, needs to verify
a claim before trusting the page it sits on. Everything the design research established stays in
force. Cycle #19 must not cost this user anything.

**The agent.** New. A desktop agent, or Claude Code, or anything speaking MCP, driving a room build
and a script check without a browser. It needs tool schemas that describe the department honestly,
an auth handshake that survives a process restart, and failure messages written for a reader who
cannot see the screen.

**Este, running personas as a test harness.** The reason that reframed this cycle. Putting several
agent personas behind separate runs and having them use the tools the way different users would is
synthetic user testing, and it is the one justification for the MCP surface that a judge can verify
in the repo rather than take on faith. It also raises the bar on the tool descriptions and the error
strings: they stop being plumbing and become the product, because a persona that cannot tell why a
call failed is a test that produced nothing.

**The unmet need underneath all three:** research is scene-triggered, not front-loaded
(`critique-adversarial.md:41`). A writer hits page 40 and needs one fact in thirty seconds, mid-draft.
A batch job started back at the logline cannot serve that. An agent-callable `check_scene`, invoked
from wherever the writer actually works, is the first thing in this product that can.

## Inspiration & References

Everything below already exists in the tree or the estate. `/spec` reads these rather than
re-deriving them.

| Source | What it carries |
| --- | --- |
| [`docs/design/DIRECTION.md`](design/DIRECTION.md) | THE MORGUE, the palette, the type stack, the two make-or-break rules, the seven behavioural obligations |
| [`docs/design/critique-adversarial.md`](design/critique-adversarial.md) | The screenwriter's close-the-tab moments, in their own voice |
| [`docs/design/research-ai-aversion.md`](design/research-ai-aversion.md) | Why calibrated confidence beats blanket confidence; the purple-gradient tell |
| [`docs/design/research-screenwriter-practice.md`](design/research-screenwriter-practice.md) | "Grounded," primary-vs-secondary as the trust axis, scene-level cues |
| [`docs/design/visual-directions.md`](design/visual-directions.md) | The three directions and why the other two lost |
| [`docs/INFRASTRUCTURE.md`](INFRASTRUCTURE.md) | Live service, the single-instance argument, the secrets map, the Firestore posture |
| [`.vibe-access/state/inventory.json`](../.vibe-access/state/inventory.json) | 5 routes, 4 `token` + 1 `none`, 2 unmapped. The agent-access surface, already inventoried 2026-08-10 |
| 626Labs dashboard `mcp-server` | Estate precedent: sha256-hashed API keys and a single-tenant OAuth 2.1 AS running side by side, cheap path shipped first |
| [`docs/adversarial-review-2026-08-06.md`](adversarial-review-2026-08-06.md) | H1/H2/H3 and what was actually fixed |

Design energy is decided and not reopened: Cabinet Green ground, Manila cards owning >40% of the
filed room, Aniline violet as flat stamp ink, Oxide Red for flagged. Archivo Narrow / Newsreader /
Sligoil, self-hosted, no CDN.

## Goals

Three parts, and they are not independent. **Part 1 exists to serve Part 2.**

### 1. A durable identity, added rather than substituted

Google sign-in, but as an *upgrade* on the anonymous session, not a replacement for it.

The stated goal at `/onboard` was replacing anonymous Firebase auth with `GoogleAuthProvider`.
Narrowed here, deliberately. The sign-in wall is the exact close-the-tab moment
`critique-adversarial.md:9` names, and `DIRECTION.md:54` records our silence as the rebuttal to it.
A hard Google gate hands that objection back, and it lands before a judge sees a single stamp.

So: silent anonymous stays the front door. Google linking is offered only where it buys something
real, which is an MCP credential that outlives a browser profile. Firebase upgrades an anonymous
account to a Google credential while preserving the uid, which is what keeps the rooms from
vanishing on link. `web/auth.js` runs raw Identity Toolkit REST rather than the SDK, so `/spec`
confirms the REST shape rather than assuming it.

The retention disclosure in the intake becomes *more* load-bearing once a real identity is attached
to a stored treatment, not less. Obligation 5 does not get softened.

### 2. Pipeline B — Script Check

`ClaimExtractor → Verifier → Annotator`, emitting `CONFIRMED` / `ANACHRONISM` / `UNVERIFIABLE` with
sources. Verifier checks the room's own citations first, then fresh `parallel_search`. `Claim` and
`Verdict` already exist in `star/models.py`.

The extractor returns the claim's **exact quoted text** from the scene, never a paraphrase. GUI
Phase 4's anchor matcher string-matches it client-side rather than trusting character offsets.

Plus the Phase 4 surface: the scene marked in place, citation rail following the selected mark,
assembled with `document.createTextNode` and real spans, never by building an HTML string from
scene text.

### 3. An HTTPS MCP server inside `star/server.py`

Four tools: `list_rooms`, `get_room`, `build_room`, `check_scene`. Per-user bearer tokens. OAuth 2.1
AS explicitly deferred, matching the estate precedent where the cheap path shipped first.

**Inside `server.py`, not as a separate service.** `_runs`, `_ip_limiter`, and `_daily_cap` are
in-memory module state and the deploy pins `--max-instances=1 --min-instances=1`. A second service
either breaks live runs or forces all three into a shared store in the same change. That is a
constraint, not a preference.

### Why this order: 1 → 2 → 3

Reordered from the `/onboard` statement of 1 → 3 → 2, for a mechanical reason rather than a
risk-averse one. **`check_scene` over MCP requires Pipeline B to exist.** MCP first means shipping
three tools and then reopening the server to add the fourth. Pipeline B first makes the MCP layer
one pass over a finished tool surface.

The schedule supports all three. 2026-08-10 to the hard deadline (Sun Sep 7, 2:00 PM PT) is 28 days;
to the Sep 5 target, 26. Pipeline A is built, hardened, deployed, and the Morgue is live at
`https://star-390753828501.us-central1.run.app`. This is not a triage cycle and was not scoped as one.

## What "Done" Looks Like

A judge opens the live URL and finds the room they watched in the video. A writer pastes a treatment
without signing in to anything, watches four drawers fill in parallel, and sees a citation stamped
with the domain and the date it was retrieved, or stamped `UNSOURCED` in oxide red with the clip
still on screen. They paste a scene and get it back marked, each verdict carrying the source it
rests on.

Then, separately: an agent that has never seen the web UI authenticates, calls `build_room`, polls
until the room is filed, calls `check_scene` against it, and gets back the same verdicts. Two
surfaces, one department, one ledger.

Concretely:

- Anonymous sign-in still silent, still zero-click, still the default path.
- Google linking available, preserving the uid and the rooms.
- Pipeline B live, with the anchor matcher tested against paraphrase and whitespace cases.
- Four MCP tools reachable over HTTPS with per-user bearer auth, and tool descriptions written for
  an agent that cannot see the screen.
- At least one persona-driven MCP run recorded as evidence the test-harness idea works.
- Repo public with the MIT badge in the About sidebar. GitHub already detects the license, so this
  is one `gh repo edit --visibility public` behind a credential sweep.
- ≤3-min video, English, no third-party logos or brands on screen.
- The Python suite green and `ruff check star tests scripts` at 0 findings.

## What's Explicitly Cut

Named cuts, with reasons. Some of these are engineering invariants rather than MVP trimming.

- **OAuth 2.1 authorization server for MCP.** Bearer tokens instead, hashed at rest. The estate
  already shipped this exact split once. An AS is a week of work that no judging criterion asks for.
- **Scaling past one Cloud Run instance.** `--max-instances=1 --min-instances=1` is load-bearing.
  Moving off it means moving `_runs`, `_ip_limiter`, and `_daily_cap` to a shared store *in the same
  change*, and nothing this cycle needs justifies that.
- **Firestore security rules.** No ruleset is deployed and that is the correct posture: with none
  deployed, Firestore denies all client access, and the server via ADC is the only path. One boundary,
  not two. Deploying permissive test-mode rules would silently void it.
- **Replacing anonymous auth.** Cut on design grounds, see Part 1. Additive, not substitutive.
- **Source-type inference (primary vs secondary).** The research says it matters. Doing it properly
  needs a classifier we do not have, and guessing from the domain is exactly the unearned confidence
  this design exists to avoid.
- **Export as a markdown zip bundle.** The board's designated cut line and it stays there. Ranked
  below the MCP surface, which now carries a platform argument the zip does not.
- **Any AI provider other than Google Cloud at runtime.** Disqualification criterion. ADK ships
  adapters for other providers; never use them.
- **Any code copied from `writer-studio-template`.** Its ideas are fair game, its code is not.
  Contest opened 2026-07-27; everything is authored in-window.
- **A build step in `web/`.** Native ES modules, plain CSS, no bundler.
- **Third-party browser requests.** Every font and library is a file in `web/vendor/`. The only
  permitted external calls are Google's identity endpoints.

### The cut line, if one is ever needed

Written down now so it is never decided under pressure. In order of what goes first:

1. The export zip. Already cut above.
2. The MCP beat in the video. The server ships and lives in the repo and the Devpost writeup; it
   just does not have to earn twenty seconds of a three-minute cut.
3. `check_scene` over MCP. Ship three tools, note the fourth as next.

**Pipeline B and the video never go.** The video is pass/fail, and its beat sheet has the script
check catching a planted anachronism as its centerpiece.

## Loose Implementation Notes

Non-binding. `/prd` and `/spec` refine or discard these.

**`build_room` over MCP is long-running, and most clients will not wait.** `star/config.py` records
observed runs of 146s to over 420s with a ceiling raised to 600s. A synchronous MCP tool call that
takes seven minutes is a broken tool. The likely shape is `build_room` returning a `run_id`
immediately with a separate poll or status tool, which also mirrors what the SSE stream already does
for the browser. This is the single largest unknown in Part 3.

**The abuse guards key on IP, and MCP gives them a new front door.** `_ip_limiter` is per-IP; an MCP
client is one address, and a desktop agent behind CGNAT could share one with strangers. The MCP path
probably wants a per-uid limiter rather than a per-IP one, or the daily cap becomes the only real
ceiling on spend. Worth resolving in `/spec`, not discovering in a bill.

**MCP token storage follows the dashboard precedent:** sha256 at rest, shown once at issue, never
recoverable. Do not invent a scheme when the estate already has one that shipped.

**The video's MCP shot has a brand problem.** `HANDOFF.md:44` forbids third-party logos and brands on
screen. The obvious shot is a desktop agent calling `build_room` while the web room fills live, which
is a strong twenty seconds and also puts a competitor's client in the frame of a Google-track
submission. `HANDOFF.md:34` scopes the runtime-AI restriction to what the project *runs*, so this is a
video-surface problem rather than a disqualification one. Three exits: a small in-repo MCP client we
author and drive with Gemini, a terminal-only shot with no client chrome, or the MCP story lives in
the repo and the writeup. `/prd` picks.

**`/spec` reads `.vibe-access/state/inventory.json` rather than re-scanning.** The route inventory
and auth model were captured on 2026-08-10.

## Open, and owned

Named rather than left silent.

- **20 commits ahead of `origin/main`.** All of Phase 3 exists on one machine. Cloud Run deployed
  from local source, so the live URL does not prove a push. Owner: Este, before any new branch.
- **Repo is private.** Correct through development; it is a submission-week gate, not an overdue
  item. GitHub already detects the MIT license, so the About badge follows the visibility flip.
  Owner: Este, submission week, after a credential sweep.
- **The board's "GUI Phase 3" task reads Not Started** while `eec40b2` is in the log and the live URL
  serves `tokens.css`, `drawer.js`, and `shell.js`. Stale, not wrong work. Owner: `/task-meditation`.
- **Nothing on the board covers Google sign-in or the MCP server.** Both are new this cycle and need
  tasks. Owner: `/checklist`.
- **`technical_experience.languages` and `.frameworks` are 107 days past a 90-day TTL.** Deferred by
  the autonomous contract, not stamped. Owner: the next interactive `/onboard`.
