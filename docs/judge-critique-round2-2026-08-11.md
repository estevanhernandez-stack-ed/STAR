# STAR — round two. The judge comes back after the remediation.

Date: 2026-08-11, evening. Method: same as round one, deliberately harder. I read the remediation commits first so I knew what you claimed to have fixed, then attacked the claims with *fresh* ammunition — a new salted scene using four error classes different from round one's (so a fix tuned to my last scene would fail), and a new room built from a treatment carrying a different false premise in a different city and decade. Everything below happened live today against rooms `94a15bbca87e` (scene `efa55c83ef9c`) and `d93dae8eb142`.

The remediation was real. Here is the scorecard, finding by finding.

---

## Part 1 — What round one found, re-tested

### The false-clean check — FIXED, and it generalized

This was the finding that mattered most, and I did not re-run my old scene, because your commit log told me you'd measured against it ("Nine green stamps on a salted page, now three anachronisms"). A fix that memorizes the test is worthless, so I wrote a new one. Four planted errors, none of them classes from round one: a character paying at a Pewex counter in złoty (procedural-economic — Pewex took hard currency and coupons only), a Solidarność banner in 1978 (institutional anachronism, two years early), stencil ink poured into a spirit duplicator's reservoir (the inverse of round one's machine confusion), and a ZOMO conscript walking foot patrol alone with no radio (procedural).

**All four were extracted, all four were stamped anachronism, all four cited sources that resolve.** The Pewex verdict quoted the Polish Wikipedia passage on dollar-denominated pricing. The duplicator verdict pulled the exact sentence — "There is no separate ink used in spirit duplication" — that settles it. The solo-patrol verdict is the one that impressed me most: it cited an IPN academic journal article on the Gdańsk ZOMO unit, from the room's own files, containing a veteran's recollection that patrols went in pairs with one shared radiotelephone. That is not a search-engine answer; that is the room's research paying off on a question I invented to be hard.

And then the check did something I did not plant. My scene included, as a *truth control*, women queueing outside a Społem grocery "with ration cards for butter." The check flagged it: butter rationing was introduced in April 1981; in 1978 the only rationed product was sugar. **The judge salted the scene and the desk caught an error the judge didn't know he'd made.** Queues, yes; ration cards for butter, no. That moment — the tool out-researching a hostile expert reader on the reader's own planted terrain — is the single best demo beat this product now owns, better than the Walkman. Put it in the video.

Round one's summary was 9 confirmed / 1 anachronism / 0 unverifiable on a scene carrying three errors. Round two, on a harder scene: **5 confirmed / 5 anachronism / 0 unverifiable — and all five stamps are correct, including one I'd have marked wrong myself.** The fix note in the commit is also the right diagnosis: the desk had been applying a courtroom standard (can this be proven impossible?) instead of a research desk's (does this fit the world the sources describe?). That reframing generalized to error classes it had never seen.

One label quibble survives: "anachronism" is now carrying weight the word doesn't mean. Paying złoty at a Pewex isn't a time error, it's a procedural impossibility; patrolling alone isn't early or late, it's against practice. The notes explain correctly, so no writer is misled, but a third verdict word — `contradicted`, for "the sources describe a world this doesn't fit" — would let the stamp say what the note says.

### The scope note — SHIPPED, working, honestly designed

The check now says, in the same breath as the tally: "This check examined 10 claims, about objects, places, technology, words and phrases, how people behaved or what they were allowed to do. Nothing here is a claim about timings and durations. If the scene asserts any of that, it was not examined." That is exactly the underclaiming guard round one asked for, and the implementation refuses the tempting overreach — it does not pretend to count unexamined claims, because anything findable would have been checked. Correct instinct, correctly argued in the docstring.

### The truncated bible — FIXED at the root, and the diagnosis was better than mine

I found one truncated bible; your remediation found two of three stored rooms and the actual mechanism — `max_output_tokens` on a thinking model bounds thinking *plus* output, so the rooms that researched hardest thought longest and shipped the shortest documents. 125 sources → 654 tokens of bible; 95 sources → a complete 3,528. The correlation running backwards is what proves the cause, and the fix (a bounded thinking allowance, writing keeps the rest) targets it. Verified live: tonight's build shipped a complete 16,453-character bible ending on a citation, from 117 sources — the most sources of any room on this account, which under the old defect would have produced the *shortest* bible. Fixed where it was broken.

Still open on this item: the two damaged stored rooms are still damaged. Lenin Shipyard and Ruth Kovacs still carry their cut bibles, still report `complete`, and I found no resynthesis path. Forward-fixed is real, but a writer who opens Ruth Kovacs sees a document that stops at "river tracks to" with a status that says finished.

### The premise check — SHIPPED, and it caught the new plant

Round one's Lagos room researched around a false premise without ever pointing at it. Tonight I buried a different one — "the citywide blackout of September 1977" in a South Bronx treatment; the blackout was July 13–14 — and the bible came back with a **"Verify before writing" block naming the discrepancy directly**: the intake says September, historical research confirms July 13–14, 1977, during the mid-July heatwave. The department now does the thing that makes it a department: it tells the writer their load-bearing premise is dated wrong, in the document, where they'll read it. This was the largest product gap in round one and it is closed. What I'd add is placement: the callout lives inside the bible's prose. It belongs in the room's *summary* too — a writer who skims drawers and never reads the bible top-to-bottom shouldn't miss the one line that saves them a rewrite.

### The MCP auth gap — addressed beyond what was asked

Round one didn't even press on this; the README disclosed it honestly. The remediation shipped a real authorization server anyway — protected-resource metadata, the discovery flow a spec-compliant client expects, plus the serverInfo icon fix with a test that fetches every icon URL the handshake names and compares it to what it claims. That last test immediately caught a Windows-vs-container MIME divergence, which is the kind of thing that only surfaces when a test asserts reality rather than intent. Good.

---

## Part 2 — Still standing, carried forward

These are unchanged from round one, re-verified against tonight's code, listed by weight.

**The `get_room` payload.** Still one shape, still ~30–37k tokens on a complete room, still no summary / drawer / bible-only argument. I hit my own tooling's output ceiling on it twice more today. Every agent wired to this pays the full room on the first poll after a build completes. This is now the largest remaining defect on the surface you should care most about.

**No delete over MCP.** `check_scene` still stores the scene and still points at the web app to delete it. The web intake now carries honest retention copy — "your treatment itself is not stored," and the scene-storage explanation with delete-follows-check semantics is well written — which softens round one's close-the-tab moment considerably in the browser. But the agent door still writes and cannot erase.

**The error room still explains nothing.** Same copy, no failure category, budgets still charged for a diagnosis that amounts to a guess. `partial` and `interrupted` are now finely differentiated — the error path deserves the same care.

**Room hygiene.** The account still lists three "Untitled" rooms and the errored husk; no retitle, no delete, no way to clean up over either door that I could find from the MCP side.

**The harness.** The salted-scene test lives in `test_verdicts.py` as unit coverage, which is good, but the persona harness still has no hostile-writer persona. The measure that caught round one's biggest defect was a judge doing it by hand; that judge should be a transcript in `harness/runs/` that reruns on demand.

**The adoption thesis — untouched, and that's fine for this week.** Four tools and no fifth: still no `ask_room`, still no export, still no price display before the spend, still no room lifecycle. I stand by all of it as the post-hackathon roadmap, and I'd sequence `ask_room` first, then `get_room` shapes, then delete. None of it blocks the submission.

---

## Part 3 — The revised scorecard

**Technological implementation** — was strong, now stronger, and the *remediation itself* is evidence a judge should weigh: the commits reproduce the critique's findings before fixing them, measure the fix against the same instruments, and in two cases (the bible's backwards correlation, the MIME divergence) found root causes more interesting than the symptoms. That is engineering culture, not hackathon triage.

**Design** — the scope note and retention copy are design in the sense that matters here: sentences load-bearing for trust, placed where the skeptical reader actually is. I did not re-review the visual layer; the glow-campaign commits suggest it moved, and the round-one caveat (shipped app must match described app by demo day) stands until someone opens the URL and looks.

**Potential impact** — moved. Round one's complaint was that the check confirmed nouns while the world slipped past, which capped the product at reassurance theater. Tonight the check caught a currency rule, an institutional founding date, a machine's internals, a patrol protocol, and a rationing timeline — five different kinds of world — and told me what it didn't look at. That is a tool a Mad Men-style researcher could actually lean on, which means the impact story is no longer aspirational copy. It still needs the distribution answer (the MCP door in the writer's daily assistant) to cash it.

**Idea creativity** — unchanged, high, and now better proven: the ledger idea survived a second adversarial pass that was designed to route around the first pass's fixes.

**Verdict, both hats off.** Round one ended: *it caught one of my three lies, ignored two, and never asked why I was lying.* Round two: **it caught four of four new lies, corrected a fifth error I didn't know I'd told, flagged the false premise in my treatment, and told me what it hadn't examined.** The naysayer's remaining objections are now about reach and lifecycle, not trust. That is a different, and much better, class of problem — trust was the one you couldn't have shipped your way out of later.

Before September 7, in order: the demo video (lead with the butter ration cards — the moment the tool out-researches its own auditor — then the premise callout, then an unsourced stamp); surface the "Verify before writing" block in the room summary as well as the bible; resynthesize or honestly mark the two damaged stored bibles; and give `get_room` a shape argument if any agent-facing demo is planned, because 37k tokens per poll is the first thing a technical judge wiring it up will feel.

---

*Round-two evidence: scene `efa55c83ef9c` against room `94a15bbca87e` (5 confirmed / 5 anachronism, scope note present, 3 searches); room `d93dae8eb142` "BROWNOUT" (17 searches, 117 sources, complete 16,453-char bible, "Verify before writing: Date Discrepancy" naming the planted September date against the actual July 13–14, 1977 blackout). Remediation commits reviewed: `80ebcdd`, `30a2264`, `d089b34`, `800b9a2`, `6a7ea31`, and the wave series through `b6d55d5`. Round-one document: `docs/judge-critique-2026-08-11.md`.*
