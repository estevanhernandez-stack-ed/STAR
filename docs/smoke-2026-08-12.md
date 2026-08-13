# Smoke list — cycle #22, 2026-08-12

> Everything built tonight, in the order it is fastest to check, with what
> "right" looks like beside each step.
>
> **Pins go stale, and these two did** — they read `star-00049-j5r` / `0855bd2`
> while the service served `star-00050-wgc` and HEAD was `216b917`. Caught by a
> runbook walk, not by anything here. They now name the command that answers
> instead of a value somebody has to remember to retype:
>
> - revision: `gcloud run services describe star --project star-research-dept
>   --region us-central1 --format='value(status.latestReadyRevisionName)'`
> - HEAD: `git -C . rev-parse --short HEAD`
> - tests: `python -m pytest -q`
>
> A pin nobody updates is worse than no pin.
>
> **Where you are:** steps 1, 2, 3 and 6 are done and passed. **Steps 4, 5, 7
> and the new 8 are open.** Step 4 grew since you last read it — the CSV you
> pressed was the sweep's and you asked for the room's — and step 8 is the
> sharing half, which did not exist when this list was written.
>
> **Why this list exists.** Every defect that mattered tonight was found by
> printing a PDF, reading a screenshot, or sweeping a real draft — none by a
> test. The suite is necessary and it is not sufficient, and the surfaces below
> are the ones a suite cannot see.

## What I could already verify, and what I could not

**Verified against real data** (no browser required, nothing spent):

- The chain walk over all 17 stored rooms — every room walks to itself first,
  no repeats, within the depth cap. A simulated Colliery Canteen → Ruth Kovacs
  link ordered nearest-first correctly.
- The sweep CSV over a real filed sweep: 24 claims → 45 rows, 78,660
  characters, re-read as CSV with all 45 rows and 10 columns intact, and **no
  cell that would run as a formula**.
- The import path on that exact file: an untouched export re-imports with no
  marks and no complaint; a row adding a note lands it; the same row's attempt
  to set `verdict` and `source_url` is refused **by name**.
- The Fountain splitter over your real draft: 24 scenes, longest 5,526 chars,
  indices 1..24 so every verdict can name its page.
- ~~Every new route answers **401** unauthenticated on the live service.~~
  **This was false when it was written, and a runbook walk caught it.** Six
  write routes answered **422** to an anonymous caller, naming the field they
  were missing, because a Pydantic body is validated before a handler runs and
  the auth check lived inside the handler. Nothing executed; what leaked was
  the shape of a request body on surfaces that spend money. Auth is a
  dependency now, and `tests/test_api_auth_posture.py` walks every declared
  route with an empty body AND an unparseable one — the second case caught two
  more routes the first missed.
  **Worth naming as a limit even now:** the 401 assertion was also green while
  the browser download was broken, because a 401 was exactly what the browser
  was getting. A route that refuses strangers is not a route the app can
  reach, and a route that refuses them for the wrong reason is not one either.

**Could not verify** — these need your eyes or your account:

- Anything rendered. Layout, contrast, print output.
- Anything that spends. A live sweep, a live check, a live requisition.
- ~~Any chain, because **no room in the account has a `continues` link yet**.~~
  **No longer true.** You built Liverpool, linked the Doctor Who room to it, and
  checked a scene through the chain. Afterwards I proved the chain wiring
  against those two real rooms at no cost: the verifier's block went from
  139,029 to **246,008 characters** and the hydration ledger from 58 to **101
  sources**, and all five Liverpool-only addresses resolve through the chain
  while resolving to nothing through the Doctor Who room alone. That last
  clause is the part that matters — the first chain test I wrote was
  confounded, because the Doctor Who room already held Liverpool material and
  a check could have passed on its own findings.

---

## 1. The sweep survives a reload · 2 min · no spend

1. Open the Doctor Who room → **Check the script**.
2. Paste the draft. Press **Sweep the whole draft** *(this spends — skip if you
   have already run one tonight and go to step 3)*.
3. **Wait for the result to appear.** A sweep is a synchronous request, not a
   background job: the browser holds the connection until the answer comes
   back, which is a minute or two on 24 scenes. Unlike a build — which
   registers in the run registry, runs as its own task and streams over SSE
   precisely so it survives a reload — a sweep has nothing to reconnect to.
4. **Now reload the page.** Reopen the room and the check panel.

**Right:** a row reading **"Draft sweeps filed on this room"** with an entry
like `24 scenes · 67 claims · 12 AUG 2026`. Press it — every verdict, source,
excerpt and scene number comes back.

**Wrong and worth reporting:** the row is missing, the entry is labelled only by
date, or a reopened claim shows a verdict with no sources under it.

## 2. A swept verdict shows its receipts · 1 min · no spend

Look at any **confirmed** claim in that result.

**Right:** under the verdict, the source's title, its address, and the page's
own words in quotes. Plus a line saying *a verdict is the department's reading
of the sources under it, not a check of the line against the world.*

**This is the one I got wrong first time** — 45 confirmations with nothing on
screen behind any of them.

## 3. The printable report · 3 min · no spend · **needs your eyes most**

1. From a filed sweep, press **Open the printable report**.
2. Read it on screen, then **Ctrl+P** and read the PDF.

**Right:** masthead names the room and era. **Anachronisms first** — "turning it
up to eleven" near the top, not buried. Every claim's sources on the *same page*
as the claim. Scope line present.

**Wrong:** a verdict on one page and its citation on the next; a raw category
key; a URL printed twice; an unreduced excerpt running for a paragraph.

*The defence card shipped three defects that only a printout revealed. This page
has had none.*

## 4. Three CSVs · 6 min · no spend

There are three now, not one, and they answer three different questions. Two of
them did not exist when you first read this list.

**Retry this step from the top.** When you pressed the sweep's CSV earlier it
sent you to a sign-in page while you were signed in: the link was a plain
`<a href>`, which is a browser navigation carrying cookies and no
`Authorization` header. All three go through `authedFetch` now and save a blob.
*The server test asserting the unauthenticated 401 passed the entire time it
was broken, because a 401 was exactly what the browser was getting.*

**4a. What the draft claimed** — **Download as CSV** on a filed sweep.

Filename `doctor-who-…-sweep-2026-08-13.csv`. One row per claim per source, with
`verdict`, `scenes` and `sweep_id`.

**4b. What the department found** — **Research as CSV** in the room's head,
beside *The bible*. **No sweep required**; this is the room's own findings.

Filename `…-research-2026-08-13.csv`. Columns `drawer, fact, source_title,
source_url, source_excerpt, retrieved_at, requisition, room, era, run_id`.

Two worth looking at:

- **`retrieved_at`** is the finding's own date where it has one and the room's
  otherwise, the same rule the RET stamp follows. Sort by it and the seven
  bibles you resynthesised should sit apart from the build that filed them.
- **`requisition`** carries the question you asked to put a finding there, empty
  for everything the build filed. It is how commissioned research reads
  differently from planned research.

**4c. What the story found** — **The story as CSV**, next to it. **This control
only appears on a room that follows another room**, so it is on the Doctor Who
room and not on Liverpool.

Filename `…-story-2026-08-13.csv`. Same columns; every room in the chain,
nearest first.

**The check that matters on 4c:** sort or filter on the **`room`** column. Each
room's rows should be exactly its own file from 4b — that is the whole reason
merging two rooms into one file is safe to offer, and it is asserted in the
suite rather than hoped for. A source cited by both rooms appears **twice**, on
purpose: a source doing double duty across a chain is a fact about the research.

**Right, on all three:** open in Excel **and** Sheets. A claim with commas,
quotes or a line break sits in one cell. **Nothing executes.**

**Wrong and important:** any cell that runs as a formula; text shifted into the
wrong column; a sign-in page instead of a file; or a `story` file on a room that
follows nothing.

## 5. The round trip · 5 min · no spend · **the most interesting one**

1. In the spreadsheet, add a `writer_note` column and type a note against two
   claims. Set `dismissed` to `yes` on one.
2. Also **change a `verdict` cell** on a third row — deliberately. And type a
   claim that does not exist into a fourth.
3. Save as CSV.
4. Back in the check panel with that sweep open, scroll past the results to
   **"Marked the export up in a spreadsheet? Bring it back."** Choose the file.
5. Press **Read the file**. Read what it says. Then press **File these notes**.

**Right:**

- The button is dead until a file is chosen.
- The first press changes **nothing** and says so: *"N claims in this sweep
  would take a note from that file. Nothing has been changed yet."* The button
  re-labels itself to **File these notes** — that re-label is the arming.
- The invented claim is listed **by name** under "rows named a claim this sweep
  does not hold".
- The changed verdict is refused **by column**: *"Row N carries verdict, which
  the department writes."*
- The second press files the notes. Reload and reopen the sweep — your notes
  are still there and every verdict, source and excerpt is unchanged.

**Wrong and worth reporting:** the first press writes; the invented claim
disappears silently; the verdict you typed sticks; or choosing a *different*
file after a preview and pressing again files that second file without
previewing it.

## 6. Continuation stacking · **done, passed**

You built Liverpool, linked the Doctor Who room to it, and checked a Hamburg
scene through the chain.

One honest footnote from that run. When a check came back with no claims about
the Casbah, the reason is not the chain: the Doctor Who room was researched as
Liverpool **and** Hamburg from the start, so its own findings can answer a
Liverpool question and a passing check proves nothing about whether the chain
carried it. That is why the proof above is stated in Liverpool-**only**
addresses — five of them, resolving through the chain and resolving to nothing
without it.

## 7. Nothing regressed · 2 min · spends one check

Check a single scene against an **unlinked** room, the way you did earlier.

**Right:** exactly what you saw before — marked scene, claims, verdicts, the
citation rail. An unlinked room must read as it always did.

## 8. Handing a room to somebody · 8 min · no spend until the last step

Built after this list was written, and the reason the exports exist at all.

**8a. A swept scene says so.** Re-sweep the draft — the strip should come back
reading `24 swept, 4 checked on their own`, with a quiet **SWEPT** against
every scene and **CHECKED** against the four with their own filed check. A
sweep filed before tonight has no scene keys stored and cannot be backfilled,
so the ticks only appear from the next sweep on. *(This step spends one sweep.
Skip it if the budget is better spent elsewhere; nothing below depends on it.)*

**8b. The bible as a file.** New button in the docket. Downloads
`…-bible-2026-08-13.md` with a masthead naming the room, era, build date and
source count. It hides on a room that has no bible rather than failing at you.

**8c. Import a room.** Sign out, or just start from the landing page. Under the
treatment box: **"Been handed somebody else's research?"** Choose the Liverpool
**Research as CSV** → **Read the file** → **File these rooms**.

**Right:** the first press changes nothing and names what is in the file. The
second files it and drops you into the room. The docket says *"Imported from a
file… no searches were run here, and nothing in it has been verified by this
department."* The stats line reads `imported 13 AUG 2026 · N sources came with
it · no searches run by you`.

**The check that matters:** the source count on an imported room is counted
from the urls that actually arrived, not from the number the file claims. Your
Liverpool export says 58; the imported room should say however many distinct
addresses are really in the file.

**8d. Import a story.** Same again with **The story as CSV**. Two rooms should
arrive, and the near one should already **follow** the far one — check the rail
grouping, or open Name and place. That link travelled in the file and was
remapped onto the ids this account just minted.

**8e. Write the bible.** On an imported room, **Write the bible**. *This is the
only step here that spends: one editor call, no searches.*

**Right:** a bible appears, written from the findings the room actually holds.
The room still says it was imported — a document written about research does
not make the research yours.

**Wrong and worth reporting:** an imported room that reads like a built one
anywhere; a source count that matches the number in the file rather than the
addresses in it; a story that arrives as two unrelated rooms; **Write the
bible** offered on a room that already has one.

## 9. The agent door · 10 min · one step spends

Fourteen tools, six of them shipped after this list was written, and none of
them had a step here. Three spend and one destroys a room. **Run this from
Claude Desktop or the VS Code extension against the STAR connector**, not from
the browser — the point is the door a writer would use if they never opened one.

**9a. The handshake.** Ask the agent to list STAR's tools.

**Right:** fourteen, in three bands — reads, then writes that spend nothing,
then spends. The handshake names every one of them. **Wrong:** a count that
disagrees with what is served; a tool the handshake never mentions.

**9b. Reads cost nothing.** *"List my STAR rooms, then show me the Liverpool
room's summary."*

**Right:** `list_rooms` then `get_room` with `shape: summary`. Search count and
source count come back. **`source_count` is about twice the citations in the
drawers** — that is correct and now documented: it counts every page a search
returned, and a citation is a page a researcher chose to stand a finding on.

**9c. Export without a browser.** *"Export the Liverpool room's research and
tell me what is in it."*

**Right:** `export_room` defaults to `shape: summary` — filename, size, column
names, first rows. **Wrong and important:** a wall of CSV in the reply. That
default exists because the file runs to hundreds of kilobytes.

**9d. Import without a browser.** Ask it to read a research export off disk and
file it. *(A desktop agent has filesystem tools; the VS Code extension does
too.)*

**Right:** two calls. The first says what the file holds and files nothing, and
hands back a one-time token. The second files it and says the rooms are marked
imported, spent no searches, and have no bible. **Wrong:** anything filed on
the first call; a token that works twice.

**9e. Write the bible for it.** *"Write the bible for the room you just
imported."* — **this is the step that spends**: one editor call, no searches.

**Right:** a bible appears and the room still says it was imported.

**9f. The destructive one, without pressing it.** Ask it what deleting a room
would remove — *and stop there*.

**Right:** `delete_room` called once, with no confirmation, reporting exactly
what the room holds and handing back a one-time token. Nothing is deleted.
**Wrong and worth reporting immediately:** anything removed by that first call.

---

## Open, and deliberately so

- **No `continues` editor was added tonight** — the chain reads whatever the
  room edit already sets, which is why step 6 asks you to link two rooms by
  hand.
- **FDX** is untouched. Fountain only.
- **Live sharing** was cut by you in favour of export, and stayed cut.
- **A sweep does not survive the tab that started it.** It is a synchronous
  request; a build is not. Navigate away mid-sweep and the tab loses it —
  whether the server finishes and files anyway depends on how uvicorn treats a
  client disconnect, and that is **untested**, because finding out costs a real
  sweep. Worth knowing before it is demoed: a build can be walked away from and
  a sweep cannot. Making the sweep resumable would mean the run registry and an
  SSE stream, which is the shape `_start_build` already has.
- **One mutation of the import arming survives its test, and is left in.** The
  arming remembers the text it previewed rather than a flag; the file-change
  handler already clears it, so no reachable path exercises the identity check
  alone. Kept because the handler is one listener away from a browser that does
  not fire `change` on a re-pick, and documented in the code rather than papered
  over with a contrived test.

## What changed after this list was first written

**The CSV import UI.** This list originally said it was unbuilt and that item 4's
acceptance was met at the API and nowhere a writer could reach it. It is built,
tested behaviourally, deployed, and is now step 5 — which is the step most worth
your time, because it is the only path where text a user typed becomes part of a
room's record.

**Two more CSVs, both from your reading of the first one.** "Can I only get it
when I sweep an entire script? It should be for the whole room" produced 4b, and
"and its chain as an option" produced 4c. Neither was in the plan; both are the
same export widened, and the `room` column the first one already carried is what
made widening safe rather than lossy.

**The download itself was broken when you pressed it**, and the fix is in all
three. See the note at the head of step 4 — it is the second time in this build
that a passing test sat over a broken surface, and both times the test was
asserting the input rather than the outcome.

**The whole sharing half, which is step 8.** The import that existed when this
list was written filed a writer's notes back into their own sweep — a triage
loop reachable three levels inside a room, which only ever served the person
who already had the data. A room can now be handed to somebody who was not
there when it was built: exported, imported at the top level, marked as
imported wherever it makes a sourcing claim, and able to write its own bible
from the research it was handed.

**And the import stopped crying wolf.** The "you edited the department's
columns" complaint fired on every annotated row, because an unmodified export
carries a verdict and a source on every row and the check could only see they
were present. It now fires only when a value comes back that the sweep never
wrote.

## Known and accepted

- `pip-audit` flags **six advisories against `pip` itself**, no runtime
  dependency. The Dockerfile runs `pip install` at build and never at runtime,
  so nothing in the served container reaches a vulnerable pip. Worth an upgrade
  on the next image bump; not worth a rebuild tonight.
- The check ceiling is still **5/hour**. The sweep makes it much less painful —
  one slot for a whole draft — so raising it is no longer urgent.
