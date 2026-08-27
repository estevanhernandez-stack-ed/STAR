# Brief for the agent running the shoot

Paste this whole file as the opening prompt for a fresh session. It assumes no
prior context. Everything in it was verified on 2026-08-24 rather than
remembered.

---

You are helping Este shoot and submit the demo video for **STAR**, his entry in
the Agentic Cinema hackathon (Parallel track). The code is finished and
deployed. Your job is the shoot, not the product.

**Read `docs/video-plan-2026-08-16.md` first.** It holds the script, the twelve
shots, the timeline and the failure modes. It is the source of truth and this
brief only carries what a fresh reader would otherwise get wrong.

## Dates, and one of them already slipped

- **Today is 2026-08-24.** Check it (`date`) rather than trusting any date
  written in a document, including this one — an earlier session mis-stamped a
  week of commits because it trusted its own opening context.
- Capture the static shots **Aug 25**, shoot live **Aug 26**.
- Submit **Sep 5**. Hard deadline **Sep 7, 2:00 PM PT**.
- The plan's first timeline had an Aug 22 shoot. It passed. Do not be alarmed by
  older dates inside the plan's prose; the timeline table is current.

## What is deployed

| | |
|---|---|
| Live revision | `star-00066-4xz` |
| URL | https://star-390753828501.us-central1.run.app |
| Cloud project / region | `star-research-dept` / `us-central1` |
| `main` | `2365bd4`, 1131 tests green, nothing pending |
| Models | Gemini on **Vertex AI**, `GOOGLE_CLOUD_LOCATION=global` |

`global` is load-bearing: `gemini-3.6-flash` 404s in `us-central1`.

## The assets, all verified

**Room `1fd837bdd99e`** — "Doctor Who: Liverpool and Hamburg Special", era
1958-1962, four categories of findings, a bible, ten sweeps.

**Reference sweep `92d9c15c8ef5`** — 31 scenes, **75 claims: 34 confirmed, 33
anachronism, 8 unverifiable**. Every static shot can be captured off this.

**The draft**, already converted and committed:

    C:\Users\estev\Projects\doctor-whom\02_SHORT_STORIES\
      The Beat That Shook The Void\The_Beat_That_Shook_The_Void.fountain

31 scenes, **133,884 characters**, largest scene 7,731 (STAR refuses over
8,000). Regenerate with `python writer-studio/to_fountain.py` from that repo.

**Shot 5 — use this finding**, from the room's *logistics* drawer, hand-checked:

> A British band traveling from Liverpool to Hamburg in August 1960 traveled in
> a cramped commercial minibus — such as an Austin J4 or Morris J2 — driven from
> Liverpool through London to Harwich, loaded onto a cross-Channel ferry by quay
> crane to the Hook of Holland... a journey lasting 30 to 36 hours.

Four sources; two are dated and exactly on the fact. Backup: the Liverpool
Corporation double-decker finding, whose Wikipedia excerpt names "Liverpool
Corporation Transport Department" outright.

**Shots 9 and 10 — the catch.** `"turning it up to eleven"` in a 1959 scene,
sourced to *This Is Spinal Tap*, 1984. Beside it, `"Got blisters on your
fingers"` — Ringo, Helter Skelter, 1968. Then filter to the Casbah cluster: six
flags in one afternoon, with the Kaiserkeller, Indra and Top Ten behind them,
across 22 of the 31 scenes.

## Traps that look fine and are not

1. **Never film the `"He was seventeen."` row.** The 2026-08-14 sweep
   (`5b55e5c16c88`) flags it as an anachronism and is WRONG — it read "he" as
   George Harrison when both scenes mean John Lennon, who genuinely was
   seventeen in 1958. Este's draft was right. The current sweep confirms it
   correctly. That row was the original shot 9 and it would have been filmed.
2. **Shot 5 shows no caveat.** Room findings carry ledger citations but no
   `shares_claim_wording` flag — that lives only on the script-check path. The
   "7 of 34 confirmed rows carry a caveat" figure (re-counted 2026-08-24; an
   earlier pass said 6) is about SWEEP rows, shots 9/10. Do not promise a
   caveat on shot 5.
3. **The sweep is a synchronous request and dies with the tab.** During the live
   sweep: no tab switching, no closing the lid, no sleep.
4. **Deploying kills a build in flight** and resets the hourly counters. Nothing
   ships within 24 hours either side of the shoot.
5. **The sweep picker was tidied 2026-08-24, on Este's call.** The room now
   holds exactly one sweep — the reference `92d9c15c8ef5` — after the nine
   others (six scraps, two 64-claim Aug 13 passes, and the 78-claim Aug 14
   sweep carrying the seventeen false positive) were hard-deleted. The
   false-positive story survives only in this brief and the plan; the
   `5b55e5c16c88` sweep itself is gone. The picker reads clean on camera.

## Spending, which is the real hazard

- **5 builds per IP per hour.** Four rehearsal builds and the take is locked out.
- **5 checks/sweeps per hour**, same window, separate counter.
- Build: 600s timeout, 30 searches. Sweep: 300s timeout, 30 searches.
- Rehearse against rooms that already exist. Spend only on the take.

**Shot 3 is a live build, so it needs a room that does not exist yet.** Build a
NEW room from the same treatment. **Do not delete `1fd837bdd99e`** to make room
— it is the verified backup and it holds `92d9c15c8ef5`.

## How to work

Read-only inspection is free and encouraged. Firestore is reachable locally with
Application Default Credentials; load `.env` for `GOOGLE_CLOUD_PROJECT`, then
`firestore.Client(...)`. Rooms live at `users/{uid}/rooms/{run_id}`, sweeps at
`.../sweeps/{sweep_id}`. Este's uid is the one whose rooms include `1fd837bdd99e`.

**Ask before:** deleting any room or sweep, deploying, or spending a build or
sweep. Everything else — reading, checking a citation by hand, drafting
voiceover, updating the plan — just do.

**Verify rather than assume.** This project's expensive mistakes have all been
the same shape: a surface said something true and unusable, and two green test
suites either side of it proved nothing. Open the actual artifact. If a claim in
this brief does not match what you see, the artifact wins — say so.

## The one thing to protect

The catch at 1:50 is the video. If the edit runs long, cut the agent-door beat
to five seconds and the build to twenty. Never the catch.
