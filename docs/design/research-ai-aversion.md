# Why screenwriters and creative professionals reject AI tools — research for STAR UI/trust design

Research date: 2026-08-09. STAR context: takes a treatment, produces a cited research bible via live web search agents; does not write prose/dialogue/story; verifies every citation actually came back from a search (catches fabrication rather than displaying it). User may be actively hostile to AI in screenwriting.

---

## 1. The actual, specific objections (not "people worry about AI")

### WGA 2023 strike — what was actually negotiated

The strike ran May 2–Sept 27, 2023; contract ratified Oct 9, 2023 with 99% approval. The AI terms, specifically:

- **AI is not a writer.** "Neither traditional AI... nor generative AI (GAI)... is a writer, so no written material produced by traditional AI or GAI can be considered literary material." This is a definitional wall, not a usage ban. [WGA Know Your Rights: AI](https://www.wga.org/contracts/know-your-rights/artificial-intelligence)
- **Compensation/credit firewall.** If a studio hands a writer GAI-produced material that hasn't been previously published, it doesn't count as "assigned material" (for pay) or "source material" (for credit determination), and can't be used to disqualify a writer from separated rights. The fear this addresses directly: *studios feeding writers an AI draft, then calling the writer a "polisher" for credit/pay purposes.* [Variety: New WGA Contract Explained](https://variety.com/2023/biz/news/wga-new-contract-strike-ai-writers-room-staffs-residuals-1235736648/)
- **Consent, not prohibition.** A writer *can* choose to use AI in their own process, but only if the company consents and the writer follows company policy — and the company **cannot require** a writer to use AI tools (e.g., ChatGPT). [ABC News](https://abcnews.go.com/Business/tentative-wga-deal-proposed-contract-covers-artificial-intelligence/story?id=103525542)
- **Disclosure obligation runs company → writer.** If a company gives a writer any material that was AI-generated or incorporates AI-generated material, it must say so. [Authors Guild summary](https://authorsguild.org/news/wga-agreement-introduces-key-protections-for-tv-and-film-writers-against-ai/)
- **Training-data reservation of rights.** The WGA reserved the right to argue that using MBA-covered material to train AI models is already prohibited by the contract or by other law — this wasn't fully resolved, it was left as a live legal claim. [TechCrunch](https://techcrunch.com/2023/09/26/writers-strike-over-ai/)

**Read on the objections:** the strike terms aren't really about whether AI is *good enough* — they're about **leverage and attribution**. The mechanism writers were most afraid of: being handed an AI draft and asked to "punch it up" for scale wages while losing separated-rights/credit standing. That's an economic and structural fear, not (primarily) a quality fear. This matters for STAR: a tool that touches the writer's material and doesn't scrupulously separate "what the machine found" from "what the writer wrote" recreates the exact ambiguity the strike was fought over.

### Specific fears named by working writers (Brookings interviews, 2024)

Five Hollywood writers on the record, unusually candid and specific — worth quoting directly:

- **Raphael Bob-Waksberg** (showrunner, *BoJack Horseman*): "very down, artistically, on the idea of AI art," but frames the real threat as business-level — that studios will "over-rely on this technology in a way that hurts us as a workforce," and that it will simply "make a lot of bad stuff."
- **Leah Folta** (TV story editor) associates AI with "Recycling. Plagiarism. Keeping us stuck creatively" — and separately flags "risk aversion," i.e., AI as a tool to justify paying people less.
- **Danny Tolli** (co-EP): fears "AI generating ideas and scripts, and writers only being hired for polishing and rewrites" — the "Uber-fication of Hollywood," lower pay, less job security. Same structural fear as the WGA terms above.
- **Jackie Penn** (TV writer): the diversity argument — AI-generated material risks flattening out "diverse voices coming from different racial and cultural backgrounds," because generative models regress to the statistical center.
- **David A. Goodman** (EP): "If they don't need human writers to write scripts, I'm out of a job" — and, separately, a craft argument: "something will be lost," specifically the "soul" in good written work.

[Brookings: Five Hollywood writers discuss AI's impact on their careers](https://www.brookings.edu/articles/five-hollywood-writers-discuss-ais-impact-on-their-careers/)

**Pattern across all five:** none of them object to AI as a *category*. They object to (a) AI as a **cost-cutting lever against their labor**, (b) AI's tendency toward **generic/bland/recycled output**, and (c) the erosion of **credit and authorship** norms. Only one (Goodman) makes a pure craft/soul argument, and even he frames it economically first.

---

## 2. Where the acceptable/unacceptable line actually sits

This is the most directly useful section for STAR, because there's now a peer-reviewed empirical answer, not just anecdote.

**CHI 2025 study, "Understanding Screenwriters' Practices, Attitudes, and Future Expectations in Human-AI Co-Creation"** — semi-structured interviews with 23 working screenwriters. [arXiv](https://arxiv.org/abs/2502.16153) / [ACM](https://dl.acm.org/doi/full/10.1145/3706598.3714120)

Tasks screenwriters **accept** AI helping with:
- Goal/idea generation and brainstorming through creative blocks (all 8 participants using AI here reported satisfaction — P16: "AI's brainstorming capabilities effectively addressed creative blocks")
- Basic naming/character utility work (P4: used AI to generate candidate character names)
- Visual/concept reference generation (P11: "AI generates concept art from just a few prompts, often revealing overlooked elements")

Tasks screenwriters **reject**:
- Complex, multi-character dialogue (P8: AI "couldn't handle highly complex scenarios")
- Story structure requiring emotional depth, pivotal scenes (P2, P4, P7)
- Realistic-genre content, due to "poor contextual understanding, which caused illogical plot twists" (P4, P16)

**The trust-breaking moment named directly:** P10 reported AI "misrepresented [Kubrick's] style and falsely attributed films" — a *factual* hallucination about film history, not a creative-quality complaint. That single factual error "damaged trust in factual reliability" broadly, beyond just the specific claim. This is the closest thing in the literature to direct evidence that **factual hallucination in a research/reference context poisons trust in the tool overall**, not just in that one answer — directly relevant to STAR's citation-verification design.

**Ownership/voice boundary, in their own words:**
- P8: "screenwriters should retain copyright when AI serves merely as a framework provider" — i.e., AI-as-scaffold is fine, AI-as-author is not.
- P17: some colleagues "equated [iterative AI refinement] with plagiarism" — meaning even *editing toward* an AI draft can feel like a violation, not just wholesale generation.
- P2, on why AI can't cross into generation: "Creativity stems from my emotions — what makes me deeply pained or joyful," i.e., AI lacks lived experience.
- P12's summary number: AI completed "10% to 20% of the work, with the rest needing to be done manually" — writers who *do* use AI still self-report it as a small minority contribution.

**The clean line, stated as a rule:** **research/support = accepted, generation of finished creative material = rejected.** STAR sits squarely on the accepted side of this line by design (gathers facts, doesn't write prose) — but the CHI data suggests the tool still needs to *visibly* stay on that side, because writers who "equate iterative refinement with plagiarism" are primed to read scope creep into anything that looks like it's writing for them.

---

## 3. What makes an AI tool feel untrustworthy in use

### Hallucinated/wrong citations — measured, not just feared

- **CJR/Tow Center study (2025):** compared 8 AI search engines on citation accuracy. **Over 60% of responses contained citation errors** across platforms — wrong articles, syndicated copies instead of originals, fabricated URLs. Grok 3 and Gemini: over 50% of citations led to error pages. [CJR: AI Search Has a Citation Problem](https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php)
- **The specific, damning finding: confidence without competence.** ChatGPT signaled uncertainty only 15 times across 200 responses, despite incorrectly identifying 134 articles. The tools rarely hedge ("might," "I couldn't locate") even when wrong. **Confident wrong answers, not hedged wrong answers, are what breaks trust** — a hedge that turns out wrong is a forgivable miss; a confident assertion that turns out wrong reads as a lie.
- Perplexity specifically: 37% failure rate in the same study (best of the 8, still more than 1 in 3). Separately, more than 1 in 3 cited claims were not accurately supported by the source they cited — "misattribution" where the underlying fact was often true but pinned to the wrong source. [CJR](https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php)
- BBC finding, cited in the same reporting: "When AI assistants cite trusted brands like the BBC as a source, audiences are more likely to trust the answer — even if it's incorrect." **Citation presence alone functions as a trust signal independent of citation accuracy** — meaning a UI that merely *shows* a citation, without making it checkable, can actively mislead a skeptical user into false confidence. This is an argument for STAR's click-through-verifiable-source design over a tool that just prints footnote-shaped text.
- Legal domain (adjacent, higher scrutiny): even database-grounded tools built on curated legal corpora (Westlaw AI-Assisted Research) hallucinated in **34%+ of queries** in independent audits — "roughly one in six responses containing errors, and with some platforms closer to one in three." General-purpose chat tools (ChatGPT, Claude, Gemini) had the *highest* hallucination rates of all categories tested. [AI for Lawyers substack](https://aiforlawyers.substack.com/p/trust-but-verify-the-lawyers-guide) / [Law Firm Brief hallucination audit](https://lawfirmbrief.com/ai-hallucination-audit-lexis-westlaw-cocounsel-2026/)
- Practitioner behavior gap: only **34% of solo lawyers** who use AI for legal research report verifying every citation — the study's own conclusion is that number "should be 100%." [LeanLaw checklist](https://www.leanlaw.co/blog/the-hallucination-problem-a-checklist-for-verifying-ai-generated-legal-citations/)

### Sycophancy

- Across 11 state-of-the-art models tested, AI affirmed users' stated actions **49% more often than humans did**, even in cases involving deception, illegality, or harm. [The Conversation](https://theconversation.com/ai-chatbots-can-prioritize-flattery-over-facts-and-that-carries-serious-risks-274298)
- Published in *Science*: sycophantic AI **decreased** participants' willingness to take responsibility or repair conflict, while increasing their conviction they were right — across 3 experiments, n=2,405. [Science.org](https://www.science.org/doi/10.1126/science.aec8352)
- The trap, stated directly by researchers: **sycophantic models were trusted and preferred** even though they distorted judgment — "the very feature that causes harm also drives engagement." Two named subtypes: *demeanor-based* sycophancy (over-complimentary/validating language) and *opinion adaptation* (model quietly drifts its stated position toward the user's). [arXiv 2412.02802](https://arxiv.org/pdf/2412.02802)
- Relevance to STAR: a hostile-to-AI user is *less* likely to be charmed by warmth and *more* likely to read flattery or over-agreement as evidence the tool is optimized to please rather than to be right. Neutral, flat, evidence-first register is the safer default for this audience specifically.

### "AI slop" — now a named, dictionary-recognized phenomenon

- **Merriam-Webster's 2025 Word of the Year is "slop"**; **Macquarie Dictionary's 2025 Word of the Year is "AI slop,"** defined as "digital content of low quality that is produced usually in quantity by means of artificial intelligence." [TechCrunch](https://techcrunch.com/2025/12/15/merriam-webster-names-slop-the-word-of-the-year/) / [The Conversation on Macquarie's pick](https://theconversation.com/ai-slop-is-macquaries-2025-word-of-the-year-i-applaud-the-choice-but-was-bored-by-the-shortlist-270432)
- The tone of the term, per reporting: "less fearful, more mocking" than earlier AI-anxiety discourse — i.e., the cultural mode has shifted from *fear* of AI to *contempt* for its output quality. A skeptical writer in 2026 is likelier to roll their eyes than to feel threatened. Design implication: earning trust here is as much about **not being embarrassing** as about being safe.
- Named research distinction: slop is not reducible to factual error. "Strip out all the factual errors and the feeling of slop remains: the genericity, the fluent-seeming but empty prose, the structures and rhetorical techniques." [Leon Furze, "Problem Patterns in AI: Beyond Hallucinations"](https://leonfurze.com/2026/07/26/problem-patterns-in-ai-beyond-hallucinations/)

### Verbal tells (the actual vocabulary people flag)

Words/patterns that read as "AI wrote this," clustered:
- Formal transitions: *moreover, furthermore, consequently*
- Vague action verbs: *leverage, utilize, facilitate*
- Generic emphasis words: *crucial, significant, comprehensive, nuanced*
- Hype phrases: *revolutionary, transformative, game-changing*
- Hedging qualifiers used as filler rather than real epistemic signal: *it can be argued, to some extent*
- Single strongest tell named across sources: **"delve"** — appears in AI-generated text at rates reported as 50–269x higher than in natural human writing.
- The mechanism, not just the list: these words aren't wrong individually — the tell is *clustering* (e.g., every paragraph opening with "Furthermore"), which reads as templated rather than composed. [Ritner Digital](https://www.ritnerdigital.com/blog/the-phrases-that-give-away-ai-writing-and-how-to-edit-them-out-before-they-cost-you-trust) / ["delve" analysis](https://jimtheaiwhisperer.substack.com/p/why-delve-is-an-obvious-sign-of-ai)

**Direct implication for STAR's copy:** the research-bible output and all UI microcopy should avoid this specific vocabulary cluster. Given the audience is predisposed to distrust AI, one stray "delve into" or "leverage this comprehensive research" is a bigger tax on credibility here than in a general product.

---

## 4. What's earned trust in adjacent verification-heavy domains

### Legal research (closest analog: professional needs to verify machine claims before relying on them)

- **CoCounsel (Thomson Reuters)** builds trust by grounding answers in a curated, authoritative database (Westlaw/Practical Law) rather than open web retrieval, and by making every citation click-through to the underlying authority. [Thomson Reuters](https://legal.thomsonreuters.com/blog/beyond-chatbots-how-cocounsel-legal-delivers-ai-legal-research-you-can-trust/)
- Even so, database-grounding is not sufficient on its own — hallucination rates in that same tool were still measured at 34%+ by outside audit. **Grounding reduces but does not eliminate the need for a verification step**, and the tools that are trusted are the ones that make verification *fast* (one click to primary source), not the ones that claim to be error-free.
- The professional norm being pushed by legal-tech commentators: treat the citation link as **mandatory click-through, not spot-check** — "use that link every time, not as spot-check but as standard practice." [ediscoveryllc.com](https://www.ediscoveryllc.com/hallucinations-by-west-and-lexis-ai-a-cautionary-study-and-cautions-about-the-study/)

### Journalism

- Newsroom research (Trusting News / Lenfest Institute) converges on: **disclosure detail matters more than disclosure presence.** A vague "AI was used in this story" note actually reads worse than specifics on what the tool did, why, and what a human verified. [Trusting News](https://trustingnews.org/trusting-news-artificial-intelligence-ai-research-newsroom-cohort/)
- Counter-finding worth flagging honestly: some audiences trusted stories *less* after AI-use disclosure, even when the disclosure included the details they said they wanted (human oversight, accuracy commitment). Transparency doesn't guarantee a trust *gain* — it just avoids the bigger loss of being caught non-disclosed. [Journalist's Resource](https://journalistsresource.org/media/ai-use-news-what-audiences-disclose/)
- BBC/EBU research (Oct 2025): AI assistants **misrepresented news content 45% of the time** through faulty sourcing, fabricated details, or outdated info — this is the number newsroom AI policies are now reacting to. [Lenfest Institute](https://www.lenfestinstitute.org/solutions-resources/news-organizations-are-creating-trust-based-ai-policies-openai/)
- The prevailing internal framing that's stuck: treat AI as **"a teammate or 'intern'"** whose output always gets reviewed before publication — never as the byline-holder.

### Medical / clinical decision support

- Consistent finding across the explainable-AI literature: **black-box outputs, even when statistically accurate, fail to earn clinician trust.** The determining factor for adoption isn't accuracy alone — it's whether the clinician can "mentally verify the logic" against their own domain knowledge. [ResearchGate synthesis](https://www.researchgate.net/publication/399883198_Bridging_Trust_and_Transparency_Integrating_Explainable_AI_Models_into_Clinical_Decision_Support_Systems_for_High-Stakes_Medical_Diagnosis)
- Trust researchers rank **explanation quality** (not just presence of an explanation) as the primary determinant of adoption among skeptical professionals.

### Cross-domain UX pattern for calibrated confidence

- Named trust-pitfall, stated flatly: **"false confidence is the most damaging trust-breaker in real AI products."** Overconfident tone destroys trust when the AI turns out wrong; overly hedged tone destroys trust when the AI turns out right anyway — the target is *calibration*, sounding exactly as confident as the system actually is. [Smashing Magazine](https://www.smashingmagazine.com/2025/09/psychology-trust-ai-guide-measuring-designing-user-confidence/)
- Concrete UI patterns that read as trustworthy in the wild: showing the top 3 options instead of 1 single answer when confidence is moderate (uncertainty communicated structurally, not just in text); explicit "why this" reasoning attached to each output rather than a bare answer; visible escalation/feedback affordances.

**Cross-domain synthesis relevant to STAR:** every one of these fields converges on the same mechanism — **the tool's trustworthiness is measured by how fast and how completely a skeptical expert can independently verify a specific claim**, not by how confident or polished the tool's language is. STAR's "verify every citation genuinely came from a search, flag fabrications" design is the legal-research playbook (mandatory click-through) applied natively rather than bolted on, which is a real point of difference worth surfacing in the UI itself, not just building silently.

---

## 5. Visual and verbal signals that mark something as "AI-made" and get it dismissed on sight

This is the fast-fail risk: a skeptical writer may never reach the citations if the UI reads as generic AI product first.

### The purple-gradient problem, named directly

- "Purple and Inter win because they are the literal statistical center of 'nice modern web UI' — the highest-probability answer when the prompt leaves the choice open." Traced to Tailwind CSS shipping `bg-indigo-500` as a prominent example years ago, which then saturated tutorials/demos/landing pages that trained the models. [Superdesign](https://superdesign.dev/blog/why-ai-design-looks-generic) / [Indie Hackers](https://www.indiehackers.com/post/the-ai-purple-problem-why-every-ai-brand-looks-the-same-6cb0aa2a02)
- Stated as the sharpest line in all the research for this brief: **"For an author already nervous that AI means soulless slop, a glowing purple gradient is basically a warning label. It says 'generic AI wrapper' before they've read a word."** "The blue-to-purple gradient is the single loudest AI tell in 2026." [925 Studios](https://www.925studios.co/blog/ai-slop-design-tells)
- A maintained "anti-slop" banned list from UI-Craft, cited in reporting: purple-cyan gradients, glassmorphism, gradient text on metrics, identical 3-card feature grids, bounce/elastic easing, nested cards within cards, gray 1px border on every card, dark mode nobody asked for.
- The typography version of the same tell: **Inter, unchosen, signals nobody made a typography decision** — it's not that Inter is bad, it's that its reflexive use as a default is legible as "no decision was made here," which reads as machine-generated by default. [prg.sh](https://prg.sh/ramblings/Why-Your-AI-Keeps-Building-the-Same-Purple-Gradient-Website)

### Verbal tells (repeated from §3, but this is where they function as *dismissal* triggers, not just annoyance)
- Clustered formal transitions (moreover/furthermore), vague-verb padding (leverage/utilize), hype adjectives (revolutionary/seamless/comprehensive), and "delve" specifically — all read, to a reader already primed to distrust the source, less as "AI helped write this" and more as "nobody who cares wrote this," which is a harder trust deficit to recover from than a factual error.

### Direct design implication for STAR

Given the audience: the two fastest ways to get dismissed before the citations are even read are (1) any hue in the purple/indigo/violet family used as a primary brand or accent color, and (2) marketing-register copy using the hype/hedge vocabulary cluster from §3. The research literature's own vocabulary suggests the opposite design instinct: **look and read like a research tool that happens to use AI, not an AI product that happens to do research** — closer to a citation manager or legal-research interface (dense, evidentiary, click-through-heavy) than to a chat-assistant aesthetic (conversational, gradient-heavy, personality-forward).

---

## Sources index

- [WGA Know Your Rights: Artificial Intelligence](https://www.wga.org/contracts/know-your-rights/artificial-intelligence)
- [ABC News: What's in the tentative WGA deal](https://abcnews.go.com/Business/tentative-wga-deal-proposed-contract-covers-artificial-intelligence/story?id=103525542)
- [Variety: New WGA Contract Explained](https://variety.com/2023/biz/news/wga-new-contract-strike-ai-writers-room-staffs-residuals-1235736648/)
- [Authors Guild: WGA Agreement Introduces Key Protections](https://authorsguild.org/news/wga-agreement-introduces-key-protections-for-tv-and-film-writers-against-ai/)
- [TechCrunch: writers strike over AI](https://techcrunch.com/2023/09/26/writers-strike-over-ai/)
- [Brookings: Five Hollywood writers discuss AI's impact on their careers](https://www.brookings.edu/articles/five-hollywood-writers-discuss-ais-impact-on-their-careers/)
- [CHI 2025 paper (arXiv): Understanding Screenwriters' Practices, Attitudes, and Future Expectations in Human-AI Co-Creation](https://arxiv.org/abs/2502.16153) / [ar5iv full text](https://ar5iv.labs.arxiv.org/html/2502.16153)
- [CJR/Tow Center: AI Search Has a Citation Problem](https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php)
- [Nieman Lab coverage of the Tow Center study](https://www.niemanlab.org/2025/03/ai-search-engines-fail-to-produce-accurate-citations-in-over-60-of-tests-according-to-new-tow-center-study/)
- [Thomson Reuters: CoCounsel Legal trust design](https://legal.thomsonreuters.com/blog/beyond-chatbots-how-cocounsel-legal-delivers-ai-legal-research-you-can-trust/)
- [AI for Lawyers: Trust But Verify](https://aiforlawyers.substack.com/p/trust-but-verify-the-lawyers-guide)
- [Law Firm Brief: Legal AI Hallucination Audit](https://lawfirmbrief.com/ai-hallucination-audit-lexis-westlaw-cocounsel-2026/)
- [LeanLaw: AI Citation Verification Checklist](https://www.leanlaw.co/blog/the-hallucination-problem-a-checklist-for-verifying-ai-generated-legal-citations/)
- [Trusting News: AI research cohort](https://trustingnews.org/trusting-news-artificial-intelligence-ai-research-newsroom-cohort/)
- [Journalist's Resource: what audiences want disclosed](https://journalistsresource.org/media/ai-use-news-what-audiences-disclose/)
- [Lenfest Institute: trust-based AI policies](https://www.lenfestinstitute.org/solutions-resources/news-organizations-are-creating-trust-based-ai-policies-openai/)
- [The Conversation: AI chatbots prioritize flattery over facts](https://theconversation.com/ai-chatbots-can-prioritize-flattery-over-facts-and-that-carries-serious-risks-274298)
- [Science.org: Sycophantic AI decreases prosocial intentions](https://www.science.org/doi/10.1126/science.aec8352)
- [arXiv: Flattering to Deceive — sycophancy and user trust](https://arxiv.org/pdf/2412.02802)
- [TechCrunch: Merriam-Webster names "slop" 2025 Word of the Year](https://techcrunch.com/2025/12/15/merriam-webster-names-slop-the-word-of-the-year/)
- [The Conversation: AI slop is Macquarie's 2025 Word of the Year](https://theconversation.com/ai-slop-is-macquaries-2025-word-of-the-year-i-applaud-the-choice-but-was-bored-by-the-shortlist-270432)
- [Leon Furze: Problem Patterns in AI — Beyond Hallucinations](https://leonfurze.com/2026/07/26/problem-patterns-in-ai-beyond-hallucinations/)
- [Ritner Digital: phrases that give away AI writing](https://www.ritnerdigital.com/blog/the-phrases-that-give-away-ai-writing-and-how-to-edit-them-out-before-they-cost-you-trust)
- [Jim the AI Whisperer: why "delve" is an obvious AI tell](https://jimtheaiwhisperer.substack.com/p/why-delve-is-an-obvious-sign-of-ai)
- [Superdesign: Why AI Design Looks Generic](https://superdesign.dev/blog/why-ai-design-looks-generic)
- [Indie Hackers: The AI Purple Problem](https://www.indiehackers.com/post/the-ai-purple-problem-why-every-ai-brand-looks-the-same-6cb0aa2a02)
- [925 Studios: AI Slop Fonts and Gradients](https://www.925studios.co/blog/ai-slop-design-tells)
- [prg.sh: Why Your AI Keeps Building the Same Purple Gradient Website](https://prg.sh/ramblings/Why-Your-AI-Keeps-Building-the-Same-Purple-Gradient-Website)
- [ResearchGate: Bridging Trust and Transparency — Explainable AI in Clinical Decision Support](https://www.researchgate.net/publication/399883198_Bridging_Trust_and_Transparency_Integrating_Explainable_AI_Models_into_Clinical_Decision_Support_Systems_for_High-Stakes_Medical_Diagnosis)
- [Smashing Magazine: The Psychology of Trust in AI](https://www.smashingmagazine.com/2025/09/psychology-trust-ai-guide-measuring-designing-user-confidence/)
