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

Counter again, compressed. Land on the result: **78 claims, 42 confirmed, 26
anachronisms.**

### 1:50–2:35 — The catch. This is the video.

Two beats, in this order. Small first, structural second.

**Beat one, the arithmetic.** The `"He was seventeen."` row.

> George Harrison was fifteen in 1958. The desk knows what year the scene is set
> in, because it read it off the page — and it caught the same line again forty
> pages later, against a different year, where he was sixteen.

**Beat two, the cluster.** Filter to the Casbah rows.

> The Casbah opened in August 1959. So did its espresso machine, the spider
> painted on its wall and the rainbow on its ceiling. Four flags, one afternoon
> — and eleven more across eighteen of the thirty-one scenes, all tracing to a
> single decision about when this story happens.

Then the honest close on it, which is the strongest thing in the video:

> It does not tell you that is wrong. It is a Doctor Who story about a stolen
> chord — the timeline might be broken on purpose. It tells you a reader will
> notice, in eighteen places. What you do about it is the writer's business.

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
| 8 | Result header: 78 / 42 / 26 | browser | no |
| 9 | The `"He was seventeen."` row and its note | browser | no |
| 10 | Casbah rows filtered | browser or the CSV | no |
| 11 | Agent calling `defend_claim` | desktop agent | no |
| 12 | Draft again, line flagged | editor | no |

**Two live shots, 3 and 7.** Everything else can be captured off a filed room
and re-shot freely.

## Timeline, back from Sep 5

| When | What |
|---|---|
| **Aug 17–20** | Rehearse the browser path against the *existing* rooms. No spending. Settle wording. |
| **Aug 21** | Delete the Beat rooms. Capture the shots that do not need the live run. |
| **Aug 22** | **Shoot day.** One build, one sweep, both live. Nothing deployed for 24 hours either side. |
| **Aug 23–27** | Edit. Time-lapse passes, counter overlays, voiceover. |
| **Aug 28** | Watch it cold. One pass of notes. |
| **Aug 29–31** | Fixes. Re-shoot any single shot if needed — the hourly window has reset many times by then. |
| **Sep 1–4** | Buffer. Do not touch the code. |
| **Sep 5** | Submit. Deadline is Sep 7, 2:00 PM PT; two days of slack is the point. |

## What could go wrong on camera, and what to do

- **The build fails or times out.** It now recovers as `partial` with whatever
  was checkpointed. A real recovery story, but not one to demo — cut and re-run.
  You have five an hour.
- **The sweep dies with the tab.** It is a synchronous request. **Do not switch
  tabs, close the lid, or let the machine sleep during shot 7.**
- **A confirmed row cites the wrong page.** The citation defect is open. Shots 5
  and 9 must use rows **checked in advance**. The anachronisms are reliable; an
  unchecked confirmation is a coin flip.
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

**The treatment is unchanged.** The existing Beat That Shook The Void treatment
is what gets pasted in shot 2.

## The one thing to protect

**The catch at 1:50 is the video.** Everything before it is setup and everything
after it is a coda. If the edit runs long, cut the agent-door beat to five
seconds and the build to twenty — never the catch.
