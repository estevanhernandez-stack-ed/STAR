# STAR — adversarial critique from a working screenwriter

Grounded in the actual repo (`C:\Users\estev\Projects\STAR`) as of 2026-08-09, not just the pitch copy: `web/index.html`, `web/app.js`, `web/styles.css`, `star/config.py`, `star/server.py`, `star/findings.py`, `star/agents/researchers.py`, `docs/adversarial-review-2026-08-06.md`, and `docs/superpowers/specs/2026-08-09-star-gui-design.md`.

---

## 1. Would I actually use this? The exact moment I'd close the tab.

Before the four minutes even starts: **"Sign in with Google to hand your treatment to the department."** `web/app.js` treats Firebase Auth as a hard dependency — no token, no request, full stop (`"STAR needs Google sign-in to run"`). Per the GUI spec, every room persists to `/users/{uid}/rooms/{roomId}` in Firestore, tied to my identity, with no stated retention or deletion policy anywhere in the intake copy. Every working writer has been told by an agent, a WGA rep, or plain paranoia never to paste unproduced material into an identity-linked account with no visible data policy. That's the close-the-tab moment, and it happens before I've read a single researched fact.

If I get past that: the "about four minutes" claim in the brief is already contradicted by the product's own commit history from *today*. `star/config.py` documents observed run durations for one fixed treatment ranging **146 seconds to over 420 seconds**, and the timeout was raised from 420s to 600s after a legitimate run sat for **nine minutes** with the UI spinning and no error. I'm not watching a four-minute wait — I'm watching an indeterminate wait, styled as a scrolling `<ul>` of "X is searching the live web" with a pulsing ellipsis and no percentage, no ETA, nothing to tell me if it's almost done or hung. Past minute five of that, I close the tab and assume it broke, because nothing on screen tells me otherwise.

## 2. What's wrong with the design for a screenwriter, specifically

**The grid isn't for me — it's for the judges.** The design spec says this outright: *"The Agentic Cinema Stage Two rubric scores implementation, design, impact, and idea with equal weight. Design is a quarter of the score, and the current frontend gives away its strongest asset: four researchers genuinely run at once... The architecture's most interesting property is invisible."* That is the design brief. Not "writers need to see four categories at once to work faster" — "judges need to see parallelism to score it higher." I don't care that four API calls happened concurrently. That's an implementation detail cosplaying as a feature, the same instinct as a magician narrating the mechanism instead of performing the trick.

**The left rail assumes I file research the way a Notion power-user files docs.** I don't keep a standing library of "rooms." I research one project hard, then I'm done with it, or I revise the same treatment eight times and now have eight stale, half-duplicate "rooms" cluttering a sidebar with no merge, no versioning story visible anywhere in the spec.

**The reading view's "receipts" don't exist yet.** As shipped right now, `web/app.js` renders `research_bible` as one `marked.parse()` blob of markdown with inline `<a>` links — indistinguishable from any ChatGPT-with-browsing transcript. The clickable-chip-expands-to-excerpt view is Phase 3 of a four-phase plan (`docs/superpowers/specs/2026-08-09-star-gui-design.md`), and only Phase 1 — invisible backend plumbing — has any completed task reports in `.superpowers/sdd/2026-08-09-gui-phase-1-ledger-and-findings/`. I was shown a mockup of a UI that does not run. If a writer clicks the actual URL today, they get a single-column timeline and three flat tabs (Bible / Profile / Plan), not the 2×2 grid described to me. That gap, presented as "the product," is the kind of bait-and-switch that kills trust with exactly the audience STAR needs.

**The timeline is progress-bar theater, and it's the least screenwriting-specific part of the whole thing.** Gold pulse, agent name, "is searching the live web" — that's the identical interaction pattern as every "watch the agents work" AutoGPT/CrewAI dashboard since 2023. Swap "Setting researcher" for "Planner" and "Props researcher" for "Coder" and nothing else changes.

## 3. What the "research department" metaphor gets wrong

It borrows institutional weight it can't back up. A real studio research department is something you talk to — you say "no, go deeper on the getaway-car mechanics, drop the guitar tangent" and it adjusts. STAR runs once against a fixed plan generated from your treatment and hands you a finished document. You can't interrupt it, redirect it, or ask a follow-up. It's not a department, it's a vending machine wearing department-flavored copy: "the Setting researcher filed their work," "Head of research," "Editor." The moment a writer realizes they can't talk back mid-run, the metaphor stops flattering and starts feeling like a costume.

It also imports an authority the tool doesn't have. Real studio research departments exist partly for **E&O liability** — defamation review, real-person/real-place legal clearance, chain-of-title research — backed by lawyers and paid consultants, not just search-and-summarize. "Every studio has a department, now every writer does" tells a solo spec writer they've been handed institutional rigor. What they've actually been handed is four parallel Google-adjacent searches with citation-hygiene checking. A writer who's been through a real clearance process will feel that gap immediately, and it will read as presumptuous rather than empowering.

## 4. Where it looks like every other AI product

Dark ground, gold accent, Georgia serif is the exact palette "premium AI for creatives" has converged on since 2024 — it's the "we want to feel literary" default, the Canva-template version of literary. The live-search timeline with named agents filing in real time is structurally identical to every agent-swarm demo dashboard since AutoGPT went viral, just with researcher titles instead of Planner/Coder/Reviewer. The citation-chip-with-hover-excerpt idea is Perplexity's UI, described almost verbatim, minus Perplexity's actual shipped polish (which, notably, this app doesn't have yet either — see #2).

Cost with peers: screenwriters have been pitched "AI for creatives" for two years and have learned to clock dark-mode-gold-serif-plus-agent-swimlane as a tell for "built by developers who skinned a hackathon demo," not "built by someone who understands craft." The aesthetic actively undercuts the one differentiated claim the product has — "we don't write your script, we just do research" — because everything about the visual language screams generic AI-does-your-job tool before that distinction ever gets read.

## 5. Why it gets dismissed in the first ten seconds

One textarea, one button labeled "Build the Room," one line of pitch copy above it. Nothing on the actual intake screen (`web/index.html`) tells a first-time visitor what the tool *won't* do before they commit a treatment. "Paste your idea, something happens" is the exact shape of every failed AI-screenwriting-assistant landing page a working writer has already been burned by. The differentiating claim — four researchers, live citations, fabrication-checking — is completely invisible at the point of commitment. It only becomes visible *after* you've pasted your logline, signed in with Google, and waited through an indeterminate multi-minute build. By then the skeptical writer has already half-decided what kind of tool this is, and the UI gave them nothing to correct that read.

## 6. The objection a software designer wouldn't anticipate

Research for a script isn't front-loaded by category — it's associative and scene-triggered. Nobody sits down at treatment stage and thinks "I need the LOGISTICS category for 1962 Memphis." They hit page 40, realize the plot hinges on how a rotary party line actually worked, and need that one fact in the next thirty seconds, in context, mid-draft — not bundled into a four-minute batch job triggered back at the logline stage. STAR's whole shape — one big upfront research pass split into four fixed categories — solves the research problem of a small minority of writers (outliners who front-load everything) and misses how most working screenwriters actually hit and resolve research gaps: iteratively, scene by scene, usually while avoiding the scene itself.

`star/agents/researchers.py` also reveals the category taxonomy is fixed and generic — setting, props, logistics, forces & conflicts — not adaptive to what the treatment is actually about. A heist film and a courtroom drama get the same four buckets. A writer whose story lives or dies on something outside those four (medical procedure accuracy, a specific subculture's slang, a niche sport) gets a department that structurally can't hear the question.

## 7. Is the flagged fabrication brave or damning? The case for damning.

Admitting the system invents citations, even dressed as "flagged, not hidden," is a confession that the headline promise — "every fact cited to a real source, no invented facts" — is not actually guaranteed, only checked after the fact and disclosed when the check fails. If a human researcher turned in a bible and said "three of these citations I made up, but don't worry, I highlighted them in yellow," the correct reaction isn't "brave transparency," it's "why did you turn in fabricated work, and how confident am I that your checker caught all of them and not just some?"

And the checker is narrower than the marketing implies. Per `star/findings.py`, the verification is a **URL-membership check against a ledger of what `parallel_search` actually returned** — it can only catch a citation whose *URL* was never seen. It cannot catch a real, ledger-verified URL attached to the wrong fact, a cherry-picked or misleading excerpt, or a low-quality source (a fan wiki, an SEO content farm) that happened to rank in Parallel's index. So the green "verified" state covers exactly one narrow failure mode and stays silent on a much more dangerous one. Worse: proving the system does aggressive checking on the narrow case will make a writer trust everything *else* on the page more, not less — the flag can manufacture false confidence in precisely the claims it isn't checking.

Leading with "we catch our own hallucinations" as a headline feature, before a writer has formed any baseline trust in the product, tells a skeptical audience that hallucination is expected, known behavior of this system — before they've decided to believe anything else it says. That's a costly first impression for a tool whose entire pitch is "trust our facts."

---

## What's genuinely good

The citation-integrity engineering is real, not hand-waved: researchers are only ever trusted to reproduce a URL they actually saw, while titles and excerpts are hydrated server-side from a `SourceLedger` built from actual `parallel_search` responses — the model never gets to author a title or an excerpt, only point at a URL. That's a materially better answer to citation fabrication than most "AI research" tools ship, and it's backed by a real measurement (`star/findings.py`'s docstring: 31 of 31 bible source lines carried the ledger's real title in a verified end-to-end run), not a claim taken on faith.
