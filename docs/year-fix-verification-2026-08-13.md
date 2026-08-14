# Year-fix verification — third attempt, judged 2026-08-13

Room `1fd837bdd99e`. Sweep 1 filed as `6fce0e172dcc`, sweep 2 as `e6f57c022783`. Instruction was to assume the fix did not work; the verdicts below are read against that assumption.

## 1. Spent or written beyond the two sweeps

Nothing. Two `sweep_draft` calls, one search each (`search_count: 1` on both), both marked. The two sweeps are stored with the room, which is inherent to the tool. No other call was made against STAR.

## 2. Sweep 1, claim by claim — verdict, note, and what the desk compared against

**`Vox AC30 amplifier`** (scenes [1, 2]) — verdict `anachronism`. Note, exact: **"Introduced in 1959, so the Vox AC30 did not exist in 1958."** Compared against: the *scene's year*. The note does the arithmetic itself — introduction year, then the year that breaks it, in one sentence. Two details worth the coder's attention: the claim carries `scenes: [1, 2]`, so the several-years rule ran (asserted 1958 and 1961, failed on 1958, whole claim failed); and `citation_sources: ["room"]` — the disproof came from the room's own files, whose Vox AC30 Wikipedia source was always sufficient. The evidence never changed between the three attempts; only what the desk compared against did.

**`KAISERKELLER`** (scene [2]) — `confirmed`. Note: "Music club at 36 Große Freiheit in St. Pauli, Hamburg, opened in 1959." Compared against: the scene's year implicitly and correctly — opened 1959, scene is 1961, no strain. Room-sourced.

**`1961`** (scene [2]) — `confirmed`, claim_type `timing`. Note, exact: **"1961 is valid within the story setting."** Compared against: **the era. This is the banned reasoning, verbatim in shape.** See §5. Note also what this claim *is*: the scene heading's own year, extracted as a claim and then judged against the era — the year machinery examining itself and using the old standard to do it.

**`Hamburg`** (scene [2]) — `confirmed`. Note: "Major port city in West Germany." Timeless geography; nothing to compare; fine.

**`LIME STREET`** (scene [3]) — `confirmed`. Note: "Major thoroughfare in central Liverpool." Room-sourced. Fine.

**`Liverpool Empire Theatre`** (scene [3]) — `confirmed`. Note: "Major venue on Lime Street in Liverpool, operating in 1958." Compared against: the scene's year, by name. `citation_sources: ["room", "room"]` — zero searches for it.

Dedup line: 7 raised, 6 distinct — the two AC30 assertions merged into one claim spanning both scenes, which is precisely what bar 1 needed to even be testable.

## 3. The three bars

**Bar 1 — PASS.** The AC30 is `anachronism`, not `confirmed`. Asserted in 1958 and 1961, failed because of 1958.

**Bar 2 — PASS.** "Introduced in 1959, so the Vox AC30 did not exist in 1958" names the breaking year and does the arithmetic. No reader math required.

**Bar 3 — PASS.** The Empire is `confirmed`, from the room's files (`["room", "room"]`), and its note anchors to 1958 rather than the era. The fix did not buy the anachronism by making the desk timid: five of six claims still confirmed, all on their merits.

## 4. The traps

**Scene 2 (no year) behaved as 1958.** The Stratocaster came back `confirmed` with the note "introduced in 1954 and was in active production **throughout 1958**" — and both citations are literally 1958-Stratocaster pages, meaning even the *searches* were year-anchored. Inheritance from scene 1 reached the desk and the search layer both. (Caveat for §6: this proves inheritance on a claim that passes; the sharper proof is a claim that *fails only* on an inherited year.)

**Scene 3 ("born in 1931" in dialogue):** produced no claims at all, and no trace of 1931 appears anywhere in either sweep's results — no timing claim, no note reasoning from 1931. No evidence the parser read the dialogue year as the scene's year. Honest limit: since the scene yielded zero claims, there was also no surface on which a wrong inherited year could have shown. Absence of leakage confirmed; the year the scene was internally carried as is unobservable from outside.

**Scene 4 ("ROOM 402", "1200 in notes"):** no claims, no dates invented from either number. Same observability caveat, same clean result.

**Transistor radio (scene 1, the control):** `confirmed`, note "introduced in 1954 … available in Britain and worldwide by 1958" — year-anchored, correct, fresh-searched.

## 5. Notes still reasoning from the era

**One.** The `1961` timing claim: **"1961 is valid within the story setting."** That is "fits the era" wearing different words, surviving on a claim class the fix's authors probably never saw — the extractor turning a scene heading's year into a claim of its own, which the verifier then judges the only way a bare year *can* be judged, against the era. Two defects folded together: the heading year should arguably never be extracted as a world-claim (it is the writer's declaration, the thing the fix reads as *input*), and if it is extracted, "valid within the story setting" is a circular stamp — the era was derived from the treatment, so this confirms the writer's setting against the writer's setting. Inconsistently, sweep 2's scene 1 heading year `(1958)` was *not* extracted as a claim. Same syntax, different behavior between two sweeps minutes apart.

## 6. What I would try next, with one slot

One sweep, four scenes, three knives. Scene 1: `INT. TOP TEN CLUB - NIGHT (1962)`, no claims worth checking. Scene 2: **no year, containing the AC30** — the fixture proved inheritance can confirm (Stratocaster); this forces it to *convict* on an inherited year alone, with no stated year anywhere on the claim. If the AC30 comes back confirmed here, inheritance reaches the search layer but not the verdict logic. Scene 3: `INT. CASBAH CELLAR - NIGHT` with the action line **`SUPER: "1958"`** and a claim true in 1962 but false in 1958 — screenwriters date scenes with SUPERs and `FLASHBACK TO:` far more often than with parenthetical years in the slug; if the carrier only reads the slug, the inherited 1962 silently overrides the SUPER's 1958 and the verdict is wrong *with the writer's own date on the page*. Scene 4: `INT. CAVERN CLUB - NIGHT (1958-1962)` — a montage range in the heading itself; a range is not a year, and whichever way the parser resolves it (first year, last year, era, crash) is currently unspecified behavior about to be specified by accident.

## Verdict

The third attempt worked where the first two failed: the desk now compares against the scene's year, names it in the note, fails a multi-year claim on its worst year, and did not go timid to get there. What remains is one leak (§5) on a claim class outside the fixture, and one untested carrier path (§6, the SUPER/flashback convention) that real screenplays use more than the one the fix reads.
