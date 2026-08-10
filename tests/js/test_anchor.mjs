// Proves web/anchor.js places a verdict on the right characters, without a
// browser and without a JS test framework.
//
// web/anchor.js is pure and imports nothing, so unlike the web/auth.js tests
// there is no patched import line and no stubbed global here: Node imports the
// file that ships, byte for byte.
//
// What this guards, and why each one is its own named test rather than one
// omnibus scenario. Every line below is a requirement out of
// prd.md > Script Check - The Marked Scene, and every one of them is a place
// where a plausible implementation is wrong in a way a screenshot would not
// show:
//
//   paraphrase  A quote that is not in the scene must reach the rail. Losing it
//               loses a verdict, which is the one failure mode this surface is
//               not allowed to have.
//   whitespace  A scene reflows; an extracted quote does not. A mark that only
//               lands when the newlines agree lands almost never.
//   case        Same argument, one character at a time.
//   repeat      EVERY occurrence is marked, including one that only exists at
//               an offset overlapping another occurrence of the same claim. The
//               extractor returns text and not offsets, so marking the first
//               would assert a position nobody computed.
//   gating      The normalized pass runs only for claims with zero exact hits,
//               so a claim that was found verbatim and then lost pass 3 does
//               not get a fuzzy second attempt at a different position.
//   empty       A claim carrying only whitespace is never anchored. Its
//               normalized form is a single space, which occurs between most
//               words on the page.
//   overlap     Longest wins, the shorter claim goes to the rail, and nothing
//               nests. Nested spans are a defect, not a degraded state.
//   end of      The normalized pass maps a match back through an index map. The
//   scene       off-by-one at the end of that map is invisible until a claim
//               ends where the scene does, and it produces two nested marks
//               rather than an obvious crash.
//   boundary    Where a match begins or ends inside a collapsed whitespace run,
//               which is the one judgment call in normalize().
//   round trip  Concatenating every segment reproduces the scene exactly. If
//               that holds, nothing was dropped and nothing was duplicated.
//   never HTML  Segments carry characters. A pasted <img onerror> is text at
//               every step, and stays text.
//
// Run directly: `node tests/js/test_anchor.mjs` (exit 0 = pass).
// Wired into pytest via tests/test_js_auth.py so pytest stays the single entry
// point.

import { strict as assert } from "node:assert";

import { anchor } from "../../web/anchor.js";

/** The marked segments, in order. */
function marked(segments) {
  return segments.filter((segment) => segment.claim !== undefined);
}

/** Derive each marked segment's raw span by walking the list and accumulating
 *  offsets, which is the only place span indices exist once anchor() has
 *  returned. `scene` is passed so the derived offsets are checked against the
 *  source rather than trusted: a span whose slice does not match its own text
 *  means the segmentation drifted, whatever the individual pieces look like. */
function spansOf(scene, segments) {
  const spans = [];
  let cursor = 0;
  for (const segment of segments) {
    assert.notEqual(segment.text, "", "an empty segment is a gap that should not have been emitted");
    if (segment.claim !== undefined) {
      const span = { start: cursor, end: cursor + segment.text.length, claim: segment.claim };
      assert.equal(
        scene.slice(span.start, span.end),
        segment.text,
        "a marked segment must be the scene's own characters at its own offset"
      );
      spans.push(span);
    }
    cursor += segment.text.length;
  }
  return spans;
}

/** The invariant the whole file rests on. */
function assertReproducesTheScene(scene, segments) {
  assert.equal(
    segments.map((segment) => segment.text).join(""),
    scene,
    "concatenating the segments must reproduce the scene exactly"
  );
}

/** No two accepted spans intersect.
 *
 *  Stated as its own loop because it is the contract, and paired with
 *  assertReproducesTheScene because on a sequential segment list the loop alone
 *  cannot fail: derived offsets are sequential by construction. The round-trip
 *  check is what actually catches a nested or duplicated span, which shows up
 *  as scene text appearing twice. Both are asserted so the contract is written
 *  down and so it is genuinely tested. */
function assertNoIntersections(spans) {
  for (let i = 0; i < spans.length; i += 1) {
    for (let j = i + 1; j < spans.length; j += 1) {
      const a = spans[i];
      const b = spans[j];
      assert.ok(
        !(a.start < b.end && b.start < a.end),
        `spans [${a.start}, ${a.end}) and [${b.start}, ${b.end}) intersect`
      );
    }
  }
}

// -- 1: paraphrase. The verdict reaches the rail rather than vanishing. -----
// Neither pass can find this text: it is not in the scene verbatim, and it is
// not in the scene under collapsed whitespace and lowercase either. The scene
// must come back whole and unmarked, and the claim must come back by reference
// so the rail can read its verdict.
function testParaphraseFallsToTheRail() {
  const scene = "She takes the '61 Impala out past the county line.";
  const claim = { text: "She drives a Chevrolet", verdict: "unverifiable" };

  const { segments, unanchored } = anchor(scene, [claim]);

  assert.deepEqual(segments, [{ text: scene }], "an unmatched claim leaves the scene unmarked");
  assert.equal(unanchored.length, 1);
  assert.equal(unanchored[0], claim, "the rail gets the claim object, not a copy of its text");
  assertReproducesTheScene(scene, segments);
}

// -- 2: whitespace. A reflowed scene still anchors. -------------------------
// The claim carries single spaces; the scene carries a line break and an indent
// in the middle of the same phrase. The mark must cover the scene's characters,
// not the claim's.
function testWhitespaceDriftStillAnchors() {
  const scene = "He checks the\n    '61 Impala's\ttrunk before dawn.";
  const claim = { text: "the '61 Impala's trunk", verdict: "confirmed" };

  const { segments, unanchored } = anchor(scene, [claim]);
  const hits = marked(segments);

  assert.equal(unanchored.length, 0, "a whitespace-only difference is recoverable");
  assert.equal(hits.length, 1);
  assert.equal(
    hits[0].text,
    "the\n    '61 Impala's\ttrunk",
    "the mark covers the scene's whitespace, not the claim's"
  );
  assert.equal(hits[0].claim, claim);
  assertReproducesTheScene(scene, segments);
}

// -- 3: case. -------------------------------------------------------------
// Slug lines are shouted and the extractor is not obliged to shout back.
function testCaseDriftStillAnchors() {
  const scene = "INT. GARAGE - NIGHT\n\nA Bakelite radio hums on the bench.";
  const claim = { text: "a bakelite radio", verdict: "confirmed" };

  const { segments, unanchored } = anchor(scene, [claim]);
  const hits = marked(segments);

  assert.equal(unanchored.length, 0);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].text, "A Bakelite radio", "the mark preserves the scene's casing");
  assertReproducesTheScene(scene, segments);

  // A character whose lowercase form is longer than itself: "İ" lowercases to
  // "i" plus a combining dot. The normalized scene and its index map are built
  // together, one map entry per normalized code unit, so a character like this
  // cannot put them out of step and shift every mark that follows it. The mark
  // below sits 21 characters downstream of that character, which is where a
  // drift of one would show.
  const drifty = "İSTANBUL, 1961.\n\nA Bakelite radio hums.";
  const driftyClaim = { text: "a bakelite radio", verdict: "confirmed" };

  const drift = anchor(drifty, [driftyClaim]);

  assert.equal(marked(drift.segments).length, 1);
  assert.equal(
    marked(drift.segments)[0].text,
    "A Bakelite radio",
    "the index map does not drift past a character whose lowercase form is longer"
  );
  assertReproducesTheScene(drifty, drift.segments);

  // A letter above the basic plane, which JavaScript stores as two code units.
  // normalize() slices the whole code point before lowercasing it, so this
  // folds; lowercasing one half of a surrogate pair at a time would leave it
  // untouched and the claim would reach the rail for a reason nobody could see.
  const astral = "\u{10400} SLATE";
  const astralClaim = { text: "\u{10428} slate", verdict: "confirmed" };

  const wide = anchor(astral, [astralClaim]);

  assert.equal(wide.unanchored.length, 0, "a surrogate pair is case-folded as one letter");
  assert.equal(marked(wide.segments)[0].text, astral);
  assertReproducesTheScene(astral, wide.segments);
}

// -- 4: repeat. Every occurrence, both passes. ------------------------------
// The extractor gives text and not offsets. Marking the first occurrence would
// be an assertion about a position that was never computed, so all of them are
// marked or the claim is not placed at all.
function testEveryOccurrenceOfARepeatedQuoteIsMarked() {
  const exactScene =
    "the Impala pulls in. Behind it, the Impala's twin. Nobody drives the Impala.";
  const exactClaim = { text: "the Impala", verdict: "anachronism" };

  const exact = anchor(exactScene, [exactClaim]);
  const exactHits = marked(exact.segments);

  assert.equal(exactHits.length, 3, "three verbatim occurrences, three marks");
  for (const hit of exactHits) {
    assert.equal(hit.text, "the Impala");
    assert.equal(hit.claim, exactClaim, "every mark carries the same claim object");
  }
  assert.equal(exact.unanchored.length, 0);
  assertReproducesTheScene(exactScene, exact.segments);

  // The same rule has to survive the normalized pass, which is a separate loop
  // and therefore a separate chance to stop at the first hit.
  const casedScene = "THE IMPALA is red. the impala is fast.";
  const casedClaim = { text: "The Impala", verdict: "confirmed" };

  const cased = anchor(casedScene, [casedClaim]);
  const casedHits = marked(cased.segments);

  assert.equal(casedHits.length, 2, "two case-drifted occurrences, two marks");
  assert.deepEqual(
    casedHits.map((hit) => hit.text),
    ["THE IMPALA", "the impala"]
  );
  assert.equal(cased.unanchored.length, 0);
  assertReproducesTheScene(casedScene, cased.segments);
}

// -- 4b: an occurrence that only exists at a shifted offset. ---------------
// The occurrence scan advances by one, not by the needle's length. This is the
// case that decided it, and it is the case a length-advancing scan gets wrong:
// "no no" occurs at 9 and at 12, the longer claim "says no" takes [4, 11), and
// a scan that jumped past the first occurrence never finds the second. The
// claim would then reach the rail as unplaceable while a free occurrence of its
// own text sits three characters to the right of the mark that beat it.
function testAnOccurrenceHiddenBehindAnotherIsStillFound() {
  const scene = "She says no no no and walks out.";
  const longer = { text: "says no", verdict: "confirmed" };
  const periodic = { text: "no no", verdict: "unverifiable" };

  const { segments, unanchored } = anchor(scene, [longer, periodic]);
  const spans = spansOf(scene, segments);

  assertNoIntersections(spans);
  assertReproducesTheScene(scene, segments);
  assert.deepEqual(
    marked(segments).map((segment) => segment.text),
    ["says no", "no no"],
    "the free occurrence is marked even though the first one was taken"
  );
  assert.equal(unanchored.length, 0, "nothing reaches the rail while its own text sits unmarked");
}

// -- 4c: a claim that matched verbatim is not retried loosely. -------------
// The normalized pass is gated on zero EXACT hits, not on zero accepted spans
// (spec.md > The marked scene). A claim that was found verbatim and then lost
// pass 3 to a longer claim has been placed and beaten, which is a different
// outcome from never having been found. Here "The Colt Navy" is beaten at the
// only place it appears verbatim, and the lowercase occurrence later in the
// scene is NOT a second chance for it: re-searching a beaten claim loosely
// would let a fuzzy runner-up outrank the verbatim placement that lost.
function testAClaimThatMatchedVerbatimIsNotRetriedLoosely() {
  const scene = "The Colt Navy revolver sits there. Later, the colt navy appears again.";
  const longer = { text: "The Colt Navy revolver", verdict: "confirmed" };
  const beaten = { text: "The Colt Navy", verdict: "unverifiable" };

  const { segments, unanchored } = anchor(scene, [longer, beaten]);

  assert.deepEqual(
    marked(segments).map((segment) => segment.text),
    ["The Colt Navy revolver"],
    "the beaten claim does not pick up the lowercase occurrence on a second pass"
  );
  assert.deepEqual(unanchored, [beaten]);
  assertReproducesTheScene(scene, segments);
}

// -- 4d: a claim carrying no text worth anchoring. -------------------------
// A claim whose text is empty or all whitespace normalizes to a single space,
// and a single space occurs between most words in the scene. Anchoring it would
// not be a degraded mark, it would be a wrong one on nearly every gap in the
// page, so it never becomes a candidate and lands in the rail instead.
function testAWhitespaceOnlyClaimIsNeverAnchored() {
  const scene = "She takes the '61 Impala out past the county line.";
  const single = { text: " ", verdict: "unverifiable" };
  const run = { text: "\n\t  ", verdict: "unverifiable" };
  const empty = { text: "", verdict: "unverifiable" };

  const { segments, unanchored } = anchor(scene, [single, run, empty]);

  assert.deepEqual(segments, [{ text: scene }], "not one character of the scene is marked");
  assert.deepEqual(unanchored, [single, run, empty]);
}

// -- 5: overlap. Longest wins, the loser goes to the rail, nothing nests. ---
// Three claims fight over one phrase and a fourth stands clear of it, so the
// test also proves the resolution drops only what actually clashes.
function testLongestMatchWinsAndTheShorterClaimGoesToTheRail() {
  const scene =
    "He carries a Colt Single Action Army revolver, and she carries a derringer.";
  const longest = { text: "a Colt Single Action Army revolver", verdict: "confirmed" };
  const nested = { text: "Single Action Army", verdict: "confirmed" };
  const straddling = { text: "Army revolver, and she", verdict: "unverifiable" };
  const clear = { text: "a derringer", verdict: "anachronism" };

  const { segments, unanchored } = anchor(scene, [nested, straddling, longest, clear]);
  const spans = spansOf(scene, segments);

  assertNoIntersections(spans);
  assertReproducesTheScene(scene, segments);

  assert.deepEqual(
    spans.map((span) => scene.slice(span.start, span.end)),
    ["a Colt Single Action Army revolver", "a derringer"],
    "the longest candidate takes the phrase; the unrelated claim keeps its own"
  );
  assert.deepEqual(
    unanchored,
    [nested, straddling],
    "a nested claim and a straddling one both go to the rail, in input order"
  );
  assert.equal(
    marked(segments).filter((segment) => segment.claim === longest).length,
    1,
    "the winner is marked once, not once per claim it beat"
  );
}

// -- 5b: equally long candidates are resolved leftmost first. --------------
// The candidate sort tie-breaks on start, then on the claim's position in the
// input. Neither key is decoration: with the first removed, which claim owns a
// line would depend on the order the extractor happened to list them; with the
// second removed, it would depend on whatever the engine's sort does with a
// tie. Synthetic text, because an extractor emitting two overlapping quotes of
// exactly equal length is rare and the rule still has to be a rule. The claims
// are handed over rightmost-first so a resolution that quietly fell back to
// input order would pick the other one.
function testEquallyLongCandidatesAreResolvedLeftmostFirst() {
  const scene = "alpha beta gamma delta";
  const rightward = { text: "beta gamma delta", verdict: "confirmed" };
  const leftward = { text: "alpha beta gamma", verdict: "confirmed" };
  assert.equal(rightward.text.length, leftward.text.length, "the case only means anything as a tie");

  const { segments, unanchored } = anchor(scene, [rightward, leftward]);

  assert.deepEqual(
    marked(segments).map((segment) => segment.text),
    ["alpha beta gamma"],
    "leftmost of the equally long takes the mark"
  );
  assert.deepEqual(unanchored, [rightward]);
  assertReproducesTheScene(scene, segments);
}

// -- 5c: two claims carrying the same text. --------------------------------
// The verifier can return two verdicts on the same quote. Both cannot own the
// same characters, and splitting the occurrences between them would hand each
// claim a position nobody computed, which is the same mistake as marking only
// the first occurrence of a repeat. So the first claim in the extractor's own
// order takes every occurrence and the second reaches the rail, where its
// verdict is still read.
function testTwoClaimsWithTheSameTextCannotBothOwnIt() {
  const scene = "The Impala is red. The Impala is fast.";
  const first = { text: "The Impala", verdict: "confirmed" };
  const second = { text: "The Impala", verdict: "anachronism" };

  const { segments, unanchored } = anchor(scene, [first, second]);
  const hits = marked(segments);

  assert.equal(hits.length, 2, "both occurrences are marked");
  for (const hit of hits) {
    assert.equal(hit.claim, first, "one claim owns every occurrence of its own text");
  }
  assert.deepEqual(unanchored, [second]);
  assertReproducesTheScene(scene, segments);
}

// -- 6: the end of the scene. The index-map off-by-one. --------------------
// A normalized match is mapped back as [map[i], map[j-1] + 1). Writing
// [map[i], map[j]) reads one entry past the match, which is undefined when the
// match ends where the scene does. Nothing throws: the end becomes undefined,
// every overlap comparison against it is false, and a nested claim is accepted
// alongside the winner. The scene then comes back with its last phrase printed
// twice, which only the round-trip check sees. Writing map[j-1] without the +1
// is the other half of the same mistake and drops the final character, which
// only the text assertion sees. Both are asserted here.
function testANormalizedMatchAtTheEndOfTheSceneKeepsItsLastCharacter() {
  const scene = "INT. GARAGE - NIGHT\n\nShe wipes down a 1961 IMPALA";
  const longest = { text: "a 1961 impala", verdict: "anachronism" };
  const nestedExact = { text: "1961 IMPALA", verdict: "confirmed" };

  const { segments, unanchored } = anchor(scene, [longest, nestedExact]);
  const hits = marked(segments);

  assertReproducesTheScene(scene, segments);
  assertNoIntersections(spansOf(scene, segments));

  assert.equal(hits.length, 1, "one mark, not a winner plus the claim it should have beaten");
  assert.equal(
    hits[0].text,
    "a 1961 IMPALA",
    "the last character of the scene belongs to the mark that reaches it"
  );
  assert.equal(segments[segments.length - 1], hits[0], "nothing is emitted after the final span");
  assert.deepEqual(unanchored, [nestedExact]);

  // The same boundary with no competitor, so a dropped final character cannot
  // hide behind an overlap decision.
  const alone = anchor(scene, [longest]);
  assert.equal(marked(alone.segments)[0].text, "a 1961 IMPALA");
  assertReproducesTheScene(scene, alone.segments);
}

// -- 7: a span boundary landing inside a collapsed whitespace run. ---------
// normalize() maps a collapsed run to the run's FIRST raw index, which is the
// character that produced the space. That choice is only visible when a match
// begins or ends on a collapsed space, and it produces a deliberate asymmetry
// documented in web/anchor.js: a span that BEGINS on a collapsed space takes
// the whole run, and a span that ENDS on one takes a single character and
// leaves the rest outside. The end is the side worth protecting, because a
// mark that swallows a paragraph break draws a highlight across the blank line
// between two lines of a script.
function testACollapsedRunIsTakenWholeAtTheStartAndOneCharacterAtTheEnd() {
  const endScene = "He drew the Colt Navy.\n\n\nTHEN she left.";
  const endClaim = { text: "the colt navy. ", verdict: "confirmed" };

  const end = anchor(endScene, [endClaim]);
  const endHits = marked(end.segments);

  assert.equal(endHits.length, 1);
  assert.equal(
    endHits[0].text,
    "the Colt Navy.\n",
    "a match ending on a collapsed run takes one whitespace character"
  );
  assert.equal(
    end.segments[end.segments.length - 1].text,
    "\n\nTHEN she left.",
    "the rest of the run stays outside the mark"
  );
  assertReproducesTheScene(endScene, end.segments);

  const startScene = "FADE IN.\n\n\nColt Navy in his hand.";
  const startClaim = { text: " colt navy", verdict: "confirmed" };

  const start = anchor(startScene, [startClaim]);
  const startHits = marked(start.segments);

  assert.equal(startHits.length, 1);
  assert.equal(
    startHits[0].text,
    "\n\n\nColt Navy",
    "a match beginning on a collapsed run opens where the run opens"
  );
  assertReproducesTheScene(startScene, start.segments);
}

// -- 8: the round-trip property, over everything above and a few more. -----
// If concatenating the segments reproduces the scene, the segmentation dropped
// nothing and duplicated nothing. Cheap to assert and it covers cases nobody
// thought to write a named test for.
function testSegmentsAlwaysReproduceTheScene() {
  const cases = [
    ["", []],
    ["", [{ text: "anything" }]],
    ["A scene with no claims at all.", []],
    ["A scene with a null in the claim list.", [null, { text: "scene" }]],
    ["A claim whose text is empty.", [{ text: "" }]],
    ["A claim that is nothing but spaces.", [{ text: "   " }]],
    ["\n\n\t  \r\n  ", [{ text: "nothing here" }]],
    ["Repeats: red red red red.", [{ text: "red" }]],
    ["Overlaps: alpha beta gamma.", [{ text: "alpha beta" }, { text: "beta gamma" }]],
    ["Nested: alpha beta gamma.", [{ text: "alpha beta gamma" }, { text: "beta" }]],
    ["Case and space:  ALPHA\n\nBETA ", [{ text: "alpha beta" }]],
    ["Ends at the end: BETA", [{ text: "beta" }]],
    ["Starts at the start: BETA", [{ text: "starts at" }]],
    ["Emoji hold their halves: 🎬 slate 🎬", [{ text: "🎬 SLATE 🎬" }]],
    ["Accents: CAFÉ de la Paix", [{ text: "café de la paix" }]],
    ["Windows newlines\r\nin the middle", [{ text: "newlines in" }]],
  ];

  for (const [scene, claims] of cases) {
    const { segments, unanchored } = anchor(scene, claims);
    assertReproducesTheScene(scene, segments);
    assertNoIntersections(spansOf(scene, segments));
    for (const claim of unanchored) {
      assert.ok(claims.includes(claim), "the rail only ever contains claims it was given");
    }
  }

  // Not an array, and not a string. The renderer must not be able to hand this
  // function something that throws on a surface whose whole job is showing a
  // reader what happened.
  assert.deepEqual(anchor(undefined, undefined), { segments: [], unanchored: [] });
  assert.deepEqual(anchor(null, null), { segments: [], unanchored: [] });
}

// -- 9: segments are data, never markup. ----------------------------------
// This is the H1 XSS's other door. anchor() escapes nothing because anchor()
// produces nothing to escape: the pasted characters come back as the pasted
// characters, and web/scriptcheck.js turns them into text nodes.
function testSegmentsAreDataAndNeverMarkup() {
  const payload = "<img src=x onerror=alert(1)>";
  const scene = `She holds a sign reading ${payload} and laughs.`;
  const claim = { text: payload, verdict: "unverifiable" };

  const { segments } = anchor(scene, [claim]);
  const hits = marked(segments);

  assert.equal(hits.length, 1);
  assert.equal(hits[0].text, payload, "the payload comes back exactly as pasted, unescaped");
  assertReproducesTheScene(scene, segments);

  for (const segment of segments) {
    assert.deepEqual(
      Object.keys(segment).sort(),
      segment.claim === undefined ? ["text"] : ["claim", "text"],
      "a segment carries text and at most a claim, never a rendered string"
    );
    assert.equal(typeof segment.text, "string");
  }
}

testParaphraseFallsToTheRail();
testWhitespaceDriftStillAnchors();
testCaseDriftStillAnchors();
testEveryOccurrenceOfARepeatedQuoteIsMarked();
testAnOccurrenceHiddenBehindAnotherIsStillFound();
testAClaimThatMatchedVerbatimIsNotRetriedLoosely();
testAWhitespaceOnlyClaimIsNeverAnchored();
testLongestMatchWinsAndTheShorterClaimGoesToTheRail();
testEquallyLongCandidatesAreResolvedLeftmostFirst();
testTwoClaimsWithTheSameTextCannotBothOwnIt();
testANormalizedMatchAtTheEndOfTheSceneKeepsItsLastCharacter();
testACollapsedRunIsTakenWholeAtTheStartAndOneCharacterAtTheEnd();
testSegmentsAlwaysReproduceTheScene();
testSegmentsAreDataAndNeverMarkup();

console.log("tests/js/test_anchor.mjs: all assertions passed");
