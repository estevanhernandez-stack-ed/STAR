# Voiceover sheet — timed for the ElevenLabs pass

Read at 150 words per minute. Each line carries its word count and the
seconds it needs at that pace, against the seconds the shot has. Where the
line runs long the shot is the fixed thing and the line gets cut, never the
other way round. The catch at 1:50 is protected: it keeps every word.

Clip sources: `build` = shot-03-04-build-live-trim.mp4 (2:21, speed-ramp to
fit); `reel` = statics-reel.mp4 with the cut marks in statics_marks.txt;
`sweep` = Este's screen recording of the live sweep (or the clean re-take);
`agent` = the shot-11 snip; `editor` = Este's own capture of the draft.

| # | Time | Shot | Source | Line | Words | Needs | Has |
|---|---|---|---|---|---|---|---|
| 1 | 0:00–0:20 | Draft on the page, Casbah visible | editor | Every studio has a research department. A writer working alone gets one chance to notice that the club in this scene opened a year after the scene is set. | 31 | 12s | 20s |
| 2 | 0:20–0:25 | Intake, treatment pasted | reel 2.5s | *(no line — let the paste land)* | 0 | 0s | 5s |
| 3+4 | 0:25–1:00 | Build rail filling, query strings | build, ramped | Four researchers, live web search, about two minutes. Every finding it files comes back with the page it came from. | 20 | 8s | 35s |
| 5 | 1:00–1:20 | One drawer, one finding, its source | reel 17.5s / 25.8s | Nothing here says "verified." It says what was checked, and what it could not settle. | 16 | 6s | 20s |
| 6 | 1:20–1:25 | Draft pasted, 31 scenes | reel 35.5s | *(no line)* | 0 | 0s | 5s |
| 7 | 1:25–1:45 | Sweep running, real-time counter burned in | sweep, ramped | Eight chapters, twenty-three thousand words, one request. Scene by scene this would be thirty-one search budgets. It is one. | 21 | 8s | 20s |
| 8 | 1:45–1:50 | Result header, 75 claims | reel 44.3s | Seventy-five claims. Thirty-four confirmed. Thirty-three anachronisms. | 8 | 4s | 5s |
| 9 | 1:50–2:10 | eleven + blisters | reel 52.3s | That phrase comes from a film made in 1984. Two rows down, "Got blisters on your fingers" — Ringo said that in 1968, on Helter Skelter. Neither is a date anybody could be expected to hold in their head. | 40 | 16s | 20s |
| 10 | 2:10–2:35 | The Casbah cluster | reel 62.3s | The Casbah opened in August 1959. So did Mona Best's coal cellar under it, its espresso machine, the spider painted on its wall and the rainbow on its ceiling. Six flags, one afternoon — and the Kaiserkeller, the Indra and the Top Ten behind them, across most of the thirty-one scenes, all tracing to a single decision about when this story happens. It does not tell you that is wrong. It is a Doctor Who story about a stolen chord — the timeline might be broken on purpose. It tells you a reader will notice, in twenty-two of the thirty-one scenes. What you do about it is the writer's business. | 111 | 44s | 25s |
| 11 | 2:35–2:50 | Agent calling defend_claim | agent | Fifteen tools over MCP. Same rooms, same receipts, no browser — and the ones that spend money say so before they spend it. | 23 | 9s | 15s |
| 12 | 2:50–3:00 | Draft again, line flagged | editor, or `check` 170s–181s | Every studio has a research department. Now every writer has one, and so does every agent they run. | 19 | 8s | 10s |

Shot 12 has a second source since the shoot: `shot-12b-check-inline.mp4`, a
live check on Chapter 3 scene 1 that renders the Casbah paragraph with five
marks in red and the rail reading "The Casbah Coffee Club opened on August
29, 1959, so it did not exist in 1958." From 170s the frame is the flagged
line on the page itself. Either bookend works; the browser one lets the close
rhyme with shot 1 (same paragraph, now marked) without leaving the product.

**Total voiced: 289 words, ~1:56 of speech inside 3:00.** Comfortable everywhere
except shot 10, which needs 44 seconds and has 25. That is the catch, so the
line stays and the clock moves: take 10 seconds from the build (35 → 25, the
plan's own cut) and 5 from the agent door (15 → 10, the plan's other cut), and
shot 10 becomes 2:05–2:45 at 40 seconds. Read it a shade under pace and it
fits with air.

**Generated 2026-08-26, voice `8gpP3pZU3NERlkDEdxub` (the audiobook narrator,
Este's clone), `eleven_multilingual_v2`. Measured, not estimated: 93.6s total.**
The clone reads faster than 150 wpm, and the collision above dissolves.

| Clip | Measured | Shot has |
|---|---|---|
| vo-01-open | 8.4s | 20s |
| vo-03-04-build | 6.5s | 35s |
| vo-05-receipt | 4.4s | 20s |
| vo-07-sweep | 7.8s | 20s |
| vo-08-numbers | 4.0s | 5s |
| vo-09-eleven-blisters | 13.6s | 20s |
| vo-10a-casbah | 22.1s | — |
| vo-10b-writers-business | 13.5s | — |
| vo-11-agent | 7.7s | 15s |
| vo-12-close | 5.6s | 10s |

Shot 10 at 35.6s voiced fits its original 25s only with the cuts above still
applied (build 35 → 25, agent 15 → 10 gives it 40s). Keep those cuts: the
catch gets 40 seconds and 4 seconds of air, which is right. Shot 8's numbers
land in 4.0s against a 5s hold — tight but clean. Everything else has room.
Regenerate any single line by editing its slide in `vo/manifest.json` and
rerunning; the files are per-shot so one change costs one clip.

## Title card (added 2026-08-26, Este's call)

Four seconds up front, before shot 1: the app's own dark ground, the ✶ mark,
STAR in Archivo Narrow, the subtitle in Sligoil, and the script's first line
as the tagline in Newsreader italic. Fades in and out over 0.6s. Paid for by
trimming shot 5's hold from 20s to 16s (its line ends at 5.4s), so the cut is
still exactly 3:00. Rendered from `scripts/shoot/title.html` by
`render_title.py` with the vendored fonts, so it matches the frames around it.

## End card (added the same day)

Four seconds after shot 12, matching the title: the mark, STAR, then the
close in two lines — "Now every writer has a research department." / "And so
does every agent they run." — the live URL and the GitHub path under it. Paid
for by trimming shot 1 from 20s to 16s (its line ends at 9.4s). Still 3:00.
`scripts/shoot/end.html`, rendered by `render_card.py end`.

## Notes for the read

- "verified" in shot 5 wants audible quote marks — a half-beat either side.
- Shot 8's three numbers are the only numbers spoken in the video. Land each
  one; they are what the sweep frame shows.
- Shot 9's "Neither is a date anybody could be expected to hold in their
  head" is the thesis in miniature. Slow it.
- Shot 10's "It does not tell you that is wrong" is the strongest line in the
  script. Pause before it. The turn from catching to declining to judge is the
  whole point of the product.
- Shot 7's line says "about two minutes" for the build now (the take filed in
  2:09); the plan's "about four minutes" is retired.
- Nothing is voiced over shots 2 and 6. Silence plus the paste is the beat.

## What the counter overlays say

- Build: real elapsed, from the page's own "0:08 elapsed" counter — it is in
  the frame, no overlay needed unless the ramp blurs it.
- Sweep: burn in `ELAPSED 0:00 → 3:20` and one caption, "31 scenes · one
  request", because the surface itself shows only a status line.
