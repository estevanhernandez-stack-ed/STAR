// Guards the ledger excerpt against reaching a reader as the scraper left it.
//
// THE GAP. The app's primary evidence surface rendered raw markdown as literal
// characters, on both surfaces that show a source, and no lens filed it — a
// grep of the findings register for "excerpt" returned nothing across all 67.
// Measured on the two stored rooms before the fix: 104 excerpts, median 1462
// characters, no length cap anywhere in web/, and on the Sony Walkman card the
// citation block was 1421px of a 1730px card while the answer it supported was
// 21px.
//
// THE NUMBER THAT DECIDED THE DESIGN: only 4 of 50 excerpts in one room BEGIN
// with prose. 34 begin with a markdown heading. So the work is not truncation,
// it is finding where the prose starts — and a character cap or a
// first-sentence cap applied to the raw string caps a table cell most of the
// time. Every fixture below is a real shape taken from the stored rooms, not an
// invented one, because the invented ones are exactly what the naive
// implementation passes.
//
// ONE CONTIGUOUS PASSAGE. A structural line ENDS a run rather than being
// deleted from the middle of one. `.cite-excerpt` is a <blockquote>, and a
// quotation assembled from two paragraphs that were never adjacent is a
// quotation of something the page does not say.
//
// Run directly: `node tests/js/test_excerpt_prose.mjs` (exit 0 = pass).

import { strict as assert } from "node:assert";

const { excerptProse } = await import(new URL("../../web/excerpt.js", import.meta.url).href);

const has = (t, re) => re.test(t);
const MARKUP = /\|[^|]*\||\]\(|\*\*|(^|\s)#{1,6}\s|\[\[|`{3,}/;

/* 1 — a heading before the prose. 34 of 50 excerpts open this way. ------- */

const heading = excerptProse(
  "# History of the cassette Walkman\n" +
    "In March 1979, at the request of Masaru Ibuka , the audio department " +
    "modified the small recorder used by journalists, \"Pressman\", into a " +
    "smaller recorder. It went on sale in Japan on 1 July 1979."
);
assert.doesNotMatch(heading, MARKUP, "the heading marker must not survive");
assert.ok(
  heading.startsWith("In March 1979"),
  `the quote should start where the prose starts, got: ${heading.slice(0, 40)}`
);

/* 2 — a table row that does not start with a pipe. ----------------------- */

// The infobox shape that defeated the first implementation: a bullet, not a
// pipe, so anchoring the table rule to ^\| left the cells glued to the prose.
const infobox = excerptProse(
  "* Ministry of Internal Affairs | |Child agency |* ZOMO , ORMO |\n" +
    "The Milicja Obywatelska ( MO ), known as the Citizens' Militia in " +
    "English, was the national police organization of the Polish People's " +
    "Republic . It was formed in 1944 and dissolved in 1990."
);
assert.doesNotMatch(infobox, MARKUP, "table cells must not reach the reader");
assert.ok(infobox.startsWith("The Milicja"), `got: ${infobox.slice(0, 40)}`);

/* 3 — nested brackets in a link. ---------------------------------------- */

const nested = excerptProse(
  "The Milicja Obywatelska ( Polish pronunciation: " +
    '[[miˈlit͡sja ɔbɨvaˈtɛlska]](/wiki/Help:IPA/Polish "Help:IPA/Polish") ; MO ) ' +
    "was the national police organization of the Polish People's Republic, and " +
    "it answered to the ministry rather than to any local authority."
);
assert.doesNotMatch(nested, MARKUP, "a doubled-bracket link must unwrap cleanly");
assert.match(nested, /miˈlit͡sja ɔbɨvaˈtɛlska/, "and keep the words it wrapped");

/* 4 — an empty image link opening the excerpt. --------------------------- */

const image = excerptProse(
  "[](https://en.wikipedia.org/wiki/File:GDANSK,_Falowiec.JPG) " +
    '[Gdańsk](https://en.wikipedia.org/wiki/Gda%C5%84sk "Gdańsk") \'s longest ' +
    "falowiec at Obrońców Wybrzeża street\n" +
    "Falowiec is a block of flats characterised by its length and wavy shape. " +
    "This type of building was built in Poland in the late 1960s and 1970s."
);
assert.doesNotMatch(image, MARKUP, "an image link must not print as brackets and a URL");
assert.doesNotMatch(image, /https?:\/\//, "and must not leave a bare URL behind");

/* 5 — a heading in the MIDDLE ends the run; it is not deleted from it. --- */

// This is the contiguity property. Joining across the heading would quote a
// passage the page does not contain.
const twoSections = excerptProse(
  "# Section one\n" +
    "The first paragraph runs on for long enough to read as real prose, and it " +
    "ends here with a full stop.\n" +
    "## Section two\n" +
    "The second paragraph is also prose and also long enough to qualify on its " +
    "own terms."
);
assert.match(twoSections, /first paragraph/, "the first prose run is chosen");
assert.doesNotMatch(
  twoSections,
  /second paragraph/,
  "and the run STOPS at the next heading — text either side of a section " +
    "break was never one passage, so quoting both as one is a fabrication"
);

/* 6 — the HTML flavour passes through with its highlight. ---------------- */

// 5 of 104 excerpts carry <strong>. clip.js hands this to DOMPurify, so the
// tags have to survive this module intact.
const html = excerptProse(
  "<strong>Komitet</strong> <strong>kolejkowy</strong> – grupa osób " +
    "pilnujących porządku i kolejności kolejki, nieodzowna w przypadku " +
    "powstania listy kolejkowej, na której zapisywano chętnych."
);
assert.match(html, /<strong>Komitet<\/strong>/, "the match highlighting is real evidence");

/* 7 — capping: at a sentence, never mid-word, and marked. ---------------- */

const SOURCE =
  "Supercalifragilistic introductory clause without any terminator at all so " +
  "the sentence branch cannot fire and the word-boundary branch has to carry " +
  "this on its own merits right here";
const long = excerptProse(SOURCE, { limit: 60 });
assert.ok(long.length <= 70, `capped, got ${long.length}`);
assert.match(long, /…$/, "a truncated passage says so, with the mark star/auth.py uses");

// The real property: the kept text must END WHERE A WORD ENDS in the source.
// Asserting the absence of `\w…` proves nothing, because the code always puts
// a space before the mark — that assertion passed on a build that cut
// mid-word, which is how this test was wrong the first time.
const kept = long.replace(/\s*…$/, "");
assert.ok(SOURCE.startsWith(kept), "the quote is a real prefix of the source");
assert.match(
  SOURCE.slice(kept.length),
  /^(\s|$)/,
  `cut mid-word: source continues with ${JSON.stringify(SOURCE.slice(kept.length, kept.length + 8))}`
);

/* 8 — a tag is never cut in half. ---------------------------------------- */

// limit 58 puts the window's end INSIDE `<strong>` rather than after it. The
// first version of this used 64, which lands past the closing bracket and
// exercises nothing.
const midTag = excerptProse(
  "aaaaaaaaaa bbbbbbbbbb cccccccccc dddddddddd eeeeeeeeee <strong>ffff</strong> " +
    "gggggggggg hhhhhhhhhh and then a good deal more text after it as well.",
  { limit: 58 }
);
// Balance, not a trailing-anchor match: the ellipsis is appended AFTER the
// cut, so `/<[a-z]*$/` can never fire even on a result carrying `<str`. That
// is how this assertion passed on a build with the guard removed.
const balanced = (t) => (t.match(/</g) || []).length === (t.match(/>/g) || []).length;
assert.ok(balanced(midTag), `half-written tag: ${JSON.stringify(midTag.slice(-24))}`);

// The case where the guard is the ONLY thing standing between a reader and a
// half-written tag. With a space before the tag the word-boundary cut already
// removes it — tag names contain no spaces, so the last space is always in
// front of the `<`. Take the spaces away and that branch has nothing to fall
// back to, and the raw limit lands inside `<stro`.
const unspaced = excerptProse("a".repeat(40) + "<strong>bbbb</strong>" + "c".repeat(20), {
  limit: 44,
});
assert.ok(
  balanced(unspaced),
  `no space to retreat to, so the tag-aware trim is what has to catch this: ` +
    JSON.stringify(unspaced.slice(-24))
);

/* 8b — a run carrying residue loses to a clean one further down. --------- */

// Both runs read as sentences on length and punctuation alone. Only the
// residue check separates them, and without it the reader gets the markers.
const dirtyThenClean = excerptProse(
  "An opening paragraph **with an unbalanced emphasis marker that still runs " +
    "long enough to look like a sentence on its own.\n" +
    "## A heading, which ends that run\n" +
    "A second paragraph that is entirely clean and also long enough to read as " +
    "real prose in its own right."
);
assert.doesNotMatch(dirtyThenClean, MARKUP, "the residue disqualifies the first run");
assert.match(dirtyThenClean, /second paragraph/, "so the clean run is quoted instead");

/* 8c — a surviving run beats flattening the whole source. ---------------- */

// No run here is prose (too short, no terminator), so the choice is between
// the trimmed run and the last-resort flatten. The flatten would drag the
// heading's words in beside it.
const shortRun = excerptProse("# Portugal Banknote Gallery\nItem Code: PT-173");
assert.match(shortRun, /Item Code/, "the surviving run is the quote");
assert.doesNotMatch(
  shortRun,
  /Banknote Gallery/,
  "the heading is not folded in beside it — the last-resort flatten is for " +
    "sources where every single line is structural, not for this one"
);

/* 9 — never empty, whatever arrives. ------------------------------------- */

// A source that is nothing but a table has no sentence to quote. Showing the
// page's words in the page's order beats showing the reader the scraper.
const allTable = excerptProse(
  "# Portugal Banknote Gallery\n" +
    "|Home Page | | Portugal Banknote Gallery |\n" +
    "| Portugal 20 Escudos 1971 | | Item Code: PT-173 |\n" +
    "| Watermark: Statue |"
);
assert.ok(allTable.trim(), "a reader must never meet an empty quotation");
assert.doesNotMatch(allTable, MARKUP, "and never meet the table markers either");
assert.match(allTable, /Portugal/, "the page's own words survive");

for (const input of ["", null, undefined]) {
  assert.equal(excerptProse(input), "", `${String(input)} yields an empty string, not a crash`);
}

/* 10 — plain prose is left alone. ---------------------------------------- */

const plain =
  "Powyższa decyzja była po części wypadkową wydarzeń czerwca 1976 roku, " +
  "kiedy ludzie przypuścili szturm na sklepy.";
assert.equal(excerptProse(plain), plain, "7 of 50 arrive clean and must pass through untouched");

console.log("test_excerpt_prose.mjs: 29 assertions passed");
