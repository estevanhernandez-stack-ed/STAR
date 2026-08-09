# STAR GUI — persistent workspace design

**Date:** 2026-08-09
**Status:** approved, pending implementation plan
**Supersedes:** the three-panel flow in `web/` (intake → single-column timeline → three tabs)

## Why this exists

The Agentic Cinema Stage Two rubric scores implementation, design, impact, and
idea with equal weight. Design is a quarter of the score, and the current
frontend gives away its strongest asset: four researchers genuinely run at once
under `ParallelAgent`, and the UI renders that as one flat chronological list.
The architecture's most interesting property is invisible.

This design makes a room the persistent thing a writer returns to, makes the
parallelism literal on screen, and makes citations first-class objects instead
of markdown links dissolved into a prose blob.

## What is kept

The current app is not being thrown away. Three things carry forward unchanged:

- **The department metaphor in the microcopy.** "Hand your treatment to the
  department", "filed their work", and the friendly agent names in
  `server.py::_FRIENDLY` are real design work. They stay.
- **The palette and type.** Dark ground, gold accent, Georgia throughout. It
  reads editorial rather than dashboard, which suits the product.
- **The research bible as a full-width reading document.** It is the artifact a
  writer prints. It keeps its markdown treatment.

## Decisions

| Decision | Choice | Rejected |
| --- | --- | --- |
| Scope | Re-conceive the surface as a persistent workspace | Polish pass; live-run rework only |
| Identity | Firebase Anonymous Auth | Google Sign-In; browser-local UUID |
| Script Check presentation | Inline annotated scene | Two-pane cards; verdict report |
| Room reading view | Four-quadrant, one component in two states | Sticky citation rail; category tabs |
| Structured findings | **A** — strict researcher format parsed server-side | **B** (4 parallel structurer agents) held as fallback; **C** (single registrar) rejected |

Choosing a persistent workspace makes **Firestore a blocker rather than a
nice-to-have**, and it moves ahead of the Cloud Run deploy in the task order. A
persistent workspace with nowhere to persist is the current app with a sidebar.

Three GCP services now run at runtime: Gemini, Firestore, and Firebase Auth.

## The constraint that shaped the backend

`models.py` defines `ResearchDoc`, `Finding`, and `Citation`. **The pipeline
uses none of them.** `make_researcher()` sets `output_key` with no
`output_schema`, so `findings_<category>` are prose strings, and synthesis reads
those blobs to write the bible. Structured citations exist nowhere in the
running system.

They cannot be produced the obvious way. ADK forbids tools on schema'd agents,
and the researchers require `parallel_search`. That door is closed, which is why
structure has to be recovered after the fact rather than declared up front.

## Architecture

### The source ledger

`parallel_search` returns `{title, url, excerpts}` per result, and ADK exposes
function *responses* on the event stream alongside calls. The server records
every result into a per-run ledger:

```text
url -> { title, excerpts, found_by_agent }
```

The ledger is the keystone. Researchers only ever need to write down a URL they
just saw, which is the one thing a model reproduces reliably. Titles and
excerpts are never trusted to the model; they are hydrated from the ledger.

The H2 "check the receipts" fix falls out of this for free: a cited URL absent
from the ledger came from nowhere.

`Event.get_function_responses()` is confirmed present in ADK 2.6.2 and returns
the parts carrying tool output. **Confirmed against the live API on 2026-08-09:**
the envelope is a bare `dict` with a single top-level key `result`, whose value
is exactly the `list[dict]` `parallel_search` returns. `unwrap_results` handled
it with no modification. Pinned by `tests/test_response_shape.py` using real
recorded data, so an ADK upgrade that changes the wrapping fails loudly instead
of silently emptying every ledger.

**Parse-rate baseline, same date, one full room build (1962 Memphis treatment):**

| Category | parse_rate | findings | citations | unverified |
| --- | --- | --- | --- | --- |
| setting | 1.0 | 9 | 17 | 0 |
| objects_props | 1.0 | 8 | 16 | 0 |
| logistics | 1.0 | 6 | 9 | 0 |
| forces_conflicts | 1.0 | 5 | 12 | 0 |

15 searches against a budget of 30, 109 distinct sources, 17,141-character
bible. Every category parsed perfectly and **zero citations failed the ledger
check**, meaning no researcher cited a URL it had not actually seen. Approach A
holds; the fallback to B (four schema'd structurer agents) is not needed. The
70% trigger stays documented in case a later prompt change regresses it.

### Flow

```text
treatment
   |  POST /api/rooms
intake -> planner -> [4 researchers in parallel] -> synthesis
                          |  tool responses
                     SOURCE LEDGER  (url -> title, excerpts, agent)
                          |
   findings prose --parse--> ResearchDoc --hydrate--> Findings + Citations
                                                └--> uncited URLs flagged
                          |
                      Firestore  /users/{uid}/rooms/{roomId}
```

### New modules

Each has one job, and `server.py` returns to orchestration only.

| Module | Responsibility | I/O |
| --- | --- | --- |
| `star/ledger.py` | Accumulate search results per run | none |
| `star/findings.py` | `(prose, ledger) -> ResearchDoc` | none |
| `star/store.py` | All Firestore reads and writes | Firestore |
| `star/auth.py` | Verify Firebase ID token, return uid | Firebase |

`ledger.py` and `findings.py` are pure. That is deliberate: they are the two
pieces most likely to drift, and purity makes them cheap to test hard.

### Researcher output format

The researcher instruction is tightened to emit one finding per line:

```text
- <fact stated plainly> :: <url>, <url>
```

Everything else about the researchers is unchanged, including the data /
instruction delimiters from the adversarial review and the standing rule to
report uncertainty rather than invent facts.

### Firestore schema

```text
/users/{uid}/rooms/{roomId}
    title, logline, era, genre, locations[], key_entities[]
    research_plan
    research_bible          (markdown)
    search_count
    status                  running | complete | error | interrupted
    createdAt
    categories: {
      setting:          { findings[], questions[], parse_rate, unverified_count },
      objects_props:    { ... },
      logistics:        { ... },
      forces_conflicts: { ... }
    }
    /scenes/{sceneId}
        text, claims[]      (Claim with verdict, note, citations)
```

### Security boundary

The server owns all Firestore access; the browser talks only to STAR's own API
with a Firebase ID token as a bearer credential. The idiomatic Firebase
alternative — client SDK reading Firestore under security rules — gives two
boundaries to get right instead of one, three weeks from a deadline. One
boundary, one owner.

### Zero third-party browser requests

Firebase Auth, `marked`, and `DOMPurify` are vendored into `web/vendor/`.
Nothing loads from a CDN. `index.html` currently pulls `marked` and `DOMPurify`
from cdnjs, which means a cold Cloud Run instance or a bad edge node drops the
bible to its escaped-`<pre>` fallback — on camera, during a recorded demo. The
rule is absolute because the failure is silent and the demo is unrepeatable.

### SSE contract change

Events gain a `category` field mapped from the ADK author name, so the UI routes
each event to its quadrant without string-matching friendly labels. Events also
gain a monotonic `seq` so a reconnecting client can apply them idempotently —
the stream endpoint replays from cursor zero on every connect, which today would
duplicate timeline entries on reconnect.

## Interface

### Shell

A persistent left rail of projects and one main stage that changes state.

```text
+-----------+---------------------------------------------+
| * STAR    |  1962 Memphis                    [Room][Chk]|
|           |  1960-1962 · Crime drama                    |
| PROJECTS  |  ( Memphis )( Stax Studio )( McLemore Ave ) |
| • Memphis |                                             |
| • Noir 78 |              ( main stage )                 |
| • Untitled|                                             |
|           |                                             |
| + New room|                                             |
+-----------+---------------------------------------------+
```

**The story profile becomes the room's identity**, not a tab: title, era, and
genre as a header, locations and key entities as chips beneath.

**The research plan moves inside the quadrants.** Each category's questions live
in its own panel, so a panel tells a complete story — what we asked, what we
found. Two tabs die and the room gets more honest.

### CategoryPanel — one component, four states

`idle -> searching -> filed -> expanded`, plus a `failed` state. The 2×2 grid of
these is the whole room, in both the running and finished views.

```text
RUNNING                              FILED
+--------------+--------------+      +--------------+--------------+
| SETTING   ~  | PROPS     ~  |      | SETTING    v | PROPS      v |
| "Stax studio | "Fender      |      | 6 facts      | 4 facts      |
|  interior"   |  models '62" |      | 11 sources   | 7 sources    |
| . . .        | . .          |      | 3 questions  | 2 questions  |
+--------------+--------------+      +--------------+--------------+
| LOGISTICS v  | FORCES    ~  |      | LOGISTICS  v | FORCES     ! |
| filed        | "Memphis PD  |      | 5 facts      | 8 facts      |
| . . . .      |  vice, 1962" |      | 9 sources    | 14 sources   |
|              | . .          |      |              | 1 unverified |
+--------------+--------------+      +--------------+--------------+
```

Gold pulse means searching, green check means filed, each dot is one cited
search landing live, and `!` means at least one citation failed the ledger
check.

### Expanded reading view

The clicked panel takes the stage; the other three collapse to a rail.

```text
+---------------------------------------------------+
| <- SETTING         [Props][Logistics][Forces]     |
|---------------------------------------------------|
| Q: What did the Stax recording room look like?    |
|                                                   |
|  Stax operated out of the old Capitol Theatre;    |
|  the sloped theater floor was never leveled and   |
|  shaped the room's sound.                         |
|                                                   |
|  RECEIPTS  ( staxmuseum.org ) ( rollingstone.com )|
|            └ "...the floor still raked down       |
|               toward where the screen had been"   |
+---------------------------------------------------+
```

A receipt chip shows the domain, clicking drops the ledger excerpt inline, and
the title links out with `target=_blank rel=noopener noreferrer`.

### Script Check

A mode toggle in the room header, not a separate place — its value is being
checked *against this room*. Paste a scene, run it, and the scene returns marked
in place, with a citation rail that follows the selected mark.

Verdict colors: confirmed green, anachronism red, unverifiable dim.

### Visual language

Palette and type hold. What changes is that color acquires a job: gold means
working, green means filed, red means anachronism, dim means unverifiable.

### Frontend structure

No build step, native ES modules: `auth.js`, `api.js`, `room.js`, `panel.js`,
`scriptcheck.js`, `render.js`, with `web/vendor/` holding the three vendored
libraries. Below 900px the 2×2 stacks to one column and the expanded view goes
full-bleed.

## Failure handling

### Parse drift — the risk accepted with A

Unparseable lines are kept, never dropped. A panel renders structured findings
first, then any remainder as a "field notes" prose block. Worst case a quadrant
degrades to roughly what ships today.

**The fallback trigger is measured.** `findings.py` reports a parse rate per
category and the server logs it per run. **If parse rate sits below 70% across
five consecutive runs after one round of prompt tuning, build B** — four
parallel schema'd structurer agents, one per category, legal because they carry
no tools. Checkable on a date rather than arguable in September.

### Fabricated citations

A URL cited but absent from the ledger never renders as a receipt. The fact
carries an unverified mark and the panel shows the count. The H2 fix becomes
visible evidence that the department checks its own people.

### Dead researcher branch

If `findings_<category>` is missing or empty the quadrant enters `failed` and
says that researcher didn't file; synthesis proceeds on the survivors. This is
the open M4 question, and the panel state is what makes the answer legible when
it gets tested.

### Budget exhaustion

`parallel_search` already returns an error dict and instructs the researcher to
report unresearched questions. Today that vanishes into prose. The panel surfaces
it: budget reached, N questions unanswered.

### Scene annotation and XSS

The annotated scene is assembled with `document.createTextNode` and real span
elements. **Never** by building an HTML string from scene text. Inline
annotation interleaves model output with user text, which is exactly where the
H1 XSS fixed in the adversarial review would return through a different door.
DOMPurify guards the bible; DOM construction guards the scene.

### Anchor miss

When an extracted quote does not appear verbatim, normalize whitespace and case
and retry, then fall back to showing the claim in the rail as unanchored. A
verdict is never lost because it could not be placed.

### Auth failure

Anonymous sign-in failure degrades to an ephemeral session: the run works, a
banner says it will not be saved. The app does not die for want of an identity.

### Server death mid-run

The in-flight asyncio task does not survive a restart. Runs left `running` with
no active task are marked `interrupted` on next read rather than spinning
forever in the UI.

## Testing

| Target | Kind | Cost |
| --- | --- | --- |
| `findings.py` parse + hydrate | Unit, golden fixtures from real runs | none |
| `ledger.py` accumulation | Unit | none |
| Anchor matcher | Unit, paraphrase and whitespace cases | none |
| Uncited-URL detection | Unit | none |
| Full pipeline | Integration, stubbed runner replaying a recorded event stream | none |
| Forced researcher failure (M4) | Manual, once | one run |

Fixtures are captured from real runs and committed, so the parser is tested
against what Gemini actually writes rather than what it ought to write.
`pytest` is already a dev dependency; nothing new is required.

## Implementation order

This spec is larger than one implementation plan and decomposes into four
phases. Each is independently shippable and leaves the app working.

**Phase 1 — Foundation.** `ledger.py`, `findings.py`, the tightened researcher
format, and per-category findings exposed on `GET /api/rooms/{run_id}`. Pure
backend, fully unit-tested, no UI change. This is where parse rate gets measured
and therefore where the A-versus-B question actually gets answered, so it goes
first and alone.

**Phase 2 — Persistence.** `auth.py`, `store.py`, Firebase Anonymous Auth,
Firestore schema, room list and room read endpoints. Still no visual change
beyond a project rail.

**Phase 3 — The room.** Shell, sidebar, `CategoryPanel` in all five states, the
2×2 grid, expanded reading view with receipts, vendored libraries, SSE `category`
and `seq` fields, responsive collapse. This is the phase that earns the design
score.

**Phase 4 — Script Check UI.** Depends on Pipeline B existing; the pipeline
itself is tracked separately on the dashboard. This phase covers only the
annotated-scene surface, the anchor matcher, and the citation rail.

Phase 1 is the slice to plan first.

## Consequences

- Firestore moves ahead of Cloud Run in the task order.
- `models.py` types finally get used by the running pipeline.
- The H2 receipt check ships as a visible UI feature rather than a silent guard.
- The M4 unknown gains a defined UI state, so testing it produces a visible answer.
- Two tabs are removed; the story profile and research plan are absorbed into the
  room.
- The browser makes no third-party requests, removing a silent demo-day failure.
