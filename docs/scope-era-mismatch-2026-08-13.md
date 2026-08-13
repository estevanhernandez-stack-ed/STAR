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
