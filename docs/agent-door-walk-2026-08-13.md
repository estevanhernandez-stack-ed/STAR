# STAR agent-door walk — 2026-08-13

Walker: Claude (Cowork session), STAR connector over Anthropic's MCP proxy. Rooms touched: `1fd837bdd99e` (researched, "Doctor Who: Liverpool and Hamburg Special"), `054dfd2a82ad` (imported this walk), sweep `a4c89e30722b`. Steps 1–10 walked; 6b and 8 spent as marked; step 7 stopped at the refusal; deviations disclosed in §1 and §5.

---

## 1. Removed, spent, or written without being asked

**Nothing was removed.** Nothing was spent or written beyond the walk's orders. The complete ledger: one sweep (step 6b, marked: 1 search) and one editor call (step 8, marked, 0 searches); one room imported (`054dfd2a82ad`), one bible written on it, one link set (`054dfd2a82ad` → `1fd837bdd99e`), three writer notes and one strike filed on sweep `a4c89e30722b` — all ordered by the walk. I additionally requested and received desktop access to `C:\Users\estev\Downloads` to read the step-6a file; that grant is session-scoped and was the minimum needed.

**One disclosed deviation.** Step 6a was walked with a faithful 6-row subset of the real file (same columns, same room, same missing parent `01c41bcf266a`), not the full 73-row/159KB text. Reason in §3-T2: the door's own contract would have required this client to transmit the full file three times. Every judgeable behavior (arm report, complaint, token mint/spend/reuse) ran against the subset; what the subset cannot prove is in §5.

## 2. Defects

**D1 — `sweep_draft` confirmed a planted anachronism, on imported evidence.** Input: one scene headed `NIGHT (1958)` containing "a Vox AC30 amplifier." The AC30 shipped late 1959/60; the correct 1958 amp is the AC15. Output: `"verdict": "confirmed"`, note `"Vox AC30 valve amplifiers were accessed by British musicians in the late 1950s."`, `citation_sources: ["room"]` — the "room" being the *imported* room, whose finding smears "1958–1960" across instruments that arrived at different points in that range. Three failures stacked: the researched build filed a date-range finding that covers a year one of its objects didn't exist in; the sweep answered a specific-year scene from that range without noticing the mismatch — the exact "right in 1958, wrong in 1960" case the tool's own description claims as its argument, inverted; and imported, never-verified-here findings satisfied the "work the room's files first" instruction, so no fresh search ran. This is the laundering path `import_rooms`' warnings describe, closed everywhere except here.

**D2 — `import_rooms` arm preview mints an id that never exists.** The first (no-confirm) call returned `"run_id": "6ed4bdb882b9"` in its preview; the confirm filed the room as `"run_id": "054dfd2a82ad"`. An agent that captured the preview id — the natural thing to do with a field named `run_id` — holds an identifier that addresses nothing, ever. Omit it or honor it.

**D3 — the import brand does not appear where a room is actually read.** `import_rooms` promises "AN IMPORTED ROOM SAYS IT WAS IMPORTED, and cannot be made to stop." `list_rooms` carries `imported_at`. But `get_room` `shape: summary` on `054dfd2a82ad` opens "This room is filed and complete: the story profile, the research plan, 4 category drawers…" — no `imported_at` field, no import sentence, and it claims a research plan the room does not have (imports carry none). The one reply an agent reads to know what a single room *is* omits the one fact that cannot come off. (`search_count: 0` is honest, and the step-8 check passed: writing the bible did not inflate it.)

**D4 — `import_notes` skips a duplicate-claim row silently.** My file had two rows for the claim "two shillings" (different sources): row 4 `dismissed: yes`, row 5 blank, both with edited excerpts. Complaints named rows 2, 3, and 4; row 5's excerpt edit drew no complaint, and the yes-vs-blank conflict on `dismissed` resolved to struck with no comment. The tool that promises "nothing is dropped in silence" dropped a row in silence. Also: complaint row numbers count the header (Excel-style) — correct choice, stated nowhere.

**D5 — `delete_room`'s scope refusal is unreadable through this client.** Two attempts, verbatim: `Protected resource https://star.626labs.dev does not match expected https://api.anthropic.com/v2/ccr-sessions/…` then `Streamable HTTP error: Server returned 403 after trying upscoping`. No `rooms:delete` on this credential (correct), nothing removed (correct), but the "words a person could act on" exist only in the tool's description, which predicted this exact outcome. Known since round three; the walk asked, so it is re-reported: still standing.

**D6 — export filenames collide within a day.** `doctor-who-liverpool-and-hamburg-special-research-2026-08-13.csv` carries room and date, no time. Two exports of the same room an hour apart are indistinguishable by name; the walk's own fixture file — `…research-2026-08-13 (1).csv` — is the operating system doing the disambiguation the filename didn't.

**D7 — the sweep export names the wrong return door.** `export_room` `kind: sweep` replies "It imports back through `import_rooms`" — a sweep file goes back through `import_notes`; `import_rooms` would arm it as *research rooms*. An agent following that sentence files a sweep's claims as findings.

**D8 — nonsense tally sentence at n=n.** `sweep_draft`: "The draft made 3 claims about the world and 3 of them were distinct, so the department asked 3 questions rather than 3." The dedup argument, rendered absurd when nothing deduplicated.

**D9 — copy slip in `defend_claim`:** "1 of these address is a forum or comment page." Minor; it sits inside the tool's best paragraph.

## 3. True but unusable

**T1 — the missing-parent complaint, verbatim:** "'Doctor Who: Liverpool and Hamburg Special' follows a room that is not in this file, so it arrives unlinked. Set what it follows with Name and place." Two failures in one sentence. The parent's id (`01c41bcf266a`, sitting in every row's `continues` column) is never named — the one identifier the person needs to re-link is the one withheld. And "Name and place" is a *web-app control*; the door this complaint came out of has `link_room`, which the complaint doesn't mention. An agent holding this reply can do nothing with it except re-derive both facts from the raw CSV.

**T2 — the round trip is not walkable at size through this door.** `import_rooms` requires `csv` on the arm call *and* the confirm call; the token-reuse probe makes a third. For the real 159KB file that is ~45k model-authored tokens transmitted three times — more than this entire walk's remaining budget. The export side solved this ("`summary` … because reading one into a model's context costs more than everything else this department does"); the import side re-creates it, doubled. A confirm that accepts token-alone (server holds the armed file for its 600 seconds), or accepts a content hash, closes it.

**T3 — `ask_room`'s ranking is illegible.** Step-3 reply: "8 of 32 findings … closest first," with `matched_terms` running 1, 1, 1, 2, 2, 2, 2, 2. The two street-lighting findings that answer the question ranked first *with the lowest printed score*, above bus-seating rows that share more terms. The right answer surfaced, but the only number shown contradicts the stated order — a reader cannot tell why #1 beat #8, or whether to trust #8 over #1 next time.

**T4 — a struck claim still counts as confirmed in the headline.** After the strike filed, `get_sweep` opens "3 distinct claims from 1 scenes: 3 confirmed" — the dismissal is in the claim body (`"dismissed": true`) and absent from the line a person reads first.

**T5 — step 2's known-quirk check:** the `get_room` *reply* says nothing about `source_count` (123) doubling the drawer citations (73); the tool *description* explains it well. An agent that reads descriptions learns it; a person reading the reply on a screen does not.

## 4. What the descriptions failed to tell

Cost marking is the success story: every spending tool says so plainly (`SPENDS`, "Spends one model call"), every free tool says "Costs nothing," and I never had to guess — the descriptions did that job. `delete_room`'s description even names the scope-fix path ("issue a token carrying `rooms:delete` from Your card"). What was missing: `import_notes`' complaint row-numbering scheme (header-inclusive — discovered by counting); the behavior of duplicate-claim rows with conflicting writer columns (discovered by triggering D4); that `import_rooms`' arm-preview `run_id` is provisional (discovered by comparing — D2); and that a *sweep* export must return through `import_notes`, which the export reply actively mis-states (D7).

## 5. What was not reached

The **full 159KB file** through `import_rooms` — subset used (§1); server-side handling of a 73-row file, and the arm report's counts at that scale, are unverified. The **genuine cross-sweep refusal** — a file exported from a real second sweep sent with the first's `sweep_id` — would have cost an unmarked `sweep_draft`; the free adjacent probe (same file, `sweep_id` column doctored to `ffffffffffff`) was refused with "That file was exported from a sweep that is not filed on this room… Export this sweep and mark that up instead. Nothing was changed." — actionable, names the fix, though it points at the parameter rather than naming the id. The **`delete_room` arm preview and confirm** — unreachable without the scope (D5); per the walk's rule, no confirmation would have been sent regardless, and nothing was removed. The **verdict-tamper probe** *was* reached and held: verdict edited to `anachronism` in the file, ignored and named on arm and on confirm, and `get_sweep` afterwards shows `"verdict": "confirmed"` with the writer's correction standing beside it as `writer_note` — which, given D1, means the sweep's one wrong verdict now carries the writer's true note under the department's false stamp, each labeled as whose it is. The system's honesty about *authorship* survived every attack; step D1 is about the judgment, not the ledger.

---

# What the walk found, and what was done about it

The walk ran. The report is the agent's; this section is what happened next.

## D1 — an imported room laundered a typed-in fact into a confirmed verdict

**Fixed, `star-00059` pending.** The agent typed *"the Vox AC30 was accessible
to British musicians in the late 1950s"* into a spreadsheet, imported it with
`import_rooms`, and swept a 1958 scene against it. **CONFIRMED**, citing the
room, no search spent, receipt indistinguishable from a researched one.

Every other guard on the import path held. The brand refuses to come off, the
source count is counted rather than read, a bible is refused on arrival, the
summary claims zero searches. And `_room_files` — the one function deciding
what the verifier actually SEES — printed a typed-in fact and a researched one
in the same shape, under the same heading, with the same grammar. **The brand
was on every surface a person reads and none the machine does.**

Two halves, because either alone is decoration:

- `_room_files` writes a PROVENANCE banner above an imported room's findings,
  naming the date and saying plainly that a person typed the facts and the
  addresses and either could be invented.
- The verifier is told what to do with one: nothing under that banner is a
  source, a claim cannot verify another claim, search it instead, and if you
  cannot search it the verdict is `unverifiable` and the note says why.

Seven tests, four mutations caught: never writing the banner, writing it for
every room until it becomes furniture, trailing it under the evidence instead
of leading, and never telling the verifier what one means.

## D7 — the sweep export named the wrong return door

**Fixed.** `export_room` told an agent its file "imports back through
`import_rooms`" for every `kind`, including `sweep`. Following that would file
a sweep's CLAIMS as researched FINDINGS — the same laundering as D1, arrived at
by obeying the documentation. A sweep goes back through `import_notes`, and
both places that said otherwise now say so.

## D3 — the brand was missing where a room is actually read

**Fixed.** Verified live against room `054dfd2a82ad` rather than taken on
report, and it was worse than reported: no `imported_at` anywhere in the
payload, no import sentence, and the reply opened by promising *"the story
profile, the research plan…"* — a document an imported room does not carry,
because it was never planned. `search_count: 0` was the only honest signal, and
an imported room shares that number with a build that failed before its first
search.

`get_room` now leads with the brand, drops the plan it cannot promise, and
carries `imported_at` as a field so a caller that parses rather than reads has
something to check. Four tests, two mutations caught.

## D1's other two thirds are still open, and they are the bigger half

The banner closes the LAUNDERING path: an imported room can no longer stand
behind a confirmed verdict. It does not close the other two failures the walk
stacked under D1, and a fully researched room can still produce the same wrong
answer honestly:

- **The researched build filed a finding smeared across "1958–1960"** covering
  objects that arrived at different points inside that range.
- **The sweep answered a specific-year scene out of that range** without
  noticing the mismatch — the inversion of the argument `sweep_draft`'s own
  description makes for itself.

That is a research-pipeline defect, not an import one, and it is the next real
piece of work.

## Still open, in the order I would take them

1. **The arm preview mints a `run_id` that addresses nothing** — preview says
   `6ed4bdb882b9`, the confirm files `054dfd2a82ad`. An agent that captured the
   first id is holding a handle to nothing.
2. **`get_room` shows no import brand.** The mark that "does not come off" is
   absent from the surface a reader actually reads a room through.
3. **The missing-parent complaint withholds the parent id** — `01c41bcf266a` is
   in every row it just read — and names a browser control instead of
   `link_room`, the fix on its own door. Seventh instance of the class.
4. **`import_notes` silently skipped a duplicate-claim row** and resolved a
   `yes`-vs-blank `dismissed` conflict without comment.
5. **`get_sweep`'s headline still says "3 confirmed"** after one was struck.
6. **Room export filenames carry no time.** Sweeps got the id; rooms did not,
   so the OS is still doing the disambiguating with `(1)`.
7. **The import round trip sends the CSV twice**, on arm and confirm. The
   export side solved this with `shape: summary`; the import side re-creates it
   and doubles it.
8. **`ask_room` prints "closest first" over matched_terms running 1,1,1,2,2,2.**
9. **`delete_room`'s refusal is transport noise** through the proxy.

## What held

The verdict tamper was ignored, named, and filed as a `writer_note` beside the
department's own stamp — including when the tamper was RIGHT and the stamp was
wrong. The ledger's honesty about authorship survived every attack in the walk.
D1 was never about the ledger. It was about the judgment.
