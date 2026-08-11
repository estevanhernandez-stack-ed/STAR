// Guards the order of the citation card against the answer sinking again.
//
// THE FINDING. F-002, rule 10: the one line a writer came for rendered FOURTH —
// stamp, claim, VERDICT_READING, then the fact — and the fact and the gloss
// above it were both el("p", "rail-line", …), byte-identical, so nothing in the
// type ranked the answer over the explanation of it. Measured before the fix,
// the answer was 21px of a 1730px card, the gloss above it 2x that, and the
// standing caveat 4x.
//
// WHAT "THE ANSWER" IS, decided 2026-08-11 and the reason this could finally be
// built: the source quotation. star/agents/script_check.py:196-199 already told
// the verifier so — on confirmed and anachronism the note is OPTIONAL, "the
// qualifier a writer needs" — and 4 of the 9 claims in the filed Gdansk check
// carry no note at all. A card design that assumes a note is present has no case
// for those four, which is why every earlier attempt at this stalled.
//
// SO THE TESTS BELOW ARE MOSTLY ABOUT ORDER, and about two things that must NOT
// happen: no sentence is invented to fill a missing note, and the caveat's
// second sentence is not lost in the move. That clause carries rule 2's
// click-through beat, scriptcheck.js argues it "cannot be cut", and the
// measuring stick records that an earlier relocation was rejected for dropping
// exactly it.
//
// Run directly: `node tests/js/test_answer_outranks_gloss.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

import { loadPatchedModule, readSource, stubDocument, walk, withClass } from "./_scriptcheck_module.mjs";

globalThis.document = stubDocument();

const { renderCheckResult } = await import(loadPatchedModule());

const CITED = [{ url: "https://example.org/a", title: "A source", excerpt: "Some real prose about it." }];

function card(overrides = {}) {
  const payload = {
    scene: "the line itself",
    claims: [
      {
        text: "the line itself",
        verdict: "confirmed",
        claim_type: "technology",
        citations: CITED,
        citation_sources: ["search"],
        ...overrides,
      },
    ],
  };
  return withClass(renderCheckResult(payload), "rail-card")[0];
}

/** The card's element children, in order, by class. */
const order = (node) =>
  node.childNodes
    .filter((n) => n.nodeType === 1)
    .map((n) => String(n.getAttribute("class") || "").split(/\s+/)[0]);

const textOf = (node) =>
  walk(node)
    .filter((n) => n.nodeType === 3)
    .map((n) => n.data)
    .join("");

/* 1 — the scope is a slug in the head, not a paragraph above the answer. -- */

const confirmed = card();
const head = withClass(confirmed, "rail-head")[0];
assert.ok(head, ".rail-head should still exist");

const slug = withClass(confirmed, "rail-slug");
assert.equal(slug.length, 1, "exactly one slug");
assert.ok(
  walk(head).includes(slug[0]),
  "the slug rides in the head with the stamp it qualifies, not in the body"
);
assert.match(
  textOf(slug[0]),
  /as read from the sources below/,
  "confirmed keeps the source-relativizer the register asked for"
);

// The stamp is still scoped, which is what the file header requires of every
// card. The slug is what satisfies it now.
const stamp = withClass(confirmed, "verdict-stamp")[0];
assert.ok(walk(head).includes(stamp), "the stamp and its scope are adjacent");

/* 2 — the gloss paragraph is gone, and nothing replaced it. -------------- */

const source = readSource().replace(/\r\n/g, "\n");
assert.doesNotMatch(
  source.replace(/\/\*[\s\S]*?\*\//g, ""),
  /VERDICT_READING/,
  "the sentence form is gone from the code, not merely unused"
);
assert.doesNotMatch(
  textOf(confirmed),
  /The department read this line/,
  "and gone from the card"
);

/* 3 — a card with no note invents nothing. ------------------------------- */

// This is the case the decision turns on: 4 of 9 real claims. The source
// answers them, and the card must not manufacture a sentence to look complete.
const noNote = card({ note: "" });
const lines = withClass(noNote, "rail-line");
assert.equal(
  lines.length,
  0,
  "no note, no prose line — the quotation below is the answer, and a sentence " +
    "written to fill the gap would be the app asserting something nobody wrote"
);
// It is still a complete card: stamp, scope, claim, evidence.
assert.equal(withClass(noNote, "rail-slug").length, 1, "still scoped");
assert.equal(withClass(noNote, "rail-citations").length, 1, "still cited");

/* 4 — the caveat follows the evidence it describes. ---------------------- */

const shape = order(confirmed);
const legendAt = shape.indexOf("rail-sublegend");
const citesAt = shape.indexOf("rail-citations");
const caveatAt = shape.indexOf("rail-caveat");
assert.ok(legendAt > -1 && citesAt > -1 && caveatAt > -1, `all three present, got ${shape}`);
assert.ok(
  citesAt < caveatAt,
  `rule 10: the answer outranks the disclaimer. Got order ${shape.join(" → ")}`
);
assert.ok(legendAt < citesAt, "the legend still introduces the list");

// And the claim still comes before the evidence for it.
assert.ok(shape.indexOf("rail-claim") < citesAt, "the claim precedes what answered it");

/* 5 — the clause that cannot be cut, is not cut. ------------------------- */

assert.match(
  textOf(withClass(confirmed, "rail-caveat")[0]),
  /opens where it came from, so you can read it and judge for yourself/,
  "rule 2's click-through beat. scriptcheck.js argues this sentence cannot be " +
    "cut and the stick records an earlier relocation rejected for dropping it"
);
assert.doesNotMatch(
  textOf(withClass(confirmed, "rail-caveat")[0]),
  /Each source below/,
  "the direction word was the only part that depended on position, and the " +
    "paragraph is no longer above anything"
);

/* 6 — a card with no sources keeps its caveat where it is. --------------- */

const unsourced = card({ verdict: "unverifiable", citations: [], citation_sources: [] });
const bareShape = order(unsourced);
assert.equal(
  bareShape.indexOf("rail-citations"),
  -1,
  "nothing to list"
);
assert.match(
  textOf(withClass(unsourced, "rail-caveat")[0]),
  /came back with nothing to read/,
  "the no-sources variant is written for exactly this card"
);
assert.match(
  textOf(withClass(unsourced, "rail-slug")[0]),
  /^not settled$/,
  "and its slug claims nothing about sources it does not have"
);

/* 7 — the quantifier the slug asserts is backed by a mechanism. ---------- */

// "the sources below" is a definite plural, and the measuring stick's
// amendment "a mark has no quantifier" exists because the intake once shipped
// one a payload could contradict. It cannot be contradicted here: verdicts.py
// downgrades a confirmed or anachronism with no citations BEFORE the payload is
// written. Assert the two verdicts that promise sources are exactly the two the
// server guards, so this stays true if someone edits either list.
for (const verdict of ["confirmed", "anachronism"]) {
  assert.match(
    textOf(withClass(card({ verdict }), "rail-slug")[0]),
    /sources below/,
    `${verdict} promises sources`
  );
}
const verdicts = (await import("node:fs")).readFileSync(
  new URL("../../star/verdicts.py", import.meta.url),
  "utf8"
);
assert.match(
  verdicts,
  /_NEEDS_A_SOURCE = \(Verdict\.CONFIRMED\.value, Verdict\.ANACHRONISM\.value\)/,
  "the server's guarded set must stay exactly the two verdicts whose slug " +
    "promises sources — if a third joins the slugs, or one leaves this tuple, " +
    "the card starts asserting a source it may not have"
);
assert.match(
  verdicts,
  /if verdict in _NEEDS_A_SOURCE and not citations:\s*\n\s*verdict = Verdict\.UNVERIFIABLE\.value/,
  "and the downgrade itself has to still happen"
);

console.log("test_answer_outranks_gloss.mjs: 22 assertions passed");
