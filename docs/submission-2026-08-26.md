# Submission copy — YouTube and Devpost

Everything below is paste-ready. Replace `YOUTUBE_URL` after the upload.

---

## YouTube

**Title**
STAR — a research department for screenwriters, built on Google ADK and Parallel

**Description**
Every studio has a research department. A writer working alone doesn't.

STAR builds one: a treatment goes in, four research agents run in parallel on Google's Agent Development Kit with Gemini on Vertex AI, each sending live queries to the Parallel Search API, and a research room comes back — setting, objects and props, logistics, forces and conflicts — where every fact is filed with the page it came from: the domain, the day it was retrieved, and the page's own excerpt. Paste a whole draft and it checks every claim the script makes about the world, against the room's files first and a fresh search only for what those can't answer, then hands the scene back marked in place.

Nothing in it says "verified." It says what was checked, and what it could not settle.

Try it: https://star.626labs.dev
Source (MIT): https://github.com/estevanhernandez-stack-ed/STAR

Built for Agentic Cinema: The Blockbuster Hackathon, Parallel track.

0:00 The problem
0:20 Building a room — four researchers, live searches, real time
0:50 The receipt
1:10 Sweeping a 31-scene draft in one request
1:35 The catch
2:36 The same department over MCP
2:50 Close

Built with Google ADK · Gemini on Vertex AI · Cloud Run · Firestore · Firebase Auth · Parallel Search API · FastAPI

**Video privacy:** Public (the hackathon requires a public YouTube link; Unlisted fails the rule).
**Category:** Science & Technology
**Keywords:** STAR, screenwriting, research, Google ADK, Gemini, Vertex AI, Cloud Run, Parallel Search API, MCP, AI agents, Agentic Cinema, hackathon, fact-checking, anachronism
**Made for kids:** No
**Language:** English

---

## Devpost

**Project name**
STAR — Story & Treatment Agentic Research

**Tagline** (under 200 characters)
A research department for screenwriters. Four agents on Google ADK research your world through Parallel's live search and file every fact with the page it came from.

**Try it out**
- https://star.626labs.dev
- https://github.com/estevanhernandez-stack-ed/STAR

**Video**
YOUTUBE_URL

**Built with** (tags)
python · google-adk · gemini · vertex-ai · google-cloud-run · firestore · firebase-auth · secret-manager · parallel-search-api · parallel-web · fastapi · mcp · javascript

---

### About the project

#### Inspiration

Every studio has a research department. A writer working alone gets one chance to notice that the club in their scene opened a year after the scene is set. I write a Doctor Who story set in Liverpool in 1958 and Hamburg in 1960, and I kept catching my own anachronisms weeks late — the Casbah Coffee Club opened in August 1959; a line about "turning it up to eleven" is from a 1984 film. Nobody holds those dates in their head. A department does.

I wanted the department, and I wanted it honest: not a chatbot that says "verified," but a desk that files what it actually found and shows the receipt.

#### What it does

**Build the Room.** Paste a treatment. An intake agent extracts a story profile; a planner turns it into a research plan; four researcher agents run in parallel — setting and atmosphere, objects and props, logistics, forces and conflicts — each issuing its own queries to the Parallel Search API. The browser watches them work over SSE: the actual query strings, the searches, the clock. A synthesis agent writes a research bible. Every finding carries its sources with the domain, the retrieval date, and the page's own excerpt.

**Script Check.** Paste a scene, or a whole Fountain draft (31 scenes, one request). A claim extractor pulls every claim the script makes about the world as an exact quotation; a verifier checks each against the room's own files first, and searches Parallel only for what those files can't answer. Each claim comes back `confirmed`, `anachronism`, or `unverifiable`, with its sources — and the scene renders marked in place, with a citation rail that follows the selected line.

**The agent door.** The same department over MCP — fifteen tools, hand-written against the Streamable HTTP transport, OAuth 2.1 with dynamic client registration — so any desktop agent can build a room, check a scene, or ask the department to defend a fact. Free reads never rate-limit; the tools that spend money say so before they spend, and browser and agent share one budget.

#### How we built it

- **Google ADK** workflow agents, not a free-roaming chat loop: a `SequentialAgent` for intake → planner → a `ParallelAgent` of four researchers → synthesis, and a second pipeline for claim extraction → verification. Deterministic steps, schema'd outputs.
- **Gemini on Vertex AI** (`gemini-3.6-flash`, pinned), authenticated as the Cloud Run runtime — no API key anywhere in the app.
- **Parallel Search API** through the official `parallel-web` SDK, called at runtime by both pipelines. Every search result is recorded in a server-side ledger before any model writes a word.
- **Cloud Run** (single instance, so in-memory run state and the SSE stream stay coherent), **Firestore** via Application Default Credentials for rooms, sweeps and filed checks, **Firebase Auth** (anonymous by default, Google linking as an upgrade), **Secret Manager** for the one secret.
- **FastAPI** + native ES modules, zero third-party browser requests — fonts and libraries are vendored so a CDN hiccup can't break a demo.

#### The thing it's actually built around

A model authors the verdict, because a verdict is a judgment. It never authors a title, an excerpt, or a claim about where something came from. Those are computed on the server from the ledger of what search actually returned:

- A URL a model cites that appears in no search result is stamped **UNSOURCED** and left on screen rather than quietly dropped.
- A `confirmed` or `anachronism` whose every cited source fails to resolve is **downgraded** to `unverifiable` — a stamp with nothing behind it is the overclaim the design exists to refuse.
- "The room answered this, a fresh search answered that" is decided by which ledger holds the URL, never by asking the model what it did.
- Running out of search budget is reported as *budget*, never as *not found*.

#### Challenges we ran into

- **Citation honesty is a measurement problem, not a prompt problem.** On an early sweep, 21 of 42 confirmed rows cited a page that repeated no word of the claim. Fixing it meant measuring — a `shares_claim_wording` check on every citation — and then showing the result on screen as a caveat rather than hiding it. It's at 7 of 34 now, and every one is labelled.
- **A false positive that would have been filmed.** One sweep flagged "He was seventeen" as an anachronism, reading "he" as George Harrison. Both scenes meant John Lennon, who was seventeen in 1958. The draft was right and the department was wrong. The fix was a better verifier; the lesson was that the product's job is to show a reader what to look at, not to rule.
- **The five-per-hour ceiling is the real hazard on a public URL.** Per-IP rate limits, a global daily cap, and a kill switch landed the day the app went public, and the order of the checks matters: the free in-memory check first, the cap increment last. Getting that backwards once burned a day's budget in seconds.
- **Gemini on Vertex 404s in `us-central1`.** `gemini-3.6-flash` is published to the global endpoint. `GOOGLE_CLOUD_LOCATION=global` is load-bearing and now documented in capitals.
- **MCP inside the same process.** A second Cloud Run service would double every budget and split the SSE stream from the build that owns it. The MCP router is hand-written against the transport spec, mounted in the same FastAPI app, sharing the same function objects as the browser — so "one budget, one ceiling" is mechanical rather than asserted.

#### Accomplishments that we're proud of

- Anti-fabrication that extends to the bible: 31 of 31 source lines carried the ledger's real title, and every URL the bible printed was one the search API actually returned.
- A whole 31-scene draft (134,000 characters) swept in one request in about two and a half minutes, with 75 distinct claims checked against a room that cost 17 searches to build.
- The catch in the demo is real and unrehearsed: the Casbah, Mona Best's coal cellar, the espresso machine, the spider and the rainbow — five details in one scene, all dated to August 1959, all flagged with the source that dates them, and the department declining to say the story is wrong.
- Fifteen MCP tools whose error strings are the product: every refusal an agent can hit names what failed and what to do next.

#### What we learned

- Two green test suites either side of a wire prove nothing about the wire. Open the artifact. Every expensive mistake on this project was a surface that said something true and unusable.
- The honest thing and the demoable thing are the same thing. "Nothing here says verified" turned out to be the strongest line in the video.
- Budgets and ceilings are features, not plumbing. A desk that says "budget" instead of "not found" is telling the truth about itself.

#### What's next

- Requisitions: a writer asks the room one question and the department sends one researcher to the field (`research_question` exists at the agent door today).
- A room that continues another, so a story spanning eras reads as one chain.
- Export the bible in a writer's-room folder layout.
- Per-writer voices for the bible: the department's prose in the register of the draft it serves.

---

### Submission checklist (from the rules)

- [ ] Video public on YouTube, English, under 3:00, no third-party logos on screen
- [ ] Repo public with the MIT license visible in GitHub's About sidebar (`gh repo edit --visibility public`; run the credential sweep first — an ignored `.mcp.json` sits in the root)
- [ ] Hosted URL live: https://star.626labs.dev
- [ ] Devpost form: name, tagline, video, links, built-with tags, the About sections above
