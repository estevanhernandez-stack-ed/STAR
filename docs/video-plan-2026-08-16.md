# The submission video — script, shot list, and what could go wrong

**Cap:** 3:00. **Story:** *The Beat That Shook The Void*, Este's own work.
**Runs:** live. **Compression:** real elapsed time on screen, playback sped up.
**The line, said once and not repeated:** the receipt is the product.

## The hard constraints the shoot has to respect

| | |
|---|---|
| Build ceiling | 600s timeout, 30 searches. Real builds have taken **3–5 minutes**. |
| Sweep ceiling | 300s timeout, 30 searches. The 31-piece book sweep fit inside it. |
| **Builds per IP per hour** | **5.** This is the production hazard, not the build time. |
| Checks and sweeps per hour | 5, same window, separate key |

**Five builds an hour is the whole risk.** Four rehearsal builds and the take is
a locked-out demo. Rehearse against rooms that already exist; spend only on the
take.

**Do not deploy on shoot day.** A deploy kills a build in flight and resets the
hourly counters — the second is harmless, the first ends a take mid-shot.

## The three minutes

### 0:00–0:20 — The problem, on the page

Open on the draft, not the app. A paragraph of *The Beat That Shook The Void*
with the Casbah in it.

> Every studio has a research department. A writer working alone gets one chance
> to notice that the club in this scene opened a year after the scene is set.

Cut to STAR's intake.

### 0:20–1:00 — Build the room, live, compressed

Paste the treatment. Press build. **Four researchers run in parallel and the
rail fills over SSE** — setting, objects and props, logistics, forces and
conflicts.

- **On-screen counter runs in real time** while playback is sped up. The number
  climbing toward four minutes is the point: this is real research, and it costs.
- Searches appear with **the actual query strings** that went to Parallel, not a
  spinner. Hold on one for a beat.

> Four researchers, live web search, about four minutes. Every finding it files
> comes back with the page it came from.

### 1:00–1:20 — The receipt. Say it once.

Open one drawer. One finding. Its source: domain, retrieval date, and the
search's own excerpt.

> Nothing here says "verified." It says what was checked, and what it could not
> settle.

**Then move on.** Do not restate it. The rest of the video demonstrates it.

### 1:20–1:50 — The whole book, one pass

Paste the draft. **31 scenes.** Sweep.

> Eight chapters, twenty-three thousand words, one request. Scene by scene this
> would be thirty-one search budgets. It is one.

Counter again, compressed. Land on the result: **75 claims, 34 confirmed, 33
anachronisms** (sweep `92d9c15c8ef5`, 2026-08-17).

### 1:50–2:35 — The catch. This is the video.

Two beats, in this order. Small first, structural second.

**Beat one, the one-liner.** `"turning it up to eleven"`, in a 1959 scene.

> That phrase comes from a film made in 1984. Two rows down, "Got blisters on
> your fingers" — Ringo said that in 1968, on Helter Skelter. Neither is a date
> anybody could be expected to hold in their head.

No arithmetic on screen, and nothing the viewer has to take on trust: both are
one-line jokes a reader either knows or doesn't, which is the point.

**DO NOT USE the old `"He was seventeen."` row.** It was a false positive and
the 2026-08-14 sweep is wrong about it. The desk read "he" as George Harrison;
scene 1 puts George at "fourteen and a half" in the same paragraph and John at
seventeen, and scene 8 is the Doctor talking about Lennon. Both are John, and
John WAS seventeen in 1958. The draft was right and the department was wrong.
The 2026-08-17 sweep confirms it correctly — which is a fix worth knowing about
and not a shot worth filming.

**Beat two, the cluster.** Filter to the Casbah rows.

> The Casbah opened in August 1959. So did Mona Best's coal cellar under it, its
> espresso machine, the spider painted on its wall and the rainbow on its
> ceiling. Six flags, one afternoon — and the Kaiserkeller, the Indra and the
> Top Ten behind them, across most of the thirty-one scenes, all tracing to a
> single decision about when this story happens.

Then the honest close on it, which is the strongest thing in the video:

> It does not tell you that is wrong. It is a Doctor Who story about a stolen
> chord — the timeline might be broken on purpose. It tells you a reader will
> notice, in twenty-two of the thirty-one scenes. What you do about it is the
> writer's business.

### 2:35–2:50 — The same department, no browser

Cut to a desktop agent. `list_rooms`, then `defend_claim` on the Casbah.

> Fifteen tools over MCP. Same rooms, same receipts, no browser — and the ones
> that spend money say so before they spend it.

### 2:50–3:00 — Close

Back to the page, the flagged line visible.

> Every studio has a research department. Now every writer has one, and so does
> every agent they run.

## Shot list

| # | Shot | Source | Live? |
|---|---|---|---|
| 1 | Draft paragraph, Casbah visible | the `.md` in an editor | no |
| 2 | Intake, treatment pasted | browser | no |
| 3 | Build rail filling, four researchers | browser + SSE | **yes** |
| 4 | Search event, real query strings | browser | yes, same take |
| 5 | One drawer, one finding, its source | browser | no |
| 6 | Draft pasted, 31 scenes listed | browser | no |
| 7 | Sweep running, counter | browser | **yes** |
| 8 | Result header: 75 / 34 / 33 | browser | no |
| 9 | `"turning it up to eleven"` and its note | browser | no |
| 10 | Casbah rows filtered | browser or the CSV | no |
| 11 | Agent calling `defend_claim` | desktop agent | no |
| 12 | Draft again, line flagged | editor | no |

**Two live shots, 3 and 7.** Everything else can be captured off a filed room
and re-shot freely.

## Timeline, back from Sep 5

| When | What |
|---|---|
| **Aug 24** | Re-plotted from here; the original Aug 22 shoot passed unused. Free prep only: the 133,884-character paste rehearsal, pick and hand-check shot 5's finding, tidy the sweep list. |
| **Aug 25** | Capture every shot that does not need a live run, off the existing room and sweep `92d9c15c8ef5`. No spending. |
| **Aug 26** | **Shoot day.** One live build, one live sweep. Nothing deployed for 24 hours either side. |
| **Aug 27–31** | Edit. Time-lapse passes, counter overlays, voiceover. |
| **Sep 1** | Watch it cold. One pass of notes. |
| **Sep 2–3** | Fixes. Re-shoot any single shot — the hourly window has reset many times by then. |
| **Sep 4** | Buffer. Do not touch the code. |
| **Sep 5** | Submit. Deadline is Sep 7, 2:00 PM PT. |

**This is the second timeline.** The first ran Aug 17–22 and the shoot date went
by while the citation defect and the Vertex move were still landing. Both were
worth the slip: the row shot 9 was built on turned out to be a false positive,
and it would have been filmed. Twelve days of runway remain, which is more slack
than the original plan ever had.

## What could go wrong on camera, and what to do

- **The build fails or times out.** It now recovers as `partial` with whatever
  was checkpointed. A real recovery story, but not one to demo — cut and re-run.
  You have five an hour.
- **The sweep dies with the tab.** It is a synchronous request. **Do not switch
  tabs, close the lid, or let the machine sleep during shot 7.**
- **A confirmed SWEEP row cites the wrong page.** Measured at 7 of 34 confirmed
  rows (21%) on the 2026-08-17 sweep (re-counted 2026-08-24 directly against
  `shares_claim_wording=false` in Firestore; an earlier pass said 6), down from
  21 of 42 (50%). Each of those
  now carries a caveat under the excerpt saying the page repeats no word of the
  claim. That is a shot 9/10 asset, not a liability: a desk marking its own thin
  receipts is the thesis rather than a failure of it.
- **Shot 5 is a different surface and carries no caveat.** It opens a ROOM
  FINDING drawer, and `shares_claim_wording` is set only on the script-check
  path (`star/verdicts.py`); `cite-unmatched` renders only in
  `web/scriptcheck.js`. Room findings were never measured and show no flag, so
  **hand-check whichever finding gets filmed** — read the excerpt against the
  fact. An earlier revision of this file claimed shot 5 could show a caveated
  row. It cannot.
- **A search comes back thin.** Live web results vary. Shot 4 holds on whatever
  arrives — the query strings are the point, not the answers.
- **Worth doing once, not on camera:** the first build after a deploy creates
  `/service/daily_cap`. Free to check, and it confirms the cap now survives.

## Decided, 2026-08-16

**Shot 7 uses the Fountain conversion in the browser**, not the agent door. The
browser is the better shot and it is the surface a writer would actually use.

The file is committed to the book repo, not left in a scratchpad — a session
temp directory does not survive to Aug 22:

    Projects\doctor-whom\02_SHORT_STORIES\The Beat That Shook The Void\
      The_Beat_That_Shook_The_Void.fountain

Regenerate it any time with `python writer-studio/to_fountain.py` from the book
repo. It reads the markdown draft, cuts at the story's own `---` breaks, never
splits a paragraph, and **fails loudly if any piece exceeds STAR's 8,000-char
ceiling** rather than producing a file that dies on paste.

Verified through STAR's own `web/fountain.js`, not a grep: **31 scenes, largest
7,731.**

**One rehearsal item this creates.** Pasting 133,884 characters into the draft
box is the only thing in the shoot nobody has watched happen. Do it once during
the Aug 17–20 window — it costs nothing, splitting is client-side — and find out
whether it looks instant or looks like a hang. If it hangs, the shot cuts from
"paste" to "31 scenes listed" and nobody is any the wiser.

**REHEARSED 2026-08-24, against the live revision.** The full 133,884-character
draft through the real `#scene` input handler: splitter + strip render 7.9ms,
layout and paint 37.5ms with the panel visible. Under 50ms end to end — the
paste looks instant, the strip announces "This looks like a screenplay — 31
scenes," and picking a scene loads it in 0.5ms with the list surviving the
pick. The shot stands as written; no cut-around needed. (Driven via Playwright
with a programmatic value-set + `input` dispatch, which is the same handler
path a native paste takes; worth one native confirm in Este's own session on
capture day.)

**The treatment is unchanged.** The existing Beat That Shook The Void treatment
is what gets pasted in shot 2.

## The one thing to protect

**The catch at 1:50 is the video.** Everything before it is setup and everything
after it is a coda. If the edit runs long, cut the agent-door beat to five
seconds and the build to twenty — never the catch.
