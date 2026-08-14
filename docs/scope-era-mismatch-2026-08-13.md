# The date-range defect — scope

> The remaining two thirds of D1, found by the agent-door walk. The import
> laundering path is shut as of `star-00059-ft4`; this is the one that survives
> in a **fully researched** room, honestly, with real sources under it.

## What actually happens

A scene headed `NIGHT (1958)` contained "a Vox AC30 amplifier." The AC30 shipped
late 1959 into 1960; the 1958 amp is the AC15. The sweep returned:

```
verdict: confirmed
note:    "Vox AC30 valve amplifiers were accessed by British musicians
          in the late 1950s."
citation_sources: ["room"]
```

Three failures stacked. Only the third was about importing, and only the third
is fixed:

1. **The build filed a finding smeared across a range.** The room's era is
   `1958-1962`, and findings are written to the era rather than to a year. A
   finding true *somewhere* in 1958-1962 reads as true *throughout* it.
2. **The verifier accepted range-membership as a match.** The scene says 1958,
   the finding covers 1958-1960, they overlap, so it confirmed.
3. **Imported findings satisfied "work the room's files first"**, so no search
   ran to catch either of the above. — *fixed 2026-08-13.*

## The root, and it is smaller than the symptom

**The verifier is never told what year the scene is.**

`star/agents/script_check.py`'s prompt judges whether a claim holds "for this
story's era and place" — and `check_state` passes exactly three things:

```python
{"scene": scene, "room_files": room_files, "search_budget": ...}
```

No era. The term the whole standard rests on is never defined for the desk that
applies it. So the verifier infers the year from whatever it can see: the
slugline if the writer wrote one, and the dates inside the room's own findings.
When those disagree, nothing arbitrates, and the widest date in view wins —
because a range that *contains* the scene's year is the easiest thing to call a
match.

**The room has always known.** `story_profile.era` is on every room document,
returned by `list_rooms`, printed on the docket, and stamped on every export.
It reaches the researchers at build time. It does not reach the verifier.

`_room_files` does not carry it either: that function prints category headings
and `fact :: url` lines, and nothing else.

## The seam

Two verification paths, two state builders, one shared file assembler:

| path | state built by | called from |
|---|---|---|
| one scene | `script_check.check_state` | `server.py:1997` |
| whole draft | `agent_sweep.verify_state` | `server.py:2384` (`_verify_claims`) |

Both are handed `room_files` out of `_chain_files`. **Any fix that lands in one
and not the other splits the product's two most visible surfaces**, which is
the mistake `_file_notes` was extracted to stop repeating.

A chain complicates it: `_chain_documents` returns several rooms, each with its
own `story_profile.era`. A Liverpool room and a Hamburg room can legitimately
carry different ones, so "the era" is not a single value at the point the files
are assembled.

## Options

### A. Pass the era, add a rule. *(recommended)*

`_chain_files` writes each room's era above its findings, the same way the
provenance banner now sits above an imported room's. `check_state` and
`verify_state` both take an `era` and put it in the prompt. The verifier gets
one added standard:

> A range in a finding is not a date for the scene. If the scene names a year
> and the finding names a span, the claim holds only if the thing was true in
> *that year* — not somewhere in the span. If you cannot tell which, search. If
> the search does not settle it, the verdict is `unverifiable` and the note
> says the source gave a range where the scene needs a year.

- **Cost:** two state builders, one file-assembler line, one prompt paragraph.
- **Validates with:** one live sweep of the AC30 scene.
- **Risk:** more `unverifiable` verdicts. That is the correct direction for a
  product whose pitch is receipts, and it is the same trade the citation fix
  already made.

### B. Have the extractor stamp each claim with the scene's year.

Cleaner in principle — the year belongs to the claim, not the room — and it
handles a draft whose scenes span years, which the era cannot. But it changes
the claim record's shape, which the CSV export, the import matcher, the scene
strip and `apply_annotations` all read. **Too wide for the time left.** Worth
doing after Sep 7.

### C. Make the researchers write findings to a year rather than an era.

Attacks failure 1 at its source and is the most correct of the three. It also
means re-running builds to see any effect, cannot fix the rooms already filed,
and costs a full build to validate rather than one sweep. **Not before the
deadline.**

## Recommendation

**A now, B after the hackathon.** A is one prompt paragraph and two call sites,
it is validated by a single sweep, and it closes the demo-visible half. B is
the right architecture and needs a week nobody has this month.

## What A does not fix, stated plainly

A teaches the verifier to *distrust* a range against a year. It does not make
the room's findings any more precise, so a claim that only a range can answer
still comes back `unverifiable` rather than correct. **That is the honest
outcome and it will make the sweep look worse** — more unverifiables, fewer
confirmations. The same trade was made on the citation fix and it was right
then.

## Validation

One live sweep, on a scene built for it:

- `NIGHT (1958)` with a **Vox AC30** — must not come back `confirmed`.
  Anachronism is the ideal answer; `unverifiable` naming the range-for-a-year
  problem is acceptable and honest.
- The same scene at `NIGHT (1961)` — the AC30 **should** confirm. A fix that
  refuses both has not learned anything, it has just stopped answering.
- One claim the room settles cleanly and unambiguously — must still confirm on
  the files with no search spent, or A has broken the thing that makes a room
  worth building.

Three claims, one sweep, one slot of the hourly window.

---

# The validation ran. Option A failed, and the failure names the real root.

Sweep `2ba53f31dab2`, live on `star-00061-wpw`, against the **researched** room
`1fd837bdd99e`. Three scenes, 8 claims raised, 7 distinct, **7 confirmed, 0
anachronism, 0 unverifiable, 0 searches spent.**

## The result, verbatim

```
text:    "Vox AC30 amplifier"
verdict: confirmed
note:    "Introduced in 1959 by Vox as a higher-wattage valve combo amplifier."
scenes:  [1, 2]
```

Scene 1 is headed `NIGHT (1958)`. Scene 2 is `NIGHT (1961)`.

**The desk found the right fact and cited the right page.** Its own note says
1959. The source it pulled even carries the sentence "In early 1958, JMI
released its first-ever guitar amplifier, the EL84-powered Vox AC15." It had
everything it needed and stamped `confirmed` anyway.

## Why Option A could not have worked

`star/sweep.py`'s `gather` collapses claims to a distinct set and hands back a
map from each claim to **every scene index it appeared in**. One claim, one
verdict, many scenes. So "Vox AC30 amplifier" in a 1958 scene and a 1961 scene
is **one claim with one stamp**, and there is no shape in the data for
"anachronism in scene 1, confirmed in scene 2."

`sweep_draft`'s own description says:

> It also catches what no number of scene checks can: an object that is right
> in 1958 and wrong in 1960 is wrong in neither scene alone.

**That is the tool's headline argument for itself, and its data model cannot
express it.** The claim it describes is exactly the one this sweep got wrong.

The era I passed is the STORY's span, not the SCENE's year, and
`verify_state`'s docstring says plainly that the verifier "is told nothing
about scenes and should not be". So the span rule never fired: the desk was
never shown a conflict, because from where it sits there is no scene 1 — only
a claim that appears somewhere in a story running 1958 to 1962.

## And it gave the rubber stamp new words

Two claims came back confirmed *on the era itself*:

- `"1961"` — *"Key year within the 1958–1962 era…"*
- `"1958"` — *"Opening year of the 1958–1962 story era."*

The era arrived as a **justification** rather than a **constraint**. That
pattern predates this change (an earlier sweep confirmed `"1960"` with the note
"Year setting"), but handing the desk the span gave it a cleaner sentence for
doing the same thing.

## The real root, and the real fix

**The dedup key is the defect.** `gather` keys on normalised claim text alone.
Two scenes in different years asserting the same object are one claim.

The fix is to make the year part of the identity:

1. **Parse a year per scene.** Nothing does this today. A slugline year
   (`NIGHT (1958)`) is the cheap case; a draft that never writes one falls back
   to the room's era, which is what the desk already had.
2. **Key the dedup on `(claim text, scene year)`** when the years differ. The
   AC30 then arrives as two claims and can take two verdicts.
3. **Tell the verifier the year for the claim it is judging**, which is only
   possible once (2) makes "the year" a single value per claim.

Then the span rule already shipped becomes reachable, and the tool's headline
argument becomes true.

## What this costs

Bigger than Option A and smaller than Option B. It touches `star/sweep.py`'s
`gather`, the scene splitter that would supply the year, and the claim record —
which the CSV export, the import matcher and the scene strip all read, because
a claim that now carries a year has a new column.

**Validated by the same three-claim sweep**, which is now a fixture rather than
a guess: AC30 in 1958 must not confirm, AC30 in 1961 must, and the Liverpool
Empire must still confirm on the files with no search.

## Standing state, honestly

- Import laundering: **shut** (`star-00059`).
- The import brand on `get_room`: **shut** (`star-00060`).
- Era reaching the desk and the span rule: **shipped** (`star-00061`), and it
  does not fix the case it was built for.
- The AC30 in a 1958 scene: **still confirms.** A demo that sweeps a draft
  spanning years can still show a wrong green stamp.

---

# The decisive experiment: it is not the dedup, and the era made it worse

Sweep `0b65b4d842a1`. **One scene**, one claim, no dedup possible.

```
text:    "Vox AC30 amplifier"
verdict: confirmed
note:    "Introduced in 1959 by British manufacturer Vox, fitting the 1958–1962 era."
scenes:  [1]
```

Scene 1 is headed `NIGHT (1958)`.

## What the note proves

The desk's reasoning is written down in its own words: the AC30 is **1959**,
the era is **1958-1962**, 1959 is inside it, therefore confirmed. **It compared
the object's date to the ERA and never to the SCENE'S YEAR.** The slugline says
1958 and played no part.

So the previous diagnosis was wrong. The dedup collapse is real and still worth
fixing, but it is **not** what produces the wrong verdict — a single scene with
nothing to collapse produces it too.

## And the era I shipped today is the instrument

Three sweeps, three notes, all reasoning from the span:

- `"1961"` — *"Key year within the 1958–1962 era…"*
- `"1958"` — *"Opening year of the 1958–1962 story era."*
- `"Vox AC30 amplifier"` — *"…fitting the 1958–1962 era."*

Option A handed the desk the **widest window in the building** and it did the
obvious thing with it: checked membership. That is the exact error the span
rule in the same prompt forbids, committed using the span that same change
supplied. The rule did not fire because nothing looked like a conflict — the
desk was not comparing a span to a year, it was comparing a year to a span and
finding it fit.

**This is worse than neutral and I should say so plainly: the change gave a
pre-existing rubber stamp a better justification.** The pattern predates it —
an earlier sweep confirmed `"1960"` with the note "Year setting" — but the era
turned a vague stamp into a reasoned one.

## The real fix, and it is narrower than either earlier option

**The desk needs the scene's year, and the era needs demoting.**

The server already holds every scene's text at the point it matters.
`server.py`'s `one(scene)` reads `scene["text"]` and `scene["index"]` and
throws the text away after extraction. **Nothing in the codebase parses a year
from a scene** — checked.

1. **`sweep.scene_year(text)`** — pure Python, no model call. A four-digit year
   from the slugline first, then the scene's opening lines. Absent, inherit the
   previous scene's: drafts state a year once and carry it, which is what a
   human reader does.
2. **`one()` returns `(index, year, claims)`**, and `gather` keys on
   `(normalised text, year)`. The AC30 in 1958 and in 1961 become two claims
   and can take two verdicts — which is what `sweep_draft`'s headline argument
   promises and its data model currently forbids.
3. **The claim carries its year into `<claims>`**, so the desk compares against
   a year rather than a span.
4. **Demote the era in the prompt.** It bounds the story; it is never a licence
   for a scene. As it stands it is the widest date in the room and the desk
   reaches for it.

**I was wrong in the scope above when I called the year approach "too wide for
the time left."** That was true of stamping the year in the extractor's schema.
It is not true of parsing it server-side from text already in hand: it touches
`star/sweep.py`, one call site, and the prompt. No model schema change, no
export column, no import change.

## Until that ships

The live service reasons from the era. **The safest interim state is not the
one deployed** — either the era comes back out, or the prompt says outright
that an era is never evidence for a scene's year. The second is one paragraph
and keeps the plumbing the real fix needs.

Validated by the same three-claim fixture, which is now a regression test
rather than a guess.

---

# The knife: the years are computed and not used

Sweep `36246040498d` on `star-00063-ch8`. Four scenes, three probes.

| claim | scene | year computed | desk judged against | |
|---|---|---|---|---|
| `Vox AC30 amplifier` | 2 (inherited) | 1958 | 1958 | anachronism |
| `Fender Jazz Bass` | 3 (deep SUPER) | **1962** | **1958** | anachronism |
| `Gibson SG` | 4 (montage span) | 1958 | 1958 | anachronism |

**Scene 3 is 1962 and every one of its three claims reasoned from 1958:**

- `Fender Jazz Bass` — *"introduced in 1960 and did not exist in 1958"*
- `container` — *"used in maritime transport by 1958"*
- `Hamburg, 1962.` — *"anachronistic in a scene set in 1958"*

Verified rather than assumed: `_head` is in the deployed commit, `star-00063-ch8`
built it, and the exact string that went over the wire parses to `1962` —
`scene_years` returns `{1: '1958', 2: '1958', 3: '1962', 4: '1958'}`.

## Which makes the two passes worthless as evidence

**1958 is also the era's opening year.** Every result in this sweep is
consistent with the desk defaulting to the era's start and never reading a
claim's `years` at all. The AC30 and the SG "passed" because their scenes
happen to be 1958.

Probe 2 is the only one where the scene's year and the era's start differ, and
it is the one that failed. **So the fix is unproven at best and inert at
worst**, and the earlier fixture result — the AC30 coming back anachronism —
proves nothing either, for the same reason.

That is three attempts at this defect where the evidence looked like success
and did not distinguish the fix from a coincidence. **Every future test of this
must put the scene's year somewhere other than the era's first year.**

## And the extractor rule did not take

`"Hamburg, 1962."` — the text of a SUPER — was extracted as a geography claim
and stamped an anachronism. The rule shipped hours earlier says a year in a
slugline, in a SUPER or in an establishing line is the writer saying WHEN, and
must not be extracted. It was extracted anyway.

## What to establish before writing another line of fix

The next thing to find out is not a fix, it is a fact: **does a claim's `years`
reach the rendered prompt at all?** `gather` puts the key on the dict, and
whether ADK's `{claims}` renders it is unverified. If it does not, every prompt
rule written about `years` has been addressed to a field the desk cannot see,
and the three sentences added to the verifier are unreachable code.

That is a free thing to determine and it decides everything after it. No more
sweeps until it is answered.
