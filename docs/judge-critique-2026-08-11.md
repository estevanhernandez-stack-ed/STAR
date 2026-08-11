# STAR — a judge's critique, written by the writer you built this for

Date: 2026-08-11. Method: I read the repo, read your own design research and adversarial docs, read the Devpost brief, and then used the live MCP server the way a hostile juror would — read the Lenin Shipyard room, ran a `check_scene` against it with planted errors, inspected the failed room, and built a fresh room from a contemporary Lagos treatment with a deliberately false historical premise buried in it. Everything below is grounded in what the tool actually did today, not in the pitch.

Two hats, as requested. The judge scores what you built. The naysayer screenwriter tells you why she still wouldn't open it twice.

---

## Part 1 — What survived contact with a skeptic

Credit first, because it's earned and because the critique lands harder when you know I saw the good parts.

I planted a Sony Walkman in a 1978 Gdańsk scene. The check caught it, dated it to July 1, 1979, cited a source that resolves, and stamped a second URL the model reached for as unsourced rather than hiding it. The provenance labels — this citation came from the room's files, that one from a fresh search — held up under inspection, and they are computed from ledgers, not asked of the model. That is the one architectural idea in this project that almost nothing else on the market does honestly, and it worked live.

The refusal copy is the best I have seen in a hackathon entry. I sent `build_room` a `title` argument it doesn't take and got back exactly what I sent wrong, what it takes instead, and what to call next. Your fumbler persona transcript shows an agent recovering from a wrong argument in one turn because the error told it how. Budget refusals name which ceiling refused you. This is craft, and judges who probe the MCP surface will notice.

The Lagos build surprised me. I gave it a contemporary, non-Western thriller — danfo driver, agbero levies, counterfeit malaria medication out of Idumota — half expecting the four-bucket taxonomy to produce generic tourism copy. Instead the plan asked about female danfo drivers specifically, about what legitimate versus counterfeit Coartem blister packs looked like in 2019, about NAFDAC field test kits and informant-protection limits. Thirty-six findings, 103 sources, a bible that reads like something a researcher would actually hand over. The instrument has range.

And the self-knowledge in this repo is unusual. Your ai-aversion research doc and your own adversarial critique already name most of the strategic problems. My job is to tell you which of those you've actually fixed, which still stand, and what I found that your own red team missed.

---

## Part 2 — What I found that your red team didn't

### The check confirms nouns and misses the world

This is the finding that matters most, so here is the full anatomy. My Gdańsk scene contained, by design, three different kinds of error and one kind of truth:

The truths were proper nouns and objects — Gate No. 2, the Falowiec, Kone cranes, moro camouflage. The check extracted ten claims, and nine of the ten were these. All confirmed, largely from the room's own files. But notice the circularity: I wrote the scene *from the room*. Confirming that a writer correctly copied the room's nouns back into a scene is a low-value pass that produces a high-value-looking score.

The planted errors it missed were the ones that live in verbs, not nouns. My scene had guards waving the night shift through Gate No. 2 "without a search" — and the room's own research plan contains a question specifically about gate search practices and security protocols. The claim that most directly contradicts the department's own files was never extracted, so it was never checked. My scene had the son arriving with a net bag of fresh oranges "bought without a queue" — in 1978 Poland, in a room whose own bible documents ration cards and queues outside Społem stores, citrus was a Christmas-miracle commodity. Not extracted. My scene had mimeographed pages smelling of spirit duplicator fluid — two different machines, a props error a Mad Men researcher would catch on page one. The check confirmed that spirit duplicator fluid *exists*.

So the scene came back **9 confirmed, 1 anachronism, 0 unverifiable** — a nearly clean bill of health for a scene I had salted with period errors. The extractor's prompt asks for prices, procedures, and behaviors, and it has a `behavior` claim type, but in practice it harvested proper nouns and technology and left every procedural assertion on the page. The danger is exactly the one your own research doc names from the BBC finding: citation presence functions as a trust signal independent of accuracy. A writer who sees nine green stamps trusts the whole page — including the parts that were never examined. Your verification is honest about what it checked. The *summary line* is not honest about what it didn't.

What it needs: either extraction recall on behavioral and procedural claims (test it with salted scenes exactly like mine — this should be a persona in the harness), or scope honesty in the output: "This check examined 10 claims about objects, places, and technology. It did not examine assertions about procedures, prices, or social conditions. 3 sentences in this scene made such assertions." The second is cheaper and more on-brand than the first, and you can ship both.

### The department never questions the treatment

I told STAR my Lagos climax happens during "the October 2019 closure of the Third Mainland Bridge for repairs." There was no October 2019 closure — the repair closure ran July 2020 to February 2021, with a short 2018 maintenance shutdown. STAR's researchers clearly brushed against this: the bible describes maintenance closures "between 2018 and 2020" and even the correct detour routes. But nothing in the room says to the writer: *your load-bearing premise is dated wrong, and your fix is to move the story nine months*. The department researched around the hole in my treatment without ever pointing at it.

A real research department's most valuable output is exactly this — The Crown's researchers surfacing "these other events maybe he hasn't thought of," Mad Men's researcher flagging what wouldn't fly. Your own screenwriter-practice doc cites both. Pipeline A already extracts a story profile with checkable premises in it; running the treatment's own factual assertions through something shaped like Pipeline B and filing a "premise notes" section in the bible would be the single most department-like feature you could add, and most of the machinery already exists.

### A truncated bible shipped silently

The Lenin Shipyard room's `research_bible` is 2,618 characters and ends mid-sentence — "…\n\nStreet" — a fragment of section 1 of what should be a four-section document. The Lagos room's bible came back complete at 12,714 characters, and your harness transcript shows a 16k bible on the McLemore room, so this is intermittent — which is worse, because nothing caught it. `parse_rate` is 1.0 on every drawer; findings have health metrics, the bible has none. A writer opening that room in the web app sees a document that just stops, in a product whose entire pitch is that nothing fails silently. Add a completeness check on synthesis output (ends mid-sentence, missing expected sections, length floor relative to findings volume) and re-run or flag when it trips. I know a remediation pass is already planned — this belongs on it, with a regression test.

### The failed room spends money and explains nothing

`get_room` on the errored room says the build "filed nothing," that polling won't help, and that "a shorter, more specific treatment usually gets further." That last clause is a guess dressed as guidance. The build charged the account's budgets and the room carries no reason — not even a category of reason (intake failed, planner failed, provider error, timeout). You don't have to leak stack traces to say "the department could not derive a story profile from this treatment" versus "a service the department depends on failed; this was not your treatment's fault." One is actionable, the other deserves a refund note. Right now a writer can't tell which happened, and a writer who paid for silence doesn't come back.

### The agent door has a token problem and a deletion problem

Your README already knows `get_room` returns ~37k tokens and warns against polling it after terminal status — but `get_room` *is* the poll, by design, so the first poll after completion dumps the entire room into the agent's context whether it wanted the bible, one drawer, or just the status line. My own session hit the ceiling twice today; every agent wired to this will burn the same tokens. `get_room` needs a shape argument — status-only, profile-and-plan, one drawer, bible — and "four tools and no fifth" survives intact, because this is still `get_room`.

Deletion is the sharper edge. `check_scene`'s response says the scene is now stored with the room and can be deleted "from the room's script-check panel in the web app." An MCP-only user has no web app open, and no tool deletes anything. For the audience your own aversion research describes — writers told by agents and WGA reps never to leave unproduced material on someone else's server — "your scene is stored and the delete button is in another application" is the close-the-tab moment, relocated to the agent door. If there is ever a fifth tool, it isn't build's sibling; it's `delete`.

### Small hygiene that a judge sees in the first minute

Three of the seven rooms on this account are titled "Untitled … Project," and one is an errored husk that can never change — the first thing `list_rooms` shows a new evaluator is a graveyard. There's no retitle or delete over MCP and apparently no cleanup. And check what actually ships in the public repo: `__pycache__`, `.superpowers` SDD internals, an 80KB process-notes file, and harness transcripts are honest working artifacts, but "public open-source code repository" is a submission requirement, and judges will open it cold.

---

## Part 3 — The naysayer's answer to the actual question: what makes anyone *adopt* this

Everything above is fixable inside the product you have. This section is about the product you may not have yet, and I'll say it as the screenwriter you researched: you have correctly diagnosed why I distrust AI tools, built the most trustworthy citation machinery I've seen at this scale, and attached it to a workflow I don't have.

Your own screenwriter-practice research says it plainly: research is continuous and demand-driven, not front-loaded. The Mad Men researcher's job was page-by-page anachronism review and *live questions from the room* — "was there a word for X yet." Nobody sits at treatment stage thinking "I need my four category drawers." They hit page 40, need one fact about rotary party lines in the next thirty seconds, and get it or write around it. Your adversarial doc calls Pipeline A a vending machine; I'll go further — the room is the *warehouse*, and you've built no counter to walk up to. The missing interaction is the small one: **ask the room a question**. One claim-shaped query, answered from the room's ledger first and one fresh search second, with the same provenance stamps, in seconds, for pennies. That is the Mad Men researcher in the writers' room, it's the feature a writer uses forty times a project instead of twice, and it is a thin recombination of code you already have — check_scene is already this, for the special case where the question is a scene.

Second: adoption lives where the writer already is, and you've under-recognized which of your two doors that is. The web app is the demo; the MCP server is the distribution strategy. A writer in 2026 increasingly has *some* assistant open next to their draft — and STAR-over-MCP inside that assistant is "highlight this scene, check it against my room" without leaving the page. Your README treats the MCP door as a compliance artifact with a known auth limitation. It's the product. Which is also why the token shape, the deletion story, and the ask-the-room tool matter more than any web-app polish: the surface you've been treating as the judges' checkbox is the only surface with a believable path to a writer's daily hands.

Third: the trust you've engineered is one-sided, and writers can smell asymmetry. Every mechanism in this codebase guards against *overclaiming a source* — hydration, downgrades, unsourced stamps. Nothing yet guards against *underclaiming the check's blind spots*, and Part 2 showed how that plays out: a salted scene sailing through with nine green stamps. The naysayer's rule: I don't distrust tools that miss things; I distrust tools that don't tell me what they'd miss. The legal-research analogy in your own aversion doc holds — the trusted tools are the ones that made verification fast, not the ones that claimed completeness. Say what wasn't checked, every time, in the same breath as what was.

Fourth, the boring adoption blockers, quickly: no visible retention or deletion policy at the point where a writer pastes unproduced material tied to their Google identity (your own critique's close-the-tab moment — still standing as far as the intake copy shows); no export, and a research bible a writer can't hand to a producer or paste into their show bible is research that stays in your app instead of their project; no price legibility before spending — writers budget; tell them what a room and a check cost before the button, not in the refusal after; and no room lifecycle — retitle, delete, re-run against a revised treatment — for the writer who revises the same treatment eight times and now owns eight half-duplicate rooms.

---

## Part 4 — The judge's scorecard

Against the Devpost rubric (implementation, design, impact, creativity, weighted equally):

**Technological implementation — strong.** Deterministic pipelines, ledger-computed provenance, hand-written MCP transport with excellent error copy, 473 tests, a persona harness that ships transcripts as artifacts, honest deployment notes. Genuine runtime integration of Gemini/ADK and Parallel in both pipelines — track compliance is airtight. The blind spots (extraction recall, silent bible truncation, opaque failure) are real but they are defects in a serious system, not a thin one.

**Design — distinctive, with a caveat.** THE MORGUE direction is the rare hackathon aesthetic derived from an argument rather than a template, and your anti-slop research shows in every line of copy. The caveat is your own adversarial doc's: make sure the shipped web experience matches the described one by demo day, because a judge who was promised drawers and receipts and finds a markdown blob will hold it against exactly the trust story you're telling.

**Potential impact — the weak leg, for the reasons in Part 3.** As pitched (paste treatment, get bible), it serves the front-loading minority of a small profession. As it could be pitched (a citation-honest research desk that lives inside whatever assistant a writer already uses, answers one question at a time, and checks scenes page-by-page like a studio researcher), the impact story writes itself and the WGA-era positioning — research and support, never generation — is already correct and already documented in your repo.

**Idea creativity — high.** "The model never authors a title, an excerpt, or a claim about where something came from" is a real idea, executed, measured, and demonstrably working live. It survived my sabotage attempt on the axis it defends. Now defend the other axis.

**Before September 7:** the 3-minute video should show the Walkman catch and an unsourced stamp on screen — those are your two unfakeable moments; fix the false-clean summary line first, because a judge who salts a scene the way I did and watches errors sail through under nine green stamps will discount the one claim your whole project stands on; put a one-line retention/deletion sentence on the intake screen; clean the room list; and decide what the public repo contains on purpose.

I planted three lies in your machine today. It caught one, ignored two, and never asked me why I was lying to it. That's a better result than any other tool in this category would have managed — and it is not yet the research department on the poster. The gap between those two sentences is your roadmap.

---

*Sources for the bridge-closure premise check: [BBC — Six months of traffic woe](https://feeds.bbci.co.uk/news/world-africa-55333365), [Al Jazeera — 2018 maintenance shutdown](https://www.aljazeera.com/video/2018/8/25/nigerias-third-mainland-bridge-shut-down-for-maintenance), [TheCable — reopening of repaired sections](https://www.thecable.ng/lagos-reopens-sections-of-third-mainland-bridge-closed-for-repairs/). Hackathon requirements: [agentic-cinema.devpost.com](https://agentic-cinema.devpost.com/). Live tests run against rooms `94a15bbca87e` (Gdańsk check, scene `81f390db3c9b`), `d04477363a9a` (errored room), and `ada00f565b29` (Lagos build, this session).*

---

## Response — the false-clean summary, measured before and after

*Added 2026-08-11 by the build, against the same room (`94a15bbca87e`) and a scene
salted the same way: guards waving a shift through without a search, oranges bought
without queueing, mimeographed pages smelling of spirit duplicator fluid.*

| | Before | After |
| --- | --- | --- |
| Tally | **9 confirmed, 1 anachronism, 0 unverifiable** | **3 confirmed, 3 anachronism, 0 unverifiable** |
| Planted errors extracted | 0 of 3 | **3 of 3** |
| Planted errors stamped | 0 of 3 | **3 of 3** |

Two defects, found in that order, because fixing the first exposed the second.

**Extraction was harvesting nouns.** The instruction already listed "a law, a
procedure" and every example around it named a thing, so things are what came back.
It now says most of its own list is nouns and most errors are not, with worked
examples in the shape it was missing, and instructs a second read for what the scene
asserts *happened* rather than what it names.

**Then the verdict standard was wrong, which only became visible once the claims were
being extracted at all.** On the intermediate run all three came back `unverifiable`
— and the third one's note read *"mimeographs used stencil ink, whereas spirit
duplicator fluid was used in spirit duplicators."* The desk had found the error,
written it down correctly, and stamped the claim unsettled. The second note conceded
that shortage queues were standard in 1978 Poland and still declined to flag.

The desk had slipped to a courtroom standard: asking whether one invented moment
could be proven impossible, which nothing about a fictional person on a fictional
night ever can be. It is judging whether the scene fits the world the sources
describe. If what it reads contradicts the claim, that is anachronism — and a note
that argues one way while the stamp says another is the desk disagreeing with itself
on the page.

**And the scope note ships regardless**, because it is true on runs where extraction
still misses. Computed from the claim types actually extracted, naming which kinds of
assertion are absent from the set. It does not print a count of what it missed: knowing
that number would mean having found them, and anything findable would have been
checked.

Still open from this critique: the bible completeness check, the errored room's reason,
repo hygiene, room lifecycle, `get_room` shape, a delete tool, and the ask-the-room
interaction in Part 3.
