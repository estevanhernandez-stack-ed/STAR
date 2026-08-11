# STAR — Session Handoff Brief

**For:** the next Claude session picking up this project
**From:** Cowork session with Estevan, 2026-08-06
**Repo:** https://github.com/estevanhernandez-stack-ed/STAR · local at `C:\Users\estev\Projects\STAR`

## What this project is

**STAR — Story & Treatment Agentic Research.** A multi-agent "research
department" for screenwriters. Pipeline A ("Build the Room") takes a
treatment and produces a cited research bible across four categories
(setting, objects & props, logistics, forces & conflicts) via live web
research. Pipeline B ("Script Check", not yet built) will verify a scene's
real-world claims against the room + fresh searches and flag anachronisms.

Pitch line: *"Every studio has a research department. Now every writer does."*
Concept lineage: the four research categories come from Estevan's
writer-studio-template (`C:\Users\estev\Projects\writer-studio-template`) —
that repo's *ideas* are fair game, its *code must never be copied in* (see
compliance below).

## Hackathon context — read this before touching anything

Entered in **Agentic Cinema: The Blockbuster Hackathon** (Devpost,
agentic-cinema.devpost.com), **Parallel partner track**, competing solo.
**Deadline: Sun Sep 7, 2026, 2:00 PM PT / 4:00 PM CDT.** Target submission
Sep 5. Full plan lives in the build plan doc from this session; the
non-negotiables:

1. **Runtime AI = Google Cloud only.** Gemini via `google-adk`/`google-genai`.
   NO other AI APIs/models/frameworks anywhere in the project (no Anthropic,
   OpenAI, etc.). ADK ships adapters for other providers — never use them.
   (Dev-time assistants like you are fine; the restriction is what the
   project itself runs.)
2. **Parallel track check = Search API called at runtime** via the official
   `parallel-web` SDK. Lives in `star/tools/parallel_search.py`. Task/Monitor
   APIs are optional extras, not substitutes.
3. **New code only, all authored in-window** (contest began Jul 27). Never
   copy code from writer-studio-template or any pre-existing project.
4. **Repo must be public** with MIT license **visible in GitHub's About
   sidebar**. As of handoff this was still unverified — the URL 404'd
   earlier (likely private). CHECK THIS.
5. **Submission needs:** hosted URL (Cloud Run planned), public repo,
   ≤3-min demo video (public YouTube, English, no third-party logos/brands
   on screen), Devpost form with findings/learnings.
6. Judging: Stage One is an automated-ish pass/fail (license visible, SDKs
   imported *and called*); Stage Two scores implementation / design /
   impact / idea, equally weighted.

## Architecture as built

- Python 3.12, `google-adk` (ADK 2.6.2 installed), `google-genai`,
  `parallel-web`, FastAPI, vanilla-JS frontend. No build step, no database yet.
- **Pipeline A** = `SequentialAgent`: `intake` (→ `story_profile`, schema'd) →
  `planner` (→ `research_plan`, schema'd) → `ParallelAgent` of 4 category
  researchers (tool: `parallel_search`, output `findings_<category>`) →
  `synthesis` (→ `research_bible` markdown).
- Entry points: `adk web` (package `research_dept/`, exposes `root_agent`)
  and `uvicorn star.server:app --reload` (FastAPI + SSE progress + web UI
  at `web/`).
- `star/config.py` centralizes models (`STAR_FAST_MODEL`/`STAR_SMART_MODEL`,
  default `gemini-flash-latest`), limits, and `validate_env()`.
- Search budget: per-run, stored in ADK session state via `tool_context`
  (module-global fallback only for direct script calls). Default 30/run
  (`STAR_MAX_SEARCHES_PER_BUILD`).
- `.env` needs `GOOGLE_API_KEY` (AI Studio) + `PARALLEL_API_KEY`. Real keys
  exist in the local `.env` — never commit it.

## Status: done / verified

- End-to-end room build works and output quality is strong (verified with a
  1962 Memphis treatment — cited findings on Stax-era studios, period props,
  routes, police). ~Search cost is trivial (~$0.005/search advanced).
- `scripts/try_search.py` smoke test passes.
- Web app works: treatment → live SSE timeline (shows each researcher's
  search objectives + counter) → tabbed results (Bible/Profile/Plan).
- **Adversarial review done** (`docs/adversarial-review-2026-08-06.md`, by a
  third Claude instance) and fixes applied: H1 XSS (DOMPurify + escaped
  fallback), H2-cheap (data/instruction delimiters in researcher+synthesis
  prompts; "only cite URLs from findings"), M1+part-H3 (per-run budget),
  M2 (task strong-ref), M3 (config.py), M5 (fail-fast env validation),
  L1 (planner premise), plus 8,000-char treatment cap. Review's L2 was a
  false alarm (README hackathon name is correct).

## Standing items — 2026-08-11

**Supersedes the Aug 6 list below**, which is kept as history. Items 2, 3 and 4
of that list are done: Cloud Run is deployed (revision `star-00017-ssr`),
Firestore persistence ships in `star/store.py`, and Pipeline B — Script Check —
is built and has since been through a seven-wave UI campaign. Item 5, the
markdown/zip export, has no endpoint and is still open. Item 7's first half is
done: model IDs are pinned in `star/config.py` with env overrides, not floating
on `-latest`.

**Where the argument now stands.** The naysayer's objections are about **reach
and lifecycle**, no longer about trust. That distinction is the whole point: a
trust problem could not have been shipped out of later, and it was the one that
had to be solved first. What is left is reachability and what happens to a room
after it exists — both of which can be built at any time.

Carried forward as roadmap, not blockers:

1. **`get_room` returns the whole room and takes no shape argument.** The
   biggest remaining agent-door defect. Measured 2026-08-11 against the two
   stored rooms: **31,047 and 29,536 tokens** per call (124,186 and 118,142
   characters). The tool's `inputSchema` accepts `run_id` and nothing else, so
   an agent asking what is in a room has no way to ask for less.

   The breakdown says what to build. On the larger room, **72.3% of the payload
   is raw source `excerpt` text** and **4.4% is the research facts themselves**;
   27 findings carry 89,735 characters of excerpt between them. Dropping
   excerpts alone takes the call to **8,613 tokens**; the research bible on its
   own is **652**. So a `shape` argument — `bible` / `plan` / `findings` /
   `full` — is a 97% reduction at the small end and a 72% one even at the
   permissive end.

   Note the overlap with the glow campaign: `web/excerpt.js` already reduces
   these same excerpts to a median 244 characters for the UI, because they
   arrive as raw scraped markdown. **The agent door sends them raw.** The
   reducer exists; nothing server-side calls it.

2. **No delete over MCP.** The door exposes exactly four tools — `list_rooms`,
   `get_room`, `build_room`, `check_scene` (`star/mcp/tools.py:227`). An agent
   can create rooms and never remove one. Lifecycle, and the naysayer is right
   about it.

3. **Error rooms charge budget and explain nothing.** A failed build still
   spends against the cap, and what comes back does not tell the caller what it
   spent or why it stopped. Builder's observation, not measured here.

4. **Two old damaged bibles still report `complete`.** Rooms that predate the
   bible fixes carry truncated bibles while their status says the build
   finished. Status is describing the run, not the artefact, and for these two
   those diverged. Builder's observation, not measured here — worth checking
   whether it is those two rooms only or a class.

5. **Adoption — `ask_room` first.** The door has no question-shaped tool. An
   agent can read a room or build one, but cannot ask it anything, so the
   cheapest possible adoption path does not exist. Build this before the other
   adoption items.

## Status: not done — in priority order (from 2026-08-06, superseded)

1. **Verify repo is public + MIT badge in About; push everything** including
   `docs/` (review + this handoff). At handoff, `server.py`, `web/`, review
   doc, and fixes may be unpushed.
2. **Cloud Run deploy**: Dockerfile, plus the deferred H3 guards the moment
   it's public — per-IP rate limit on `POST /api/rooms`, global daily run
   cap (kill switch), strip error detail from client responses (`server.py`
   `_execute` except-block leaks exception text by design for dev).
3. **Firestore persistence** (runs are in-memory only; also adds a second
   GCP service used at runtime — good for judges).
4. **Pipeline B — Script Check** (the demo's emotional peak): ClaimExtractor
   → Verifier (check room citations first, then fresh `parallel_search`
   turbo) → Annotator (CONFIRMED/ANACHRONISM/UNVERIFIABLE + sources).
   Models for it already exist (`Claim`, `Verdict` in `star/models.py`).
   Build the **H2 real fix** here: server already sees every search; collect
   returned URLs per run and flag any bible/report citation not in that set
   ("check the receipts").
5. **Export**: research bible as markdown bundle in writer-studio-template
   folder layout (zip download).
6. **Demo video** (≤3 min): hook → live room build (SSE timeline) → script
   check catching a planted anachronism → architecture slide → export.
   Fictional treatment; no real brands/logos on screen.
7. Before demo week: pin versioned Gemini model IDs via env vars
   (`-latest` floats), and pipeline-test one forced researcher failure (M4:
   unverified what `{findings_*}` resolves to if a parallel branch dies).

## Gotchas the next session should know

- ADK dev-UI shows a scary "System Instruction Performance Analysis /
  cache miss" dialog — it's expected (each sub-agent has its own
  instruction, with state injected). Ignore.
- `researchers.py` deliberately mixes f-string fragments with ADK `{state}`
  template braces — do not "clean up" into one f-string; it breaks silently.
- `output_schema` agents (intake, planner) cannot have tools in ADK.
- Under ParallelAgent, the four researchers share session state, so the
  budget counter can theoretically lose an increment race — cap is
  per-run but approximate at the margins. Known, accepted.
- Deleting files on the user's machine isn't possible via the Cowork device
  bridge; `.venv/`, `star.egg-info/`, `research_dept/.adk/session.db` live
  in the tree — ensure `.gitignore` keeps them out (venv is covered; add
  `*.egg-info/` and `research_dept/.adk/` if not).
- $100 GCP credit form (due Aug 31) was submitted; Parallel account created
  and funded/working.

## Working style that's been effective

Estevan drives terminal + deploys + recordings; Claude writes code and
commits it to the folder. He records screen captures of good runs as they
happen for the demo video. Bring tracebacks into chat verbatim; fix against
real errors. Momentum is high — day one delivered what the plan scheduled
for week two.
