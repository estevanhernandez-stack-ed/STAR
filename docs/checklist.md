# STAR — Build Checklist, cycle #22

> Vibe Cartographer cycle **#22**, `/checklist`, 2026-08-12. Mode: fully-autonomous
> (*Autonomous — Self*). Persona: Architect. Deepening rounds: 0, per the builder's standing
> pattern when the substrate is understood.
>
> **No new spec drives this cycle.** [`spec.md`](spec.md) is cycle #19's and still describes
> the app truthfully; it does not describe these five asks, which came from the builder
> directly across a working session on 2026-08-12 and from the round-three judge critique's
> Part 4. This checklist is derived from those asks and names its own acceptance criteria.
> Cycle #20's wave checklist is preserved in git at `8f678a3`.
>
> **Where this cycle starts.** 129 commits since #20. HEAD `3f5a280`, deployed
> `star-00036-92c`, 833 tests green, ruff clean, working tree in sync with origin/main.
> Shipped tonight and NOT in this list: the threat model, the `ask_room` reach fix, the
> failed-room account, seven repaired bibles, `research_question`, `defend_claim` and its
> printable card, the Fountain draft strip, and the whole-draft sweep.

## Build Preferences

- **Build mode:** Autonomous. From the record, not re-asked.
- **Git:** Commit after each item. Declarative sentence-case subjects, no conventional-commit
  prefixes. Push and deploy after each item that changes a served surface, and VERIFY the
  deployed artifact by fetching it — an exit code is not a deploy.
- **Gate before every commit:** `ruff check star tests scripts harness` and the full `pytest`,
  both by exit code rather than by reading the tail.
- **Tests:** behavioural where the defect can be behavioural. Three times this session a
  source assertion passed over a broken surface — the defence card, the draft-strip guard,
  and the toggle label. A test that asserts a string exists is not a test that the thing
  works.
- **After each item:** run it against a real artifact. Every defect found tonight that
  mattered was found by printing a PDF, reading a screenshot, or sweeping a real draft.

## The rule this cycle keeps

Every item below either **stores something a reader can come back to** or **hands something
over that leaves the app**. Both are places where an honest surface can quietly stop being
honest — a stored payload that drops a source, an exported file that reads as more certain
than the screen it came from. Each item's acceptance criteria say what must survive the trip.

---

## 1. File the sweep

**Depends on:** nothing. **Blocks:** 2, 3, 4. **Effort:** M.

A sweep result exists only in the browser tab that ran it. Reload and a whole draft's worth
of answers — and the searches that bought them — is gone. Nothing can export what is not
stored, so this is the prerequisite for the three items after it, and it is worth doing on
its own account: a check has always been filed, and a sweep is the more expensive of the two.

- [ ] `sweep_to_document` / `document_to_sweep` in `star/store.py`, pure, beside the scene
      pair they mirror. Carries: `sweep_id`, `created_at`, `scenes_read`, `claims_raised`,
      the claims with their verdicts, citations and scene lists, `search_count`,
      `budget_exhausted`, `cover_note`, `scope_note`.
- [ ] Stored as a subcollection of the room — `/users/{uid}/rooms/{run_id}/sweeps/{sweep_id}`
      — for the three reasons the scenes subcollection records: a room read must not pay for
      every sweep ever run against it, `.set()` on the room would clobber them, and one
      delete must be one delete.
- [ ] `sweep_summary` for a list, excluding the claims for the same reason `scene_summary`
      excludes the scene text.
- [ ] `GET /api/rooms/{run_id}/sweeps` and `GET …/sweeps/{sweep_id}`, uid-scoped by path so
      another account's sweep is not found rather than refused.
- [ ] `DELETE …/sweeps/{sweep_id}`. A sweep holds the writer's scene text in its claims and
      the retention promise the check panel already makes has to cover it.
- [ ] The panel lists filed sweeps and reopens one, labelled by **what it swept and when** —
      the lesson from the filed-check row, which shipped as a column of identical dates.

**Acceptance:** run a sweep, reload the page, reopen it from the list, and every verdict,
source, excerpt and scene number is the one that was there before. Delete it and the claims
go with it. A sweep filed against room A never appears under room B.

**Watch for:** the scene text inside claims is a writer's pages. Whatever the check panel's
retention copy promises, this must not quietly break.

---

## 2. Export a sweep as a PDF report

**Depends on:** 1. **Blocks:** nothing. **Effort:** M.

The defence card already proved the path: a standalone page, print CSS, and the browser's own
dialogue. No PDF library, no server-side renderer. This is that pattern applied to a whole
draft's answers.

- [ ] `web/report.html` + `report.css` + `report.js`, reading `?run=&sweep=`, in the shape
      `web/defend.*` established. Loads `/tokens.css` only.
- [ ] Screen layout IS the print layout — fixed measure, no viewport units, `break-inside:
      avoid` on a claim so a verdict never separates from its sources.
- [ ] Groups by verdict, anachronisms first: on a page somebody prints to act on, the thing
      to act on leads.
- [ ] Carries the scope line, the counts (`raised`, `distinct`, searches), and the
      budget-exhausted note when it applies.
- [ ] A control on a filed sweep opens it.

**Acceptance:** print it to PDF and read the PDF. Every claim's sources are on the same page
as the claim. No verdict appears without what is under it. The scope line survives.

**Watch for:** the defence card shipped three defects that only a printout showed — a raw
category key, an unreduced excerpt, and a live HTML entity. Print this before calling it done.

---

## 3. Export a sweep as CSV

**Depends on:** 1. **Blocks:** 4. **Effort:** S.

- [ ] Pure `star/exports.py`: `sweep_to_csv(document) -> str`. One row per claim per source,
      so a spreadsheet can filter on a domain; claims with no source still get a row.
- [ ] Columns: `scene_numbers, claim, claim_type, verdict, note, source_title, source_url,
      source_excerpt, retrieved_at`.
- [ ] `GET …/sweeps/{sweep_id}.csv`, `Content-Disposition: attachment`, deterministic
      filename from the room title and the sweep date.
- [ ] Injection-safe: a cell beginning `=`, `+`, `-` or `@` is prefixed, because a writer's
      scene text lands in a spreadsheet that will execute it.
- [ ] Quoting and newlines handled by `csv.writer`, never by hand.

**Acceptance:** open it in Excel and Sheets. A claim containing a comma, a quote, a newline
and a leading `=` all survive as text. Round-trips through item 4.

**Watch for:** CSV is the format that most easily reads as more certain than the screen. The
`verdict` column must not be the only provenance a row carries — `source_url` beside it is
what stops a spreadsheet becoming a list of facts.

---

## 4. Import a CSV

**Depends on:** 3. **Effort:** M.

The shape falls out of export: what leaves must be what comes back. The honest scope is
**annotation, not evidence** — a writer marks up an exported sweep in a spreadsheet and brings
their decisions back.

- [ ] Import accepts the export's own columns plus a `writer_note` and a `dismissed` flag.
- [ ] It **never** creates or alters a verdict, a source or an excerpt. Those are the
      department's and are hydrated from a ledger; a row that tried to introduce one is
      refused with that sentence.
- [ ] Matched to an existing filed sweep by `sweep_id` and claim text; a row that matches
      nothing is reported back, not silently dropped.
- [ ] A dry run by default that reports what would change, and a second call that applies it —
      the two-press shape `delete_room` already uses.

**Acceptance:** export a sweep, add notes to three rows in a spreadsheet, re-import, and those
three claims carry the notes with every verdict and source unchanged. A row inventing a source
is refused by name.

**Watch for:** this is the first path where data a user typed becomes part of a room's record.
It must be impossible for an import to make the room look better-sourced than it is.

---

## 5. Continuation stacking

**Depends on:** nothing (parallel with 1–4). **Effort:** L.

The builder's reshape of judge Job 2b, and better than what the judge asked for. A continuing
room does its own research from its own treatment; what stacks is **reading**. Nothing is
re-planned, so nothing can be suppressed — which is the risk
[`continuation-brief.md`](continuation-brief.md) records against re-planning and the reason
that job was held all session.

- [ ] `chain_of(uid, run_id)` in `star/store.py`: the room and every room it follows, root
      first, cycle-safe and depth-capped.
- [ ] `check_scene` and the sweep assemble `room_files` from the WHOLE chain, nearest room
      first. There is no per-check size ceiling — this line claimed one until 2026-08-17
      and no such cap has ever existed in `_room_files`.
- [ ] `ask_room` searches the chain; each finding reports which room it came from.
- [ ] The bible surface stacks the chain's bibles, each under its room's title and era, in
      chain order.
- [ ] Every answer says which room answered it. A chain that cannot tell you where a fact
      came from is a bigger room with worse provenance.
- [ ] `defend_claim` locates across the chain, and the card names the room.

**Acceptance:** build Liverpool 1958 and Hamburg 1960 as two rooms, link them, and check a
Hamburg scene: claims that only Liverpool researched come back answered, attributed to
Liverpool, with no new search spent. Unlinking restores the previous answers exactly.

**Watch for:** the measurement that matters is searches spent. If a chained check does not
spend fewer searches than the same check unchained, the stacking is not working and the
feature is decoration.

---

## 6. Documentation & Security Verification

**Depends on:** 1–5. **Effort:** M.

- [ ] `README.md` names every tool the door serves and every route the app exposes — the
      existing test pins the tools; extend it to routes.
- [ ] `docs/spec.md` gets a cycle-#22 addendum, or is marked as describing #19 and superseded
      in the places these five items changed it.
- [ ] Retention copy re-verified clause by clause against what is actually stored, now that
      sweeps and imported notes are stored. A clause that cannot be verified is CUT, not
      softened — the standing rule.
- [ ] Secrets scan across the working tree and the last 129 commits.
- [ ] `pip-audit` / dependency review; note anything unfixable with why.
- [ ] Deployment: confirm the export and import routes require auth, that CSV download sets a
      non-executable content type, and that no new route is missing from the auth-walk test.
- [ ] Threat model updated for the new surfaces: an uploaded CSV, a downloadable report, and
      a chain that lets one room read another's files.

**Acceptance:** the README describes the app that exists. `curl` proves every new route 401s
without a token. The secrets scan is clean. The threat model names the import path.

---

## Sequencing

**1 → 2 → 3 → 4**, with **5** in parallel — it shares no files with the export chain except
the sweep runner, and touches the store, the check, `ask_room` and the bible surface.

If the night runs short, the order that leaves the most value standing is **1, 5, 2**. Filing
the sweep is the only item that makes a previous night's work durable; stacking is the one the
builder's own screenplay needs, since Liverpool 1958 and Hamburg 1960 want to be two rooms;
and the PDF is the one a judge sees.

Items 3 and 4 are the most self-contained and the easiest to cut.
