# Testing the scene-year fix — a prompt to hand an agent

> Paste everything below the line into Claude Desktop with the STAR connector
> attached. **Restart the app first** if it has not been restarted since
> `import_notes` shipped.
>
> **This spends.** Each `sweep_draft` is one slot of an hourly window that
> admits five. The walk below uses **two**, deliberately, and says which claims
> are in each. Do not re-run a sweep to "check" it — the sweep is filed and
> `get_sweep` reads it back for free.

---

You have the STAR MCP connector attached. STAR checks a screenplay's claims
against researched rooms and cites what it finds.

A defect has been fixed twice already, wrongly, and I want you to decide
whether the third attempt worked. **Assume it did not.**

## The defect

A scene headed `NIGHT (1958)` asserted "a Vox AC30 amplifier". The AC30 was
introduced in 1959 — the 1958 amp is the AC15 — so that is an anachronism. The
tool returned `confirmed` twice, on two different builds, and both times **the
note it wrote contained the disproof:**

- *"Vox AC30 valve amplifiers were accessed by British musicians in the late
  1950s."*
- *"Introduced in 1959 by British manufacturer Vox, fitting the 1958–1962 era."*

The second one says 1959 outright and stamps it confirmed anyway. The desk was
comparing the object's date to the ROOM'S ERA (1958-1962) instead of to the
SCENE'S YEAR, because nothing had ever told it what year the scene was.

**The verdict alone hid this twice. The note is where the reasoning is written
down.** So for every claim below: read the note, and say what the desk actually
compared against. A `confirmed` with a sound note and a `confirmed` with "fits
the era" are the same word and different products.

## What was changed

The server now reads a year out of each scene's opening lines, carries it
forward across scenes that state none, and puts every year a claim is asserted
in onto the claim. The desk is told those years outrank the era, that "it fits
the era" is not a verdict, and that a claim asserted in several years must hold
in all of them.

## Sweep 1 — the fixture · SPENDS ONE SLOT

Room `1fd837bdd99e` ("Doctor Who: Liverpool and Hamburg Special"). Call
`sweep_draft` with these three scenes, exactly as written:

```
INT. CASBAH CELLAR - NIGHT (1958)

The cellar is packed. A Vox AC30 amplifier hums in the corner, waiting.

JOHN
Give it here.
```

```
INT. KAISERKELLER - NIGHT (1961)

Hamburg. Louder now. The same Vox AC30 amplifier drives the room.

PAUL
All of it.
```

```
EXT. LIME STREET - NIGHT (1958)

The Liverpool Empire Theatre marquee glows over the street.

GEORGE
That's where the real ones play.
```

**The bar, and all three must hold:**

1. **`Vox AC30 amplifier` must NOT come back `confirmed`.** It is asserted in
   1958 and in 1961 and it fails in 1958, so the whole claim fails.
   `anachronism` is the right answer. `unverifiable` is acceptable and honest.
   **`confirmed` is a failure however good the note is.**
2. **The note must name the year that breaks it** — something of the shape
   "correct from 1959, so wrong in the 1958 scene". A note that only says
   "introduced in 1959" leaves the reader to do the arithmetic the tool exists
   to do.
3. **`Liverpool Empire Theatre` must still come back `confirmed`**, on the
   room's files, with `search_count` at 0 for it. If the fix has made
   everything unverifiable it has not learned anything, it has stopped
   answering.

**Also report:** whether any note still reasons from the era — "fits the
1958-1962 era", "key year within the era", "opening year of the story era".
That phrasing is the exact failure and it should be gone.

## Sweep 2 — the traps · SPENDS ONE SLOT

Same room. Four scenes:

```
INT. FRONT PARLOUR - NIGHT (1958)

A transistor radio plays. Tea goes cold.

MIMI
Turn that down.
```

```
INT. BACK BEDROOM - NIGHT

A Fender Stratocaster leans against the wall.

JOHN
Someday.
```

```
INT. PUB - NIGHT

They drink.

PAUL
My dad was born in 1931. He'd have hated this.
```

```
INT. ROOM 402 - DAY

He counts out 1200 in notes and pushes it across.
```

**What each one is for:**

- **Scene 2 states no year.** It should inherit 1958 from scene 1, because a
  screenplay says its year once. The Stratocaster (1954) should confirm; a
  claim that would be wrong in 1958 should fail. **Report whether the verdicts
  behave as though scene 2 is 1958 or as though it has no date at all.**
- **Scene 3's "1931" is dialogue about a year, not the scene's year.** If
  anything in the results reads as though scene 3 is set in 1931, the year
  parser is reading too far down the page.
- **Scene 4 has "402" and "1200" and no year.** Neither is a date. If either
  becomes one, the parser's range is too wide.

## What to report

1. **Anything spent or written beyond the two sweeps.** First, even if empty.
2. **Claim by claim for sweep 1**, with the exact verdict AND the exact note.
   Say for each what the desk compared against.
3. **Pass or fail on the three bars**, plainly. Do not soften a `confirmed` on
   the AC30 into "close" — it is the whole test.
4. **The traps**, and what the results say about the year each scene was
   treated as.
5. **Any note that still reasons from the era.**
6. **What you would try next** if you wanted to break it and had one more slot.

Do not summarize as "working well". Give me the verdicts and the notes.
