// The anchor matcher: where a verdict meets the line it is about.
//
//   anchor(scene, claims) -> { segments, unanchored }
//
// `segments` is a flat, ordered list of `{text}` and `{text, claim}`. It is
// DATA. It is never HTML, and that is the whole reason this file returns the
// shape it does. web/scriptcheck.js walks the list with document.createTextNode
// and real <mark> elements. Assembling an HTML string out of scene text here
// would reopen the H1 XSS through a different door
// (docs/superpowers/specs/2026-08-09-star-gui-design.md:312-318), and it would
// do it on the one surface where the reader is pasting untrusted text on
// purpose. Nothing below escapes anything, because nothing below produces
// markup: a `<img src=x onerror=alert(1)>` sitting inside a claim comes back as
// the characters that were pasted, and stays characters all the way to the DOM.
//
// The file is pure. No document, no window, no imports, no I/O. That is what
// lets tests/js/test_anchor.mjs import exactly what ships with no patched
// import line and no stubbed globals, the way web/auth.js's tests cannot
// because auth.js imports "/config.js" (see tests/js/_auth_module.mjs).
//
// THE INVARIANT, and the one worth checking first when something looks wrong:
// concatenating every segment's `text` in order reproduces `scene` byte for
// byte. Accepted spans never overlap, never nest, and never run past the end,
// so the marked spans and the gaps between them tile the scene exactly once.
// Nested or broken spans are a defect, not a degraded state
// (prd.md > Script Check - The Marked Scene).
//
// Four passes:
//   1. Exact.       Every occurrence of claim.text in the raw scene.
//   2. Normalized.  Only for claims with zero exact hits: collapse whitespace
//                   runs, lowercase, search there, map the match back to raw
//                   indices through a per-character index map.
//   3. Overlap.     Longest candidate wins; a candidate intersecting an
//                   already-accepted span is dropped.
//   4. Unanchored.  Any claim left holding no accepted span is returned in
//                   `unanchored` and rendered in the rail without a mark. A
//                   verdict is never lost because it could not be placed.
//
// Why the extractor's text and not its offsets: star/agents/script_check.py's
// claim_extractor returns the exact quoted substring, and nothing else. There
// are no offsets to trust, which is also why every occurrence of a repeated
// quote is marked rather than the first: marking one would assert a position
// nobody computed (prd.md > Decisions this PRD makes #6).

const WHITESPACE = /\s/;

/** Every start index at which `needle` occurs in `haystack`, occurrences that
 *  overlap each other included.
 *
 *  The scan advances by one, not by the needle's length. The shorter version
 *  was written first and it is wrong, which is worth recording because it is
 *  the version that looks tidier: indexOf only matches at a shifted position
 *  when the needle is periodic, which is rare enough in prose to feel safe to
 *  skip and is not safe to skip. In "She says no no no and walks out.", the
 *  claim "says no" takes [4, 11) in pass 3, and the only occurrence of "no no"
 *  a length-advancing scan ever finds starts at 9, inside it. That claim then
 *  reaches the rail as unplaceable while a free occurrence of its own text sits
 *  at [12, 17), which fails "every occurrence of a repeated quote is marked"
 *  (prd.md > Script Check - The Marked Scene) in the direction that loses a
 *  mark rather than the direction that adds one.
 *
 *  The extra candidates cost nothing in correctness. Pass 3 resolves a claim's
 *  self-overlapping candidates by exactly the rule it applies to everyone
 *  else's, leftmost of the equally long, so a claim can never be marked twice
 *  over the same characters. They can only add placements. */
function occurrences(haystack, needle) {
  const found = [];
  if (!needle) return found;
  let from = 0;
  for (;;) {
    const at = haystack.indexOf(needle, from);
    if (at === -1) return found;
    found.push(at);
    from = at + 1;
  }
}

/** The normalized scene, plus one index-map entry per normalized code unit
 *  pointing back at the raw code unit it came from.
 *
 *  Two normalizations and no third: runs of whitespace collapse to one space,
 *  and letters lowercase. Those are the two the spec names
 *  (spec.md > The marked scene), and they are the two the extractor actually
 *  drifts on.
 *
 *  REJECTED: trimming the needle. A claim that arrives with a stray trailing
 *  newline would anchor either way, because a collapsed space matches a run of
 *  any length. Trimming would additionally change which characters the mark
 *  covers, and that is a change to this function's contract dressed up as a
 *  recovery.
 *
 *  WHY THE MAP IS BUILT PER CODE POINT, NOT BY CALLING toLowerCase ON THE
 *  WHOLE STRING. String.prototype.toLowerCase is not length-preserving:
 *  "İ" (capital I with dot above) lowercases to two code units, "i" plus a
 *  combining dot. Calling it on the whole scene at once would put the map out
 *  of step with the string it indexes from that character onward, and every
 *  mark after it would land on the wrong characters. Per code point, the loop
 *  below emits exactly as many normalized code units as the source occupies, so
 *  the two cannot drift apart no matter what a lowercase form does.
 *
 *  The length guard on top of that is narrower than it looks, and it is worth
 *  being precise about what it buys, because a reader who thinks it is holding
 *  the map together will be reluctant to touch it. It is not: the loop bound is
 *  what holds the map together. The guard decides what happens to a character
 *  whose lowercase form is LONGER, and the answer is that the character is
 *  carried through unchanged rather than truncated to the first code unit of
 *  its own lowercase. Truncation would silently invent a fold nobody chose. The
 *  cost is that "İ" does not case-match "i", which is the correct trade for a
 *  matcher whose failure mode is a mark on the wrong line.
 *
 *  WHERE A COLLAPSED RUN POINTS, and it matters at exactly two places. A run of
 *  whitespace emits one space whose map entry is the run's FIRST raw index, the
 *  character that produced the space. Raw characters strictly inside a matched
 *  range are covered no matter what the map says, because a raw span is a
 *  contiguous range; the choice is only visible when a match BEGINS or ENDS on
 *  a collapsed space, which happens when the claim text carries leading or
 *  trailing whitespace. The consequences, both tested:
 *
 *    - A span that begins on a collapsed space starts at [map[i]], the head of
 *      the run, so the mark opens where the gap opens and takes the whole run.
 *    - A span that ends on a collapsed space ends at [map[j-1] + 1], one raw
 *      character into the run, so the mark takes a single whitespace character
 *      and leaves the rest outside.
 *
 *  Pointing at the run's LAST raw index instead inverts that asymmetry: the
 *  start would take one character and the end would swallow the run. The end is
 *  the side worth protecting, because a <mark> that swallows a paragraph break
 *  draws a highlight across the blank line between two lines of a script. */
function normalize(raw) {
  let text = "";
  const map = [];
  let i = 0;

  while (i < raw.length) {
    if (WHITESPACE.test(raw[i])) {
      const runStart = i;
      while (i < raw.length && WHITESPACE.test(raw[i])) i += 1;
      text += " ";
      map.push(runStart);
      continue;
    }

    // Slice the whole code point so a surrogate pair is lowercased as a letter
    // rather than as two halves of one.
    const width = raw.codePointAt(i) > 0xffff ? 2 : 1;
    const source = raw.slice(i, i + width);
    const lowered = source.toLowerCase();
    const emitted = lowered.length === width ? lowered : source;
    for (let k = 0; k < width; k += 1) {
      text += emitted[k];
      map.push(i + k);
    }
    i += width;
  }

  return { text, map };
}

/** Does a claim carry text worth anchoring at all?
 *
 *  A claim whose text is empty or all whitespace normalizes to a single space,
 *  and searching for a space marks most of the scene. That is not a degraded
 *  anchor, it is a wrong one, so such a claim never becomes a candidate and
 *  lands in `unanchored` with everything else that could not be placed. */
function isAnchorable(claim) {
  return Boolean(claim) && typeof claim.text === "string" && claim.text.trim() !== "";
}

/** Segment a scene against a claim set.
 *
 *  `scene` is the raw pasted text. `claims` are whole ClaimResult objects
 *  (star/models.py), and the whole object is what gets attached to a marked
 *  segment and returned in `unanchored`, so the renderer reads the verdict,
 *  the note, and the citations off the same reference this function was given.
 *  Only `.text` is read here. */
export function anchor(scene, claims) {
  const raw = typeof scene === "string" ? scene : "";
  const list = Array.isArray(claims) ? claims : [];

  const candidates = [];
  const missedExact = [];

  // -- Pass 1: exact. -------------------------------------------------------
  for (let index = 0; index < list.length; index += 1) {
    const claim = list[index];
    if (!isAnchorable(claim)) continue;

    const hits = occurrences(raw, claim.text);
    if (hits.length === 0) {
      missedExact.push(index);
      continue;
    }
    for (const start of hits) {
      candidates.push({ start, end: start + claim.text.length, claim, index });
    }
  }

  // -- Pass 2: normalized, and only for the claims pass 1 missed. -----------
  // Gated on zero EXACT hits, not on zero accepted spans: a claim that matched
  // verbatim and then lost pass 3 to a longer claim has been placed and beaten,
  // which is a different answer from never having been found, and re-searching
  // it loosely would let a fuzzy second-choice span outrank a verbatim one.
  if (missedExact.length > 0) {
    const normalized = normalize(raw);
    for (const index of missedExact) {
      const claim = list[index];
      const needle = normalize(claim.text).text;
      if (needle.trim() === "") continue;

      for (const at of occurrences(normalized.text, needle)) {
        candidates.push({
          start: normalized.map[at],
          // map[at + length - 1] + 1, not map[at + length]. The second reads one
          // entry past the match, which is undefined for a match ending at the
          // end of the scene: the span's end becomes undefined, every overlap
          // comparison against it is false, and two nested marks get accepted.
          // It also swallows a whole trailing whitespace run when one follows.
          end: normalized.map[at + needle.length - 1] + 1,
          claim,
          index,
        });
      }
    }
  }

  // -- Pass 3: overlap resolution. -----------------------------------------
  // Longest first, then leftmost, then by the claim's position in the input.
  //
  // The leftmost key is load-bearing. Drop it and two equally long overlapping
  // candidates are ordered by whichever claim the extractor happened to list
  // first, so which one owns the line depends on the order they arrived in
  // rather than on where they sit in the scene.
  //
  // The third key is redundant today and is kept as a statement rather than a
  // guard: Array.prototype.sort has been required to be stable since ES2019,
  // and candidates are pushed claim by claim, so a tie on both length and start
  // already resolves in input order. It is written out because the behaviour it
  // pins is a real contract (two claims carrying identical text cannot both own
  // it, and the first one listed takes every occurrence) and reading that off a
  // language guarantee is worse than reading it off this line.
  candidates.sort(
    (a, b) => b.end - b.start - (a.end - a.start) || a.start - b.start || a.index - b.index
  );

  const accepted = [];
  for (const span of candidates) {
    // A linear scan against what has been accepted so far, kept instead of an
    // interval tree because the input is bounded and was measured rather than
    // reasoned about. config.max_scene_chars() caps a scene at 8000 characters.
    // A realistic shape, 8000 characters against 30 phrase-length claims, runs
    // in 4.2ms. The worst input the endpoint can receive at all, a full scene
    // against three one-and-two-character claims that match on nearly every
    // offset, runs in 73ms. Node 22, this machine, 2026-08-10. An interval tree
    // would buy back milliseconds on an input the extractor cannot produce.
    const clashes = accepted.some((taken) => span.start < taken.end && taken.start < span.end);
    if (!clashes) accepted.push(span);
  }

  // -- Pass 4: what is left, and the segmentation. --------------------------
  // A claim is unanchored when it holds NO accepted span, not when one of its
  // occurrences lost. A quote appearing three times whose second occurrence
  // sits under a longer claim is still marked twice and is not in the rail.
  const anchoredIndices = new Set(accepted.map((span) => span.index));
  const unanchored = list.filter((_, index) => !anchoredIndices.has(index));

  accepted.sort((a, b) => a.start - b.start);

  const segments = [];
  let cursor = 0;
  for (const span of accepted) {
    if (span.start > cursor) segments.push({ text: raw.slice(cursor, span.start) });
    segments.push({ text: raw.slice(span.start, span.end), claim: span.claim });
    cursor = span.end;
  }
  if (cursor < raw.length) segments.push({ text: raw.slice(cursor) });

  return { segments, unanchored };
}
