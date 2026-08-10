// Proves web/scriptcheck.js turns a filed check into a DOM without ever
// turning a string into markup, and that the surface's load-bearing copy and
// colour rules say what checklist item 9 requires them to say.
//
// The XSS case is a TEST here, not a manual step. web/anchor.js already proves
// its half — a pasted `<img src=x onerror=alert(1)>` comes back out of the
// matcher as the characters that went in (tests/js/test_anchor.mjs, case 9).
// This file proves the other half: those characters reach the DOM as a text
// node inside a real <mark>, and no element named IMG exists anywhere in the
// rendered tree. Two assertions back it up rather than one, because a DOM stub
// with no HTML parser cannot produce an <img> on its own and a shape assertion
// alone would therefore be circular:
//
//   1. the tree's shape, against the stub (below), and
//   2. a source assertion that web/scriptcheck.js contains no innerHTML,
//      outerHTML, insertAdjacentHTML or document.write at all — so the tree is
//      the only way anything gets in.
//
// What this file cannot prove, and what the live browser checkpoint still has
// to: that the marks are actually visible, that the focus ring is actually
// drawn, that the columns actually collapse at 900px, and what share of the
// filed room's pixels are actually manila. Those are measurements against a
// layout engine; everything below is a statement about a tree and a string.
//
// Run directly: `node tests/js/test_scriptcheck.mjs` (exit 0 = pass).
// Wired into pytest via tests/test_js_auth.py so pytest stays the single entry
// point.

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

import {
  elements,
  loadPatchedModule,
  readSource,
  stubDocument,
  textNodes,
  walk,
  withClass,
} from "./_scriptcheck_module.mjs";

const REPO_ROOT = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, REPO_ROOT), "utf8");

/** Source with its comments removed.
 *
 *  Both assertions below are about what SHIPS, not about what is explained.
 *  web/clip.js's own header says the word "verified" never appears in anything
 *  a user reads — a sentence that could not survive a grep over comments, and
 *  the file is right to carry it. Same for the innerHTML check: the module's
 *  header exists to say it has none, and a check that punished it for saying so
 *  would push the explanation out of the file to satisfy the test.
 *
 *  Block comments first, then whole-line `//` comments — anchored at the start
 *  of a line so a `//` inside a regex literal or a string is left alone. */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

globalThis.document = stubDocument();
globalThis.__starAuthedFetch = async () => {
  throw new Error("no test below should reach the network");
};

const { renderCheckResult } = await import(loadPatchedModule());

const XSS = "<img src=x onerror=alert(1)>";

/** A payload in the shape star/models.py's ScriptCheckResult produces, plus
 *  the `scene` field web/scriptcheck.js hands back in (the POST response
 *  carries the claims; the scene is the text this page just sent). */
function payload(overrides = {}) {
  return {
    scene_id: "abc123def456",
    created_at: "2026-08-10T15:04:05+00:00",
    scene:
      "INT. STUDIO B - NIGHT\n\nShe threads tape onto the Ampex 350.\n" +
      "A Bakelite radio hums on the bench.\nOutside, the '61 Impala idles.",
    claims: [],
    parse_rate: 1.0,
    unsourced_count: 0,
    field_notes: "",
    search_count: 0,
    budget_exhausted: false,
    cover_note: "",
    ...overrides,
  };
}

function claim(overrides = {}) {
  return {
    text: "the Ampex 350",
    claim_type: "object",
    verdict: "confirmed",
    note: "",
    citations: [],
    citation_sources: [],
    unsourced_urls: [],
    reason: "",
    ...overrides,
  };
}

function citation(overrides = {}) {
  return {
    url: "https://museumofmagneticsoundrecording.org/ampex-350",
    title: "Ampex 350 — Museum of Magnetic Sound Recording",
    excerpt: "The <strong>Ampex 350</strong> shipped in 1953 and &quot;stayed in studios for a decade&quot;.",
    ...overrides,
  };
}

const railText = (root) => withClass(root, "check-rail-body")[0].textContent;
const marks = (root) => elements(root, "MARK");

// -- 1: the H1 XSS's other door, closed. -----------------------------------
// The payload sits inside a claim, so it is marked — the worst case, because a
// marked segment is the one place the renderer creates an element around
// reader-pasted characters. It also sits in the note, the cover note, the field
// notes, a citation's title and excerpt, and an unsourced URL, which is every
// other string on this surface that a model or a web page authored.
function testAPastedTagRendersAsTextAndNothingExecutes() {
  const scene = `She holds a sign reading ${XSS} and laughs.`;
  const root = renderCheckResult(
    payload({
      scene,
      cover_note: `cover ${XSS}`,
      field_notes: `note line ${XSS}`,
      claims: [
        claim({
          text: XSS,
          verdict: "anachronism",
          note: `The prop is wrong for the period ${XSS}`,
          citations: [citation({ title: `title ${XSS}`, excerpt: `excerpt ${XSS}` })],
          citation_sources: ["room"],
          unsourced_urls: [`https://example.invalid/${XSS}`],
        }),
      ],
    })
  );

  // The shape: a real <mark> holding one text node that is the payload exactly.
  const hits = marks(root);
  assert.equal(hits.length, 1, "the pasted payload is marked, once");
  assert.equal(hits[0].nodeName, "MARK", "a real <mark> element, not a span dressed as one");
  assert.equal(hits[0].childNodes.length, 1);
  assert.equal(hits[0].childNodes[0].nodeType, 3, "the mark's only child is a text node");
  assert.equal(hits[0].childNodes[0].data, XSS, "the payload's exact characters");

  // And it is a text node everywhere else it appears, too.
  const payloadTextNodes = textNodes(root).filter((n) => n.data.includes(XSS));
  assert.ok(
    payloadTextNodes.length >= 5,
    `expected the payload as text in the mark, the note, the cover note, the ` +
      `field notes and the citation title/excerpt; found ${payloadTextNodes.length}`
  );

  // Nothing executed, because nothing was ever parsed.
  assert.equal(elements(root, "IMG").length, 0, "no <img> element exists in the tree");
  assert.equal(elements(root, "SCRIPT").length, 0);
  for (const node of walk(root)) {
    if (node.nodeType !== 1) continue;
    for (const name of node.attributes.keys()) {
      assert.ok(
        !/^on/i.test(name),
        `no element carries an event-handler attribute; found ${name} on ${node.nodeName}`
      );
    }
  }

  // The unsourced URL keeps its payload as text and is deliberately NOT a link
  // — star/models.py's own posture on the same field in Pipeline A: "Rendered
  // as a warning, never as a source."
  const unsourced = withClass(root, "rail-unsourced-url");
  assert.equal(unsourced.length, 1);
  assert.ok(unsourced[0].textContent.includes(XSS));
  assert.equal(elements(unsourced[0], "A").length, 0, "an unsourced URL is never an anchor");
}

// -- 1b: the source assertion the shape test needs beside it. --------------
// The stub has no HTML parser, so "no <img> in the tree" is only meaningful if
// the tree is the only way anything reaches the page. This is that.
function testTheModuleNeverTurnsAStringIntoMarkup() {
  const code = stripComments(readSource());
  for (const sink of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"]) {
    assert.equal(
      code.includes(sink),
      false,
      `web/scriptcheck.js must contain no ${sink}: it is the one surface where ` +
        "the reader pastes untrusted text on purpose"
    );
  }
  // createTextNode is how every string gets in, so it had better be there.
  assert.ok(code.includes("document.createTextNode"), "text nodes are the only door");
}

// -- 2: the scene comes back whole. ----------------------------------------
// Every character the writer pasted, in order, once. The matcher's own tests
// assert this about segments; this asserts it survived the renderer.
function testTheRenderedSceneReproducesThePasteExactly() {
  const data = payload({
    claims: [
      claim({ text: "the Ampex 350" }),
      claim({ text: "A Bakelite radio", verdict: "unverifiable", note: "Nothing dated it." }),
      claim({ text: "the '61 Impala", verdict: "anachronism", note: "Out by a year." }),
    ],
  });
  const root = renderCheckResult(data);
  const page = withClass(root, "scene-page")[0];

  assert.equal(page.textContent, data.scene, "the page reproduces the scene byte for byte");
  assert.equal(marks(root).length, 3, "three claims, three marks");
}

// -- 3: verdict colours are carried as data, and confirmed is aniline. -----
// The renderer's job is to put the verdict on the element; scene.css's job is
// to map it to a token. Both are asserted, because either one alone would let
// "confirmed renders green" ship.
function testEachVerdictIsCarriedOntoTheMarkAndTheStamp() {
  const root = renderCheckResult(
    payload({
      claims: [
        claim({ text: "the Ampex 350", verdict: "confirmed" }),
        claim({ text: "A Bakelite radio", verdict: "unverifiable", note: "Nothing dated it." }),
        claim({ text: "the '61 Impala", verdict: "anachronism", note: "Out by a year." }),
      ],
    })
  );

  assert.deepEqual(
    marks(root).map((m) => m.getAttribute("data-verdict")),
    ["confirmed", "unverifiable", "anachronism"],
    "each mark carries its own claim's verdict, in scene order"
  );

  const stamp = withClass(root, "verdict-stamp")[0];
  assert.equal(stamp.getAttribute("data-verdict"), "confirmed");
  assert.equal(stamp.textContent, "confirmed", "the stamp reads the payload's own word");

  // An unrecognised verdict lands on the state that claims least. Coercing it
  // to `confirmed` would stamp a line nobody judged.
  const odd = renderCheckResult(
    payload({ claims: [claim({ text: "the Ampex 350", verdict: "excellent" })] })
  );
  assert.equal(marks(odd)[0].getAttribute("data-verdict"), "unverifiable");
}

function testTheStylesheetMapsVerdictsToTheDirectionPalette() {
  // Comments stripped, for the reason stripComments records: this file's own
  // header quotes DIRECTION.md's "filed and verified" and its rule against
  // gradients, and a grep that punished it for explaining itself would push the
  // explanation out of the stylesheet.
  const css = stripComments(read("web/scene.css"));

  const confirmed = css.match(/\.mark\[data-verdict="confirmed"\]\s*\{[^}]*\}/)[0];
  assert.ok(confirmed.includes("--aniline"), "confirmed is aniline");
  const anachronism = css.match(/\.mark\[data-verdict="anachronism"\]\s*\{[^}]*\}/)[0];
  assert.ok(anachronism.includes("--oxide"), "anachronism is oxide");
  const base = css.match(/\n\.mark\s*\{[^}]*\}/)[0];
  assert.ok(base.includes("--pencil"), "the default mark, unverifiable, is pencil");

  const stamp = css.match(/\.rail-unsourced-stamp\s*\{[^}]*\}/)[0];
  assert.ok(stamp.includes("--oxide"), "the UNSOURCED stamp is oxide");

  // Nothing is added to the palette, and the two make-or-break rules hold.
  assert.equal(/green|#[0-9a-f]{3,8}\b/i.test(css), false,
    "no raw hex and no green — every colour is a token from web/tokens.css");
  assert.equal(/gradient/i.test(css), false, "no gradient anywhere: aniline is flat stamp ink");
  for (const [, degrees] of css.matchAll(/rotate\((-?[\d.]+)deg\)/g)) {
    assert.ok(Math.abs(Number(degrees)) <= 2.5, `rotation ${degrees}deg exceeds the 2.5deg ceiling`);
  }
}

// -- 4: the rail follows the selected mark. --------------------------------
function testTheRailFollowsTheSelectedMark() {
  const root = renderCheckResult(
    payload({
      claims: [
        claim({ text: "the Ampex 350", verdict: "confirmed" }),
        claim({
          text: "the '61 Impala",
          verdict: "anachronism",
          note: "The 1961 Impala had not shipped when this scene is set.",
        }),
      ],
    })
  );
  const hits = marks(root);

  // Opens on the first mark rather than on an instruction.
  assert.equal(hits[0].getAttribute("aria-pressed"), "true");
  assert.equal(hits[1].getAttribute("aria-pressed"), "false");
  assert.ok(railText(root).includes("the Ampex 350"));

  hits[1].dispatch("click");
  assert.equal(hits[0].getAttribute("aria-pressed"), "false");
  assert.equal(hits[1].getAttribute("aria-pressed"), "true", "selection is a state, not a colour");
  assert.ok(railText(root).includes("the '61 Impala"));
  assert.ok(railText(root).includes("had not shipped"), "the note travels with the verdict");
  assert.equal(
    withClass(root, "rail-card")[0].getAttribute("data-verdict"),
    "anachronism"
  );
}

// -- 4b: keyboard. A <mark> with role="button" gets nothing natively. -------
function testEnterAndSpaceSelectAMark() {
  const root = renderCheckResult(
    payload({
      claims: [claim({ text: "the Ampex 350" }), claim({ text: "the '61 Impala", note: "x" })],
    })
  );
  const hits = marks(root);

  for (const mark of hits) {
    assert.equal(mark.getAttribute("tabindex"), "0", "every mark is reachable by keyboard");
    assert.equal(mark.getAttribute("role"), "button");
    assert.equal(mark.getAttribute("aria-controls"), "check-rail-body");
  }

  let prevented = 0;
  hits[1].dispatch("keydown", { key: "Enter", preventDefault: () => (prevented += 1) });
  assert.equal(hits[1].getAttribute("aria-pressed"), "true", "Enter selects");

  hits[0].dispatch("keydown", { key: " ", preventDefault: () => (prevented += 1) });
  assert.equal(hits[0].getAttribute("aria-pressed"), "true", "Space selects");
  assert.equal(prevented, 2, "both keys are consumed, so Space does not scroll the page away");

  hits[1].dispatch("keydown", { key: "a", preventDefault: () => (prevented += 1) });
  assert.equal(prevented, 2, "an ordinary key is left alone");
  assert.equal(hits[0].getAttribute("aria-pressed"), "true", "and changes nothing");
}

// -- 5: every citation clicks through, safely. -----------------------------
function testEveryCitationOpensInANewTabWithNoopenerNoreferrer() {
  const root = renderCheckResult(
    payload({
      claims: [
        claim({
          citations: [
            citation(),
            citation({ url: "https://nmgl.org/rumrunning", title: "https://nmgl.org/rumrunning" }),
          ],
          citation_sources: ["room", "search"],
        }),
      ],
    })
  );

  const links = elements(root, "A");
  assert.equal(links.length, 2, "one link per hydrated citation");
  for (const link of links) {
    assert.equal(link.getAttribute("rel"), "noopener noreferrer");
    assert.equal(link.getAttribute("target"), "_blank");
    assert.ok(/^https?:\/\//.test(link.getAttribute("href")), "http(s) only");
  }

  // Obligation 7 — WHICH of the two answered, per citation, computed by
  // star/verdicts.py from two ledgers rather than asserted by a model.
  assert.deepEqual(
    withClass(root, "cite-origin").map((n) => n.textContent),
    ["From this room's files", "From a fresh search for this check"]
  );

  // A "title" that is only the URL is not a title, so the domain stands in
  // rather than the address being printed twice.
  assert.deepEqual(
    withClass(root, "cite-title").map((n) => n.textContent),
    ["Ampex 350 — Museum of Magnetic Sound Recording", "nmgl.org"]
  );

  // The search API's own <strong> highlighting and entities become characters.
  const excerpt = withClass(root, "cite-excerpt")[0].textContent;
  assert.ok(excerpt.includes("Ampex 350 shipped in 1953"), "the emphasis tags are gone");
  assert.ok(excerpt.includes('"stayed in studios for a decade"'), "entities are decoded");
  assert.equal(/[<>]/.test(excerpt), false, "and nothing angle-bracketed survives");
}

function testANonHttpCitationProducesNoLinkAtAll() {
  const root = renderCheckResult(
    payload({
      claims: [
        claim({
          // eslint-disable-next-line no-script-url
          citations: [{ url: "javascript:alert(1)", title: "not a source", excerpt: "" }],
          citation_sources: ["room"],
        }),
      ],
    })
  );
  assert.equal(elements(root, "A").length, 0, "a javascript: URL never becomes an href");
  assert.equal(withClass(root, "rail-citation").length, 0, "and never becomes a citation");
}

// -- 6: a verdict is never lost because it could not be placed. ------------
function testAnUnplacedClaimIsReachableInTheRail() {
  const root = renderCheckResult(
    payload({
      claims: [
        claim({ text: "the Ampex 350" }),
        claim({
          text: "She drives a Chevrolet",
          verdict: "unverifiable",
          note: "Nothing in the room names the car.",
        }),
      ],
    })
  );

  assert.equal(marks(root).length, 1, "only the claim that appears in the scene is marked");
  const unplaced = withClass(root, "rail-unplaced-btn");
  assert.equal(unplaced.length, 1);
  assert.ok(unplaced[0].textContent.includes("She drives a Chevrolet"));
  assert.equal(unplaced[0].getAttribute("data-verdict"), "unverifiable");

  unplaced[0].dispatch("click");
  assert.equal(unplaced[0].getAttribute("aria-pressed"), "true");
  assert.equal(marks(root)[0].getAttribute("aria-pressed"), "false", "the mark lets go");
  assert.ok(railText(root).includes("Nothing in the room names the car."));
}

// -- 7: budget reads as budget, never as not-found. ------------------------
// star/verdicts.py already writes "The check ran out of searches before
// reaching this claim." into the note. What the note does NOT say is that this
// is a limit on the department rather than a finding about the line, and that
// distinction is the whole reason the budget-honesty path exists.
function testABudgetReasonReadsAsBudgetAndNotAsAbsence() {
  const root = renderCheckResult(
    payload({
      budget_exhausted: true,
      claims: [
        claim({
          text: "the Ampex 350",
          verdict: "unverifiable",
          note: "The check ran out of searches before reaching this claim.",
          reason: "budget",
        }),
      ],
    })
  );

  const rail = railText(root);
  assert.ok(rail.includes("The check ran out of searches"), "the annotator's note is kept verbatim");
  assert.ok(
    rail.includes("limit on what the department did, not a finding about the line"),
    "and the UI adds the distinction the note does not state"
  );
  assert.equal(
    /not found|nothing was found|no such|does not exist/i.test(rail),
    false,
    "a budget answer must never be dressed as an absence"
  );

  // The whole-check counter says the same thing at the top of the surface.
  assert.ok(
    root.textContent.includes("spent its whole search budget"),
    "budget_exhausted is stated once for the check as well as per claim"
  );

  const unreached = renderCheckResult(
    payload({
      claims: [
        claim({
          verdict: "unverifiable",
          note: "The check did not come back with a verdict for this claim.",
          reason: "unreached",
        }),
      ],
    })
  );
  assert.ok(railText(unreached).includes("filed unsettled rather than dropped"));
}

// -- 8: the thin results, and the line that keeps them from reading as
//       failures. star/models.py's cover_note exists for exactly two cases.
function testTheCoverNoteIsShownAndIsNotDressedAsAnError() {
  const line =
    "Nothing in this scene made a claim about the world, so there was nothing " +
    "for the department to check.";
  const root = renderCheckResult(payload({ claims: [], cover_note: line }));

  const cover = withClass(root, "check-cover");
  assert.equal(cover.length, 1);
  assert.equal(cover[0].textContent, line);
  // Not an alert: it carries no oxide-flagged class and the rail says what it
  // says rather than sitting blank.
  assert.ok(railText(root).includes("nothing to read here"));
  assert.equal(marks(root).length, 0);
  assert.ok(root.textContent.includes("0 claims"));
}

// -- 9: research obligation 4 — the real uncertainty numbers, and each piece
//       dropped rather than defaulted when it is absent.
function testTheCountsAreStatedAndNeverGuessed() {
  const rich = renderCheckResult(
    payload({
      search_count: 6,
      parse_rate: 0.75,
      unsourced_count: 2,
      claims: [claim(), claim({ text: "A Bakelite radio" })],
    })
  );
  const text = rich.textContent;
  assert.ok(text.includes("2 claims · 6 live searches"), "sibilant plurals included");
  assert.ok(text.includes("75% of the verifier's lines parsed"));
  assert.ok(
    text.includes("measures the format it wrote in, not whether its judgments are right"),
    "parse_rate is never allowed to read as an accuracy score"
  );
  assert.ok(text.includes("2 cited links"));

  // A payload with no counts on it prints no counts, rather than a confident
  // zero for a check that ran six searches.
  const thin = renderCheckResult({ claims: [claim()], scene: "the Ampex 350 sits there." });
  assert.equal(thin.textContent.includes("live search"), false);
  assert.equal(thin.textContent.includes("%"), false);
}

// -- 10: the delete control, and the promise it keeps. ---------------------
function testDeletingTakesTwoClicksAndSaysWhatGoes() {
  let deleted = 0;
  const root = renderCheckResult(payload({ claims: [claim()] }), {
    onDelete: () => (deleted += 1),
  });

  const button = withClass(root, "check-delete-btn")[0];
  assert.equal(button.textContent, "Delete this check");
  assert.equal(button.getAttribute("data-armed"), "false");

  button.dispatch("click");
  assert.equal(deleted, 0, "the first click arms, it does not delete");
  assert.equal(button.getAttribute("data-armed"), "true");
  assert.equal(button.textContent, "Delete it for good");
  assert.ok(
    withClass(root, "check-delete-note")[0].textContent.includes("the scene text stored with it"),
    "and it names what goes, on the page rather than in a browser dialog"
  );

  button.dispatch("click");
  assert.equal(deleted, 1);
  assert.equal(button.disabled, true, "and cannot be pressed twice");

  // A payload with no scene_id gets no control rather than a dead one.
  const noDelete = renderCheckResult(payload({ claims: [claim()] }));
  assert.equal(withClass(noDelete, "check-delete-btn").length, 0);
}

// -- 11: the copy. -------------------------------------------------------
function testNoCopyOnThisSurfaceSaysVerified() {
  const rendered = renderCheckResult(
    payload({
      cover_note: "This room filed no sources of its own.",
      field_notes: "A closing note the parser could not read.",
      search_count: 4,
      parse_rate: 0.5,
      unsourced_count: 1,
      budget_exhausted: true,
      claims: [
        claim({ citations: [citation()], citation_sources: ["room"] }),
        claim({ text: "A Bakelite radio", verdict: "anachronism", note: "Out of period." }),
        claim({
          text: "the '61 Impala",
          verdict: "unverifiable",
          note: "Nothing dated it.",
          reason: "budget",
          unsourced_urls: ["https://example.invalid/gone"],
        }),
        claim({ text: "She drives a Chevrolet", verdict: "unverifiable", note: "Unplaced." }),
      ],
    })
  ).textContent;

  const html = read("web/index.html");
  const files = {
    "the rendered surface": rendered,
    "web/scriptcheck.js": stripComments(read("web/scriptcheck.js")),
    "web/scene.css": stripComments(read("web/scene.css")),
    "the check section of web/index.html": stripComments(
      html.slice(html.indexOf("<!-- Script Check."), html.indexOf("<footer>"))
    ),
  };
  for (const [where, body] of Object.entries(files)) {
    const hits = body.match(/\bverified\b/gi) || [];
    assert.deepEqual(hits, [], `"verified" must not appear in ${where}`);
  }

  // And the scope sentence that keeps a verdict from reading as a fact about
  // the world is present, not optional.
  assert.ok(rendered.includes("not a check of the line against the world"));
}

// -- 12: the narrow viewport, and the motion path. ------------------------
// Both are CSS facts, so both are asserted against the stylesheet. The browser
// checkpoint is what proves they actually take effect.
function testTheSurfaceCollapsesAt900pxAndHonoursReducedMotion() {
  const css = stripComments(read("web/scene.css"));

  const narrow = css.match(/@media \(max-width: 900px\)\s*\{[\s\S]*?\n\}/)[0];
  assert.ok(
    /\.check-columns\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/.test(narrow),
    "the scene and the rail become one column at 900px, the room's own breakpoint"
  );

  assert.ok(
    /\.verdict-stamp\s*\{[^}]*animation:\s*verdict-press var\(--stamp-duration\)/.test(css),
    "the only motion on this surface runs on the token tokens.css zeroes"
  );
  const reduced = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/)[0];
  assert.ok(
    /\.verdict-stamp\s*\{\s*animation:\s*none/.test(reduced),
    "plus the independent second path web/drawer.css and web/clip.css both carry"
  );
}

testAPastedTagRendersAsTextAndNothingExecutes();
testTheModuleNeverTurnsAStringIntoMarkup();
testTheRenderedSceneReproducesThePasteExactly();
testEachVerdictIsCarriedOntoTheMarkAndTheStamp();
testTheStylesheetMapsVerdictsToTheDirectionPalette();
testTheRailFollowsTheSelectedMark();
testEnterAndSpaceSelectAMark();
testEveryCitationOpensInANewTabWithNoopenerNoreferrer();
testANonHttpCitationProducesNoLinkAtAll();
testAnUnplacedClaimIsReachableInTheRail();
testABudgetReasonReadsAsBudgetAndNotAsAbsence();
testTheCoverNoteIsShownAndIsNotDressedAsAnError();
testTheCountsAreStatedAndNeverGuessed();
testDeletingTakesTwoClicksAndSaysWhatGoes();
testNoCopyOnThisSurfaceSaysVerified();
testTheSurfaceCollapsesAt900pxAndHonoursReducedMotion();

console.log("tests/js/test_scriptcheck.mjs: all assertions passed");
