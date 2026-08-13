# STAR — Story & Treatment Agentic Research

**Every studio has a research department. Now every writer has one, and so does every agent they run.**

STAR is a multi-agent research department for screenwriters, built with **Google ADK
(`google-adk`)** and **Gemini** on Google Cloud, using **Parallel's Search API** (via the
official **`parallel-web`** SDK) for live web research at runtime.

Paste a treatment and STAR builds a research room: setting and atmosphere, objects and
props, logistics, forces and conflicts. Every finding carries the sources it came from,
with the domain, the retrieval date, and the search's own excerpt. Paste a scene and STAR
checks the claims it makes about the world against that room's files first, then against a
fresh search, and hands the scene back marked in place.

Nothing in this app says a source was "verified." It says what was actually checked, and
what it could not settle.

Built for **Agentic Cinema: The Blockbuster Hackathon** (Parallel track).

## What it does

**Pipeline A — Build the Room.** A treatment becomes a story profile, a research plan, four
categories of researched findings, and a synthesised research bible. The four researchers
run in parallel and the browser watches them work over SSE.

**Pipeline B — Script Check.** A scene becomes a list of claims about the world, each
quoted exactly from the page, each carrying a verdict of `confirmed`, `anachronism`, or
`unverifiable`, the sources behind it, and **whether the room's own files or a fresh search
answered**. The scene comes back marked in place with a citation rail.

**The agent door.** The same department over MCP, so an agent can build a room and check a
scene without a browser, ask an existing room a question, or delete one. OAuth 2.1 with
dynamic client registration, or a per-user bearer token, and one shared budget with the
browser.

## The thing this is actually built around

A model authors the verdict, because a verdict is a judgment. It never authors a title, an
excerpt, or a claim about where something came from. Those are computed on the server from
a ledger of what search actually returned:

- Every citation is hydrated from that ledger. A URL a model cites that appears in no search
  result is stamped **UNSOURCED** and left on screen rather than quietly dropped.
- A `confirmed` or `anachronism` whose every cited source fails to resolve is **downgraded**
  to `unverifiable`, because a stamp with nothing behind it is the overclaim the whole design
  exists to refuse.
- "The room answered this, a fresh search answered that" is decided by which of two ledgers
  holds the URL, never by asking the model what it did.
- Running out of search budget is reported as *budget*, never as *not found*.

## Architecture

Deterministic multi-step pipelines built as ADK workflow agents, not a free-roaming chat
loop.

```text
Pipeline A · Build the Room  (SequentialAgent)
  intake        treatment → StoryProfile                  [Gemini, schema'd]
  planner       StoryProfile → ResearchPlan               [Gemini, schema'd]
  researchers   ParallelAgent: 4 categories, each calling
                the Parallel Search API                   [Gemini + parallel-web]
  synthesis     excerpts → cited research bible           [Gemini]
  findings.py   parse + hydrate against the run's ledger  [pure Python]

Pipeline B · Script Check  (SequentialAgent)
  claim_extractor  scene → ClaimSet, exact quotations     [Gemini, schema'd, no tools]
  verifier         claims + the room's files → verdicts   [Gemini + parallel-web]
  verdicts.py      hydrate against room ledger, then run
                   ledger; downgrade; stamp UNSOURCED     [pure Python]

The agent door
  star/mcp/     Streamable HTTP, hand-written against the transport spec.
                free:   list_rooms · get_room · ask_room · defend_claim
                        delete_room
                spends: build_room · check_scene · research_question
```

Both doors call the **same** function objects for admission and for running a build, so
"one budget, one ceiling, one kill switch" is mechanical rather than asserted.

## Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 |
| Agents | `google-adk`, `google-genai` — Gemini only, no other provider at runtime |
| Search | `parallel-web` — called at runtime by both pipelines |
| Web | `fastapi`, `uvicorn` |
| Identity | `firebase-admin` server-side; raw Identity Toolkit REST in the browser |
| Persistence | `google-cloud-firestore` via Application Default Credentials |
| Frontend | Native ES modules and plain CSS. No build step, no bundler, no CDN request |
| MCP | Hand-written. No MCP SDK dependency |

Every version is pinned exactly. A Cloud Build runs a fresh install and would otherwise
take whatever shipped that morning.

## Quickstart

```bash
# 1. Environment (Python 3.12)
python -m venv .venv
.venv\Scripts\activate            # Windows; source .venv/bin/activate elsewhere
pip install -e .

# 2. Configuration
copy .env.example .env            # cp on mac/linux, then fill it in

# 3. Smoke-test the Parallel Search integration
python scripts/try_search.py

# 4. Run the app
uvicorn star.server:app --reload   # http://127.0.0.1:8000

# 5. Or run the pipeline in the ADK dev UI
adk web                            # pick "research_dept"
```

Firestore reads and writes use Application Default Credentials, so `gcloud auth
application-default login` once against the project in `.env`.

### Tests

```bash
python -m pytest -q                        # Python + the Node suites under tests/js/
ruff check star tests scripts harness
```

The browser modules are tested through Node: `tests/test_js_auth.py` globs `tests/js/*.mjs`
and shells out, and it asserts the glob is not silently empty.

## Environment

Values live in `.env`, which is gitignored. `.env.example` documents each one.

**Required.** The app refuses to boot without these, because each fails closed but silently:

| Variable | What it is |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini, via Google AI Studio |
| `PARALLEL_API_KEY` | Parallel Search API |
| `GOOGLE_CLOUD_PROJECT` / `FIREBASE_PROJECT_ID` | The project Firestore and Auth live in |
| `FIREBASE_API_KEY` | Public web key. Identifies the project to the browser; not a secret |

**Optional.** All have working defaults:

| Variable | What it changes |
| --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` | Enables Google account linking. Absent, linking reads as unavailable and every other path works |
| `STAR_MAX_SEARCHES_PER_BUILD` | Search ceiling for one room build |
| `STAR_MAX_SCENE_CHARS`, `STAR_MAX_SEARCHES_PER_CHECK`, `STAR_CHECK_TIMEOUT_SECONDS` | Script Check limits |
| `STAR_MCP_ALLOWED_ORIGINS` | Origins the MCP door accepts |
| `STAR_FAST_MODEL`, `STAR_SMART_MODEL` | Pinned Gemini model ids |

No secret is ever served to the browser. `/config.js` carries the public Firebase key and
the public OAuth client id, and a test asserts the exact set of exports so an added key
fails rather than ships.

## The MCP server

`POST /mcp`, Streamable HTTP, on the same origin as the app. Authenticate with a per-user
token issued from **Your card** in the web app:

```http
Authorization: Bearer star_<token_id>.<secret>
```

Tokens are stored as sha256, shown once at issue, never recoverable, and revocable. A token
can only be issued to an account with a linked identity, because an anonymous account's only
proof of ownership is a `localStorage` entry.

The door serves `list_rooms`, `get_room`, `ask_room`, `defend_claim`, `build_room`,
`check_scene`, `delete_room` and `research_question`. `get_room` **is** `build_room`'s poll.
`research_question` is what `ask_room` points at when a room does not answer: it researches
that one question and files the result into the room the writer already has, rather than
charging them a whole second room to learn one thing. `defend_claim` takes one filed fact
back out with its sources, their excerpts and the date they were retrieved — the shape a
writer hands to whoever is challenging the detail, and it refuses to find a fact by
approximation rather than put real sources behind a claim the room never made. Every
description is written for a reader who cannot see a screen, and every refusal names what
failed and what to do next.

## The draft, rather than the scene

`check_scene` takes one scene, which is right for one scene and wrong for a screenplay. A
writer with a finished draft was finding each scene in their editor, selecting it, pasting,
waiting, and going back for the next — fifty times.

**Paste the whole thing.** `web/fountain.js` splits a Fountain draft into its scenes in the
browser and lists them; pressing one loads it and spends nothing. Fountain because it is what
screenwriters already have on disk (Highland, Slugline, Beat and WriterDuet all export it).
The parser requires a blank line before a scene heading as well as after, which the 1.1
reference calls optional — without it, the last line of a paragraph starting "EXT." splits a
scene in half and each half is checked without the context that made it make sense.

**Or sweep it.** One request reads every scene, collects what the draft claims about the
world, collapses that to the distinct set, and checks it against the room in a single pass.
The arithmetic is the argument: extraction is a schema'd model call with no tools, so reading
a whole feature costs model time and no searches, and only the verification is paid for.
Scene by scene, 24 scenes is 24 search budgets — up to 192 searches — and 24 slots of an
hourly window that admits five. A sweep is one of each.

Measured over a real 27-page special: 24 scenes, 85 claims raised, 65 distinct, 4 live
searches. Deduplication accounts for about a fifth of that; the budget structure accounts for
the rest.

Every claim comes back naming the scenes that made it — the answer no number of single-scene
checks adds up to, because an object that is fine in Liverpool in 1958 and wrong in Hamburg in
1960 is wrong in neither scene alone.

## What leaves the building

A sweep is filed, so a reload does not discard a draft's worth of answers and the searches
that bought them. From a filed sweep:

- **`/report.html`** — one printable page, anachronisms first, every verdict above its
  sources. The browser's own print dialogue is the export; the screen layout *is* the sheet.
- **`.csv`** — one row per claim per source, so a spreadsheet can filter on a domain. Cells
  opening `=`, `+`, `-`, `@`, tab or carriage return are prefixed, because every cell here is
  a writer's own line or a page off the open web and both land in a program that will run
  them.
- **an import** — a writer annotates that CSV and brings it back. It carries a note and a
  dismissal and **nothing else**: a verdict, a source and an excerpt are the department's,
  hydrated out of a ledger, and a row editing one has that column ignored and named in the
  report. A room must never read as better-sourced than its research made it.

## Rooms that stack

A story spans eras, and Liverpool in 1958 and Hamburg in 1960 want two rooms. `continues`
links them, and a check or a sweep against the later room reads **the whole chain** — nearest
first, each room's findings under its own name, so an answer can say which room held the fact.

Nothing is re-planned and no room is rebuilt. That is deliberate: re-planning against a
revised treatment risks a planner shown prior questions suppressing rather than narrowing, and
failing quietly — a room that comes back looking fine and thinner than it should be. Stacking
cannot fail that way. A chain that is not working spends searches it did not need; a
suppressed plan loses facts nobody knows are missing.

An unlinked room reads exactly as it did before any of this existed.

That list is pinned by a test against `star/mcp/tools.py`, and it names them rather than
counting them. The sentence here was wrong for a day after `ask_room` and `delete_room`
shipped, because it advertised only the ones that came before — the same defect
`web/consent.js` shipped when it promised "four calls" on the day a fifth tool landed. A
number in prose is a second source of truth, and in a file that cannot compute one, a test is
the only thing that keeps it honest.

**Authorization, measured against the live service on 2026-08-12.** OAuth 2.1 discovery
works. `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`
both answer 200, the authorization server advertises a `registration_endpoint` so dynamic
client registration needs no pre-provisioned client, PKCE is `S256`, and the three scopes are
`rooms:read`, `rooms:write` and `rooms:delete`. An unauthenticated call returns 401 with
`WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"`.

A client that speaks the discovery flow connects with no manual configuration:

```sh
claude mcp add --transport http star https://star.626labs.dev/mcp
```

A client configurable with a static bearer header also works, using a token issued from
**Your card**.

**What still 404s**, because a limitation stated is worth more than one implied:
`/.well-known/openid-configuration` and the path-suffixed
`/.well-known/oauth-protected-resource/mcp` variant. A client that requires either specific
path rather than the two above will not discover this server.

The date on that paragraph is load-bearing. The text it replaced said "the shape of it
measured rather than assumed" and then described a server that answered 404 on every
discovery path — true when written, false by the time a judge read it, and claiming rigor
while it was wrong. An undated measurement is how that happens.

### Connecting a desktop client

For any MCP client that speaks stdio rather than HTTP, bridge it:

```jsonc
{
  "mcpServers": {
    "star": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote@latest",
        "https://star.626labs.dev/mcp",
        "--header", "Authorization: Bearer star_<token_id>.<secret>"
      ]
    }
  }
}
```

Issue the token from **Your card** in the web app. It requires a linked account, and it is
shown exactly once.

For a client that speaks HTTP directly, no bridge is needed:

```bash
claude mcp add --transport http star https://star.626labs.dev/mcp \
  --header "Authorization: Bearer star_<token_id>.<secret>"
```

**One number worth knowing before wiring an agent to this.** `get_room` on a complete room
returns about 152,000 bytes, roughly 37,000 tokens — the bible is 16k of it and the four
drawers are 127k, because citation excerpts are real slabs of the pages search returned. Fine
for a single read. Do not poll `get_room` in a loop after a build reaches a terminal status.

## The persona harness

`harness/` drives Gemini-backed personas against the MCP surface and records what each one
did, so "synthetic user testing" is an artifact in the repo rather than a claim in a
writeup. The client is `urllib.request` from the standard library: no new dependency, and
nothing third-party in the frame. Transcripts live in `harness/runs/`.

The bar it measures: **every failure a persona could not diagnose from the response alone is
either fixed or written down with the reason it stands.**

`harness/` is not deployed. It is excluded from both the image and the source upload.

## Deployment

One Cloud Run service, one instance, serving the API, the SSE stream, the static app, and
the MCP endpoint from the same process.

```bash
GOOGLE_OAUTH_CLIENT_ID=... FIREBASE_API_KEY=... bash scripts/deploy.sh
```

Live at **[star.626labs.dev](https://star.626labs.dev)**, a Cloud Run domain mapping onto the same service.
Cloud Run additionally answers on two hostnames of its own, a project-number form and a
hash form, and both keep serving whether or not anyone means them to. That matters for one
reason: `web/auth.js` sends `location.origin + "/"` as its OAuth `redirect_uri`, so **every**
origin the service answers on has to be registered on the OAuth client, or account linking
fails for exactly the readers who arrived on the unregistered one.

`--max-instances=1 --min-instances=1 --no-cpu-throttling` are load-bearing rather than
tuning. The run registry and both abuse guards are in-memory module state; anything that
scales past one instance has to move all three to a shared store in the same change.
`scripts/deploy.sh` explains each flag and what breaks without it.

**No Firestore ruleset is deployed, and that is deliberate.** With none deployed Firestore
denies all client access, so the server holding Application Default Credentials is the only
path to the data and every read is scoped by uid. One boundary rather than two. Deploying
permissive test-mode rules would silently void it.

## Design

The interface is **THE MORGUE** — the newspaper clipping library behind the newsroom, where
nothing gets filed without a stamp saying who found it, where, and when. The metaphor was
chosen on one test: it *describes* the system rather than dressing it. A ledger entry is a
clipping file, an unsourced URL is an unstamped clip, a category is a subject drawer.

Full direction, palette, type stack, and the behavioural obligations that bind every
surface: [`docs/design/DIRECTION.md`](docs/design/DIRECTION.md).

## Runtime services (hackathon compliance)

- `google-adk` / `google-genai` — imported and called at runtime: `star/agents/*.py`
- `parallel-web` (Parallel **Search API**) — imported and called at runtime by **both**
  pipelines: `star/tools/parallel_search.py`
- All AI at runtime is Gemini on Google Cloud. No other AI model, API, or framework.

## License

MIT — see [LICENSE](LICENSE).
