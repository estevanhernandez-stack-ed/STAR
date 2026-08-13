// A Fountain draft splits into the scenes a writer would recognise.
//
// WHAT IS ACTUALLY AT RISK. This decides what text gets sent to a check, so
// its failure modes are not cosmetic:
//
//   1. A missed heading silently merges two scenes, and the writer is billed
//      for a check on a scene they did not ask about.
//   2. A false heading splits one scene in half, and each half is checked
//      without the context that made it make sense.
//   3. Text altered on the way through means the department checked something
//      the writer never wrote, and web/scriptcheck.js renders the scene it was
//      given on the assumption that it is the scene that was submitted.
//
// Every case below is from the Fountain 1.1 syntax reference or from the shape
// real exporters produce.
//
// Run directly: `node tests/js/test_fountain.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = new URL("../../", import.meta.url);
const { scenes, sceneKey } = await import(
  pathToFileURL(fileURLToPath(new URL("web/fountain.js", REPO_ROOT))).href
);

/* 1 — the ordinary draft. ------------------------------------------------ */

const DRAFT = `Title: The Substitute Sync
Credit: Written by
Author: E. Hernandez

INT. ABBEY ROAD STUDIO TWO - DAY

Jimmy laces the boots. They pinch.

JIMMY
They're a size too small.

EXT. DRURY LANE - LATER

Rain on the pavement outside Anello & Davide.

INT. VAN - NIGHT

The city goes past.`;

const parsed = scenes(DRAFT);

assert.equal(parsed.length, 3, "three headings, three scenes");
assert.deepEqual(
  parsed.map((s) => s.heading),
  [
    "INT. ABBEY ROAD STUDIO TWO - DAY",
    "EXT. DRURY LANE - LATER",
    "INT. VAN - NIGHT",
  ]
);
assert.deepEqual(parsed.map((s) => s.index), [1, 2, 3], "numbered as a writer counts");

assert.ok(
  parsed[0].text.startsWith("INT. ABBEY ROAD STUDIO TWO - DAY"),
  "the scene INCLUDES its heading — that is what a writer means by a scene"
);
assert.match(parsed[0].text, /They're a size too small\./, "and its dialogue");
assert.doesNotMatch(parsed[0].text, /EXT\. DRURY LANE/, "and stops at the next one");
assert.doesNotMatch(parsed[0].text, /Title:/, "the title page is not a scene");
assert.doesNotMatch(
  parsed.map((s) => s.text).join("\n"),
  /E\. Hernandez/,
  "and checking it would spend a search verifying the writer's own name"
);

/* 2 — text is verbatim. -------------------------------------------------- */

const ODD = `INT. SHOP - DAY

    Indented action.   Trailing spaces.

A line with <img src=x onerror=alert(1)> in it.

EXT. STREET - DAY

After.`;

const [shop] = scenes(ODD);
assert.match(shop.text, /    Indented action\./, "indentation survives");
assert.match(
  shop.text,
  /<img src=x onerror=alert\(1\)>/,
  "and so does a hostile paste, as CHARACTERS — this file must not become the " +
    "thing that sanitises, because web/scriptcheck.js is built on never " +
    "assembling markup and a splitter that 'helpfully' escaped here would " +
    "leave the stored scene disagreeing with the draft"
);

/* 3 — the headings the spec allows, and the ones it does not. ------------- */

const FORMS = `INT. HOUSE - DAY

One.

EXT./INT. CAR - NIGHT

Two.

I/E. BOAT - DAWN

Three.

EST. SKYLINE - DAWN

Four.

.SNOW GLOBE

Five, forced with a period.

int. lowercase house - day

Six. Fountain accepts it and a parser that dropped it would lose a page.`;

assert.equal(scenes(FORMS).length, 6, "every heading form the spec allows");
assert.equal(scenes(FORMS)[4].heading, "SNOW GLOBE", "the forcing period is not part of the slug");

/* 4 — what must NOT start a scene. --------------------------------------- */

const TRAPS = `INT. ROOM - DAY

He said INT. was short for interior, then kept talking without a pause.
EXT. is the other one.

The sentence above has no blank line after it, so it is action, not a heading.

...trailing off into an ellipsis

Still the same scene.`;

const trapped = scenes(TRAPS);
assert.equal(
  trapped.length,
  1,
  "a heading needs the blank line after it; without that rule a line of " +
    "action starting INT. splits a scene in half and each half is checked " +
    "without the context that made it make sense"
);
assert.match(trapped[0].text, /\.\.\.trailing off/, "two periods is an ellipsis, not a forced heading");

// The other half of the same rule, and the half a mutation caught missing: a
// slug with action glued straight underneath it. The spec requires the blank
// line after a heading, and without that requirement this is a scene — so a
// draft whose writer forgot the blank line would split where they did not.
assert.deepEqual(
  scenes("INT. ROOM - DAY\nHe waits with no blank line.\n\nMore."),
  [],
  "a heading needs the blank line AFTER it as well as before"
);

/* 5 — the boneyard is invisible. ----------------------------------------- */

const BONEYARD = `INT. ROOM - DAY

Kept.

/*
EXT. CUT SCENE - DAY

This whole scene was cut and is not in the draft.
*/

Still the first scene.

EXT. STREET - DAY

Second.`;

const boned = scenes(BONEYARD);
assert.equal(boned.length, 2, "a heading inside a comment is not a scene");
assert.doesNotMatch(boned.map((s) => s.text).join("\n"), /CUT SCENE/);
assert.match(boned[0].text, /Still the first scene\./, "and the text around it survives");

/* 5b — the shape a real draft actually uses. ----------------------------- */
//
// From The Beat That Shook The Void (doctor-whom, 24 scenes), which marks its
// scene boundaries with commented banners that CONTAIN a scene heading. Every
// one of that draft's scenes is preceded by one. Had the boneyard not been
// stripped before headings are looked for, the banner's heading would have
// opened a phantom scene four lines above the real one — twenty-four times.
//
// This is the case that made the boneyard rule load-bearing rather than tidy,
// and it was found by running the parser over a draft written by somebody who
// had never heard of it.

const BANNERED = `INT. CASBAH CELLAR — NIGHT

The band plays.

SMASH CUT TO:


/*-------------------------------------------------------------
SCENE 2 — THE VORTEX / IN TRANSIT
INT. TARDIS — IN FLIGHT
TARGET RUNTIME: 10:00 - 15:00
[[ Doctor and Rose, alone. They think it's over. ]]
-------------------------------------------------------------*/

SUPER: "Two years later. Hamburg, West Germany — 1960."

INT. TARDIS — IN FLIGHT

The time vortex churns on the scanner.`;

const bannered = scenes(BANNERED);
assert.equal(bannered.length, 2, "two scenes, not three — the banner is not one");
assert.deepEqual(
  bannered.map((s) => s.heading),
  ["INT. CASBAH CELLAR — NIGHT", "INT. TARDIS — IN FLIGHT"]
);
assert.match(
  bannered[0].text,
  /SUPER: "Two years later/,
  "the SUPER after the banner belongs to the scene before it, because the " +
    "banner was never there as far as a reader is concerned"
);
assert.doesNotMatch(
  bannered.map((s) => s.text).join("\n"),
  /TARGET RUNTIME|SCENE 2 —/,
  "and nothing from inside the banner reaches a check"
);
assert.match(
  bannered[1].text,
  /The time vortex churns/,
  "the REAL heading four lines below opens the second scene"
);

/* 6 — the shapes that are not a draft at all. ---------------------------- */

for (const input of ["", null, undefined, "Just a paragraph a writer pasted.", "\n\n\n"]) {
  assert.deepEqual(
    scenes(input),
    [],
    `${JSON.stringify(input)} has no headings, and an empty list is the ` +
      "signal the caller uses to treat a paste as one scene. A draft is not " +
      "the only thing pasted here and this module does not get to insist"
  );
}

/* 7 — a draft ending on its last heading. -------------------------------- */

assert.equal(
  scenes("INT. ROOM - DAY").length,
  1,
  "end of file counts as the blank line after — a draft that stops on a " +
    "heading still has a heading there"
);

/* 8 — the key that says what has already been checked. ------------------- */

assert.equal(sceneKey("INT. ROOM - DAY\n\nHe waits."), sceneKey("INT. ROOM - DAY\n\nHe waits."));
assert.notEqual(
  sceneKey("INT. ROOM - DAY\n\nHe waits."),
  sceneKey("INT. ROOM - DAY\n\nShe waits."),
  "a rewritten scene is new work"
);
assert.equal(
  sceneKey("INT. ROOM - DAY\n\nHe waits."),
  sceneKey("INT.  ROOM  -  DAY\n\n\nHe waits.  "),
  "a re-export that reflowed the margins is NOT new work — otherwise every " +
    "scene comes back unchecked the first time a writer changes editors"
);
assert.match(sceneKey("anything"), /^[0-9a-f]{8}$/, "eight hex digits, always");

console.log("ok - a Fountain draft splits into the scenes a writer would recognise");
