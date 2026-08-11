# STAR copy audit — what "robotic" turned out to be

**Date:** 2026-08-11
**Scope:** the app proper. `web/consent.js` and `web/consent.html` deliberately excluded.
**Measured against:** `docs/superpowers/specs/2026-08-10-star-design-language.md`, copy rules 1-11
**Result:** 28 raw findings from two lenses, deduped to 23, adversarially verified. **2 confirmed, 21 refuted.**

## Why this audit happened

The builder read the shipped copy and said much of it "feels robotic and forced
for a hackathon." The stage-1 audit had not caught it and structurally could
not: rule 9 measures *cadence* (a thing said too often) and rule 8 measures
*flattery*. Neither measures whether an institutional voice is landing as an
instrument or as a machine. So rule 11 was written — a note earns its sentence,
or it becomes a mark — and two lenses ran against it: one applying the rule
mechanically with a verb test, one reading the captures cold as the hostile
screenwriter the aversion research describes.

## The result, and what it means

**Two findings survived out of 23.** That is not a vindication of the copy and
it is not a failure of the reader. It is a finding in its own right, and the
refutations all say the same thing in different words.

Read them together and one sentence covers nearly all of them: **the cut loses
something the shorter form cannot carry.** An actor (the search, not the
department; this researcher, not the department). A scope (this drawer, not this
room; one ledger, not two). A consequence weighed before an irreversible press.
An obligation DIRECTION.md requires in words. A pronoun's antecedent. A
distinction a commit was written to introduce.

Twenty-one times, in a row, against two independent lenses.

**So the copy is not padded. It is the opposite: there is no slack in it at
all.** Every sentence is minimum-viable for the obligation it carries. That is
the mechanism behind the measurement this audit opened with — 1,143 words,
median sentence 14, mean 13.9, a band tight enough that nothing carries
emphasis. The band is tight because every sentence is doing exactly one job and
stopping.

Prose written by a person has slack in it. Some sentences exist only to make the
next one land, or to give the reader somewhere to breathe before a hard fact.
This corpus has none, because every string was written to discharge a specific
obligation and was then defended, on the record, by a comment, a commit, or a
test. That discipline is why the app is trustworthy. It is also, precisely, why
it reads as machine-made.

**The instrument was wrong, and that is worth recording.** Rule 11 asks "could
this be a mark?" and the honest answer, 21 times, was no — because marks carry
facts and these strings carry facts *plus actors plus scopes*. A rule aimed at
subtraction cannot find a problem whose cause is that nothing can be subtracted.

## What actually shipped as a finding

**C-06 — a real grammar error, in the app's first paragraph.** `index.html:105`:
"Era, place, and what your characters actually do **is** what turns a guess into
a grounded fact." A compound subject with a singular verb, on the first screen.

The conflict the lenses had over this string resolved cleanly. One wanted the
sentence rewritten; the other refused to touch it because it is the only place
in `web/` that says **"grounded"** — verified, one occurrence — a word the
practice research says three unrelated interviews reached for unprompted, and
which the phase-3 plan binds to this exact string. The skeptic wrote the version
that satisfies both:

> "A logline works; a paragraph works better. Era, place, and what your
> characters actually do: that is what turns a guess into a grounded fact."

Severity 2, visibility 5. Recasting the list as a plate fixes the agreement and
keeps every word.

**C-07 — the four drawer remits are plates written as prose.** `index.html:130,
134, 138, 142`. Rule 11's own worked example, and the render bears it out: four
serif body-face sentences, each wrapping to two lines, hanging off tracked-caps
plate tabs under a tracked-caps heading. `:130` has no finite verb at all, which
is the terminal case of the verb test — the words are already plate words and
only the face, the sentence case and the terminal period make it read as prose.

Severity 3, visibility 4. **Two corrections to the finding as filed**, both
material:

- Lens A claimed `_CATEGORY_BRIEFS` in `star/agents/researchers.py` are already
  verbless plates and the interface added verbs. False for three of four —
  OBJECTS_PROPS, LOGISTICS and FORCES_CONFLICTS all carry finite verbs the
  interface *inherited*. And they are LLM prompt fragments interpolated into
  "You are a film-studio researcher specializing in {brief}", so they must be
  noun phrases to be grammatical. Treating a prompt string as a design mark is a
  category error.
- The fix is therefore **not** string-only. Delivering the plate treatment means
  moving `.plate-remit` from `var(--body)`/`--text-sm` at 0.85 opacity to the
  mark treatment `.plate-label` uses, which moves a measured colour pair and
  must restate the ratio under invariant 5.

## A real bug the audit found by accident

Neither lens filed it. C-09's skeptic found it while refuting C-09.

`web/scriptcheck.js:404` hardcodes a singular verb: at two or more the app ships
**"2 cited links in this check *was* in neither the room's files nor this
check's own search results."** `tests/js/test_scriptcheck.mjs:499-515` runs that
exact payload and misses it, because it asserts only the substring "2 cited
links".

The sibling at `clip.js:391` avoids the problem by using a number-agnostic verb
("never appeared"). Fix `:404` to match, and tighten the test's assertion.

## What was refuted, grouped by why

**The cut drops an actor or a scope (7).** `No excerpt returned.` loses "the
search" for an agentless passive, in an app whose identity statement is "who
found it, where, and when". The two unsourced strings are not two wordings of
one obligation — one is a one-ledger fact, the other a two-ledger fact, each
canonical to its own backend. The failed-drawer lines name a department or a
researcher, a category or a room, where the mark names neither.

**The cut breaks something structural (4).** Removing "Paste a scene." leaves
"the claims **it** makes about the world" binding to the department, asserting
the exact thing `VERDICT_SCOPE` exists to deny. Removing the interrupted
branch's second clause deletes the payload-proven fact a defect-repair commit
was written to introduce.

**The finding contradicted its own document (4).** Eleven of C-01's eighteen
citations sit on the audit's own do-not-resurrect list. C-01's fix rewrites the
string Lens A named the register's model. C-09 proposed cutting half of a line
Lens A had refused.

**The arithmetic did not hold (3).** C-01's headline: 18 citations not 19, 8 of
them mutually exclusive branch alternates, 3 not the figure — a real count of 9,
across surfaces that never co-render. Its causal claim was inverted: the figure
ranges 5 to 38 words, removing every instance moves the corpus mean from 13.90
to 13.64, and the two shortest sentences in the whole corpus *are* the figure.

**A test or a requirement pins it (3).** C-11's replacement fails
`test_intake_silence.mjs` twice. C-13's fails two assertions in
`test_account_card.mjs`. C-23's fails the regex in `test_token_retention.mjs` —
written three hours earlier, in wave 1 of this same campaign.

**It duplicates an existing finding (2).** C-15 is F-014 seen from the copy
side. C-03's rail-ordering half re-litigates F-002.

**The mechanism was misread (2).** `VERDICT_SCOPE` is `rail-caveat` at 0.85
opacity rendering *fifth*, below the fact — not `rail-line` above it. "Below" is
correct at ≤900px where the rail becomes a top bar, and at 1440x900 the field is
both right of the rail *and* 118px lower.

## Where the copy earns it

Lens B was required to name what works, because a pass that finds only faults is
a mood rather than a reading. Recorded so no later round "fixes" them:

The stamp slug (`clip.js:206-208`) — verbless, falsifiable, three facts in nine
characters each, and `buildFiledHead` refuses to fill a slot it cannot support.
**"issued" rather than "completed"** (`drawer.js:187`) — the event fires on the
tool *call*, so "completed" would have been a small lie. **"Did not file"**
(`drawer.js:379`) — three words where every product instinct says "Something
went wrong." **The rooms-unreachable split** (`shell.js:131`) — "you have no
rooms" and "we could not read the list" were once one string; separating two
opposite facts is the calibrated confidence the aversion research says the whole
category fails at. **"Put it away"** (`account.js:164`) — declines to say "I
have saved it" on the reader's behalf. **"What the department could not do
cleanly"** (`clip.js:398`) — unhedged, and positioned *before* the findings.

## The honest conclusion

If the copy still reads as forced, the lever is not the strings. Twenty-one
attempts to shorten them failed on the merits, most against the codebase's own
recorded arguments.

Three directions remain, and none is a copy edit:

1. **Structural.** Change where obligations discharge — fewer surfaces carrying
   the same duty — rather than how each is worded. This is a design change to
   the app's information architecture, not a rewrite.
2. **Additive.** Give the prose slack: a short sentence that carries no
   obligation, placed for rhythm. This runs against the file-level discipline
   that every string earn its place, and should be proposed as an amendment to
   that discipline rather than smuggled in.
3. **Accept it.** An evidence-first institutional register, with every sentence
   minimum-viable for its obligation, reads tight. The alternative registers —
   warm, apologetic, discursive — are the ones DIRECTION.md's research says a
   hostile audience distrusts.

Rule 11 stays in the measuring stick. It found C-07 and it is the right question
for a note that is genuinely a label. It is recorded here as the wrong
instrument for *this* complaint.
