/* The ledger excerpt, reduced to a passage a reader can actually read.
   ---------------------------------------------------------------------

   WHAT ARRIVES. Measured against the stored Gdansk-1978 room on 2026-08-11,
   over all 50 excerpts the room holds:

     - 41 are the page's content as MARKDOWN — headings, table rows, inline
       `[label](url)` links, `[](…File:…)` image links, `[[ 12 ]]()` wiki cite
       markers.
     -  2 are a search snippet with HTML <strong> around the matched terms.
     -  7 are already plain prose.
     -  0 carry both flavours, and 0 carry HTML entities.

   THAT LAST CLAUSE IS TRUE OF THOSE FIFTY AND NOT OF EVERY ROOM. A Bonhams lot
   description in the Substitute Sync room carries `&#x27;`, which reached a
   printed defence card as "George Harrison&#x27;s signature" on a sheet meant
   to be handed to somebody. The count above stands as what was measured;
   `decodeEntities` below is what the counterexample cost. A sample of one room
   is a sample of one room.

   And the number this module exists for: only **4 of the 50 begin with prose**.
   34 begin with a heading. So the work is not truncation — it is finding where
   the prose starts. A character cap or a first-sentence cap applied to the raw
   string caps a table cell most of the time.

   THIS CORRECTS TWO COMMENTS. web/scriptcheck.js and web/clip.js both describe
   this payload as HTML carrying <strong> highlighting and entities like
   `&quot;`, "verified against the stored Detroit-1929 room". That was true of
   what they saw; it is not true of what arrives now. Either the search API
   changed its extraction or it varies by source. Both flavours are handled
   below rather than one being declared correct, because nothing here knows
   which room a reader will open.

   ONE CONTIGUOUS PASSAGE, NEVER A STITCH. Structural lines are dropped from the
   FRONT and BACK of a block, never from the middle, and blocks are never
   joined. `.cite-excerpt` is a <blockquote>, and a blockquote assembled out of
   two paragraphs that were never adjacent is a quotation of something the page
   does not say. Reducing what is shown is fair; composing a new passage is not.

   NOT A SANITIZER, AND NOT FOR FIELD NOTES. This strips the scraper's encoding
   of a third-party page — a `#` that means "heading", not a character the page
   printed. web/clip.js's renderFieldNotes deliberately does the opposite for
   researcher prose, where verbatim means verbatim, and nothing here goes near
   it. Inline HTML passes through untouched: each surface still runs its own
   escaping or DOMPurify pass afterwards, and this module must not be the thing
   standing between untrusted text and the DOM.
*/

/** A line that is the scrape's structure rather than the page's prose. */
const STRUCTURAL = [
  /^#{1,6}\s/, // markdown heading
  /\|[^|]*\|/, // a table row, ANYWHERE in the line rather than only at its
  // start: an infobox arrives as `* Ministry of Internal Affairs | |Child
  // agency |` — a bullet, so anchoring to `^\|` misses it and leaves cells
  // glued to the prose underneath.
  /^[-=*_·•]{3,}$/, // horizontal rule or a bullet run
  /^\[[^\]]*\]\([^)]*\)\s*$/, // a line that is nothing but a link
  /^!?\[\]\([^)]*\)\s*$/, // an image link with no alt text at all
  /^`{3,}/, // a code fence
  /^\.{3,}$/, // the API's own elision marker, alone on its line
  /^[\s|:.-]*$/, // blank, or a table separator row
];

/** Markup that should never survive into a quotation. Used to reject a block
 *  rather than to clean one: a block still carrying this after unwrapping is
 *  not prose that needs tidying, it is structure wearing a sentence. */
const RESIDUE = /\|[^|]*\||\]\(|\*\*|^#{1,6}\s|`{3,}/m;

const isStructural = (line) => STRUCTURAL.some((re) => re.test(line.trim()));

/** Markdown's inline marks, unwrapped to the words they wrap.
 *
 *  Order matters: links first, so a `[label](url)` cannot leave a bare URL for
 *  the emphasis rules to chew on. Underscore emphasis is deliberately the
 *  fussiest of these — an underscore is a legal character inside a URL or a
 *  file name, so it only unwraps around text that looks like words. */
function unwrapInline(text) {
  return (
    text
      .replace(/\[\[\s*\d+\s*\]\]\(\)/g, "") // wiki cite marker, e.g. [[ 12 ]]()
      // One level of nesting inside the label, because Wikipedia's markdown
      // produces both `[ [edit](url) ]` and
      // `[[miˈlit͡sja ɔbɨvaˈtɛlska]](/wiki/Help:IPA/Polish "…")`. A regex that
      // stops at the first `]` leaves the tail of each as debris.
      .replace(/!?\[((?:[^[\]]|\[[^\]]*\])*)\]\([^)]*\)/g, "$1")
      // An orphaned tail, where the opening bracket was on a line that got
      // trimmed as structure and this one kept the rest.
      .replace(/\]\([^)]*\)/g, "")
      .replace(/\[\s*\d+\s*\]/g, "") // a bare footnote ref
      .replace(/`{3,}/g, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/(^|[\s(])_([A-Za-zÀ-ž][A-Za-zÀ-ž '’-]*)_(?=[\s.,;:!?)]|$)/g, "$1$2")
      .replace(/\s{2,}/g, " ")
      .replace(/^[\s\]|*-]+/, "")
      .trim()
  );
}

/** Does this read as a sentence a person wrote, rather than a fragment left
 *  over from a table? Length alone is not enough — `| Mundur „Tytan” | 2024 |`
 *  survives a length test and reads as nothing. */
function isProse(text) {
  if (text.length < 60) return false;
  if (!/[.!?](\s|$)/.test(text)) return false;
  // Structure that survived unwrapping disqualifies the block outright. The
  // next block is nearly always cleaner, and a quotation is worth skipping a
  // paragraph for.
  if (RESIDUE.test(text)) return false;
  // Mostly letters and spaces, rather than mostly punctuation and digits.
  const letters = (text.match(/[\p{L}\s]/gu) || []).length;
  return letters / text.length > 0.75;
}

/** The runs of consecutive prose lines, in order.
 *
 *  A structural line ENDS a run rather than being trimmed out of the middle of
 *  one, and that is the whole design. Trimming only the ends leaves a heading
 *  sitting inside a joined block, where it is no longer at the start of a line
 *  and every `^`-anchored rule stops seeing it — which is how
 *  `# Lista uzbrojenia … ## Współczesne wyposażenie` survived as a "sentence".
 *  It also keeps the quotation honest: a heading between two paragraphs is a
 *  section boundary, so text either side of it was never one passage. */
function proseRuns(text) {
  const runs = [];
  let current = [];
  for (const line of text.split("\n")) {
    if (isStructural(line)) {
      if (current.length) runs.push(current.join(" "));
      current = [];
    } else {
      current.push(line.trim());
    }
  }
  if (current.length) runs.push(current.join(" "));
  return runs;
}

/** Cut at a sentence end where there is one, and never mid-word.
 *
 *  The ellipsis is the same mark star/auth.py uses for a truncated detail, and
 *  it is appended whenever anything was dropped — including after a clean
 *  sentence break, because the passage does continue on the page. */
function capAtSentence(text, limit) {
  if (text.length <= limit) return text;
  let window = text.slice(0, limit + 1);
  // Never leave a half-written tag behind. web/clip.js hands this straight to
  // DOMPurify, whose parser would drop `<stro` silently, and the two flavours
  // of excerpt mean a <strong> really can straddle the cut.
  const open = window.lastIndexOf("<");
  if (open > window.lastIndexOf(">")) window = window.slice(0, open);
  const sentence = window.search(/[.!?](?=[\s"'”’)]|$)(?![^]*[.!?](?=[\s"'”’)]|$))/);
  if (sentence >= limit * 0.5) return `${window.slice(0, sentence + 1)} …`;
  const space = window.lastIndexOf(" ");
  return `${window.slice(0, space > 0 ? space : limit).replace(/[\s,;:—–-]+$/, "")} …`;
}

/** The page's own words, as much of them as a card can carry.
 *
 *  Never returns empty for a non-empty input. A reader seeing markup is a
 *  defect; a reader seeing nothing where a source was quoted is a worse one,
 *  so every fallback below ends somewhere rather than giving up. */
/** HTML entities, decoded once, from a fixed table plus the numeric forms.
 *
 *  THE HEADER OF THIS FILE SAYS "0 carry HTML entities", and that was true of
 *  the fifty excerpts it was measured against. It is not true of every room: a
 *  Bonhams lot description in the Substitute Sync room carries `&#x27;`, and
 *  the first defence card printed off a real room read "George Harrison&#x27;s
 *  signature" on a sheet meant to be handed to somebody. The measurement was
 *  honest and the sample was one room.
 *
 *  ONCE, NEVER RECURSIVELY, and that is a security property rather than an
 *  optimisation. A source carrying `&amp;lt;script&amp;gt;` decodes here to
 *  `&lt;script&gt;` and stops; decoding again would yield a live tag. Callers
 *  escape or sanitise AFTER this runs — web/clip.js hands the result to
 *  DOMPurify or escapeHtml and web/defend.js escapes it — so even a tag that
 *  survived a pass never reaches the DOM as markup.
 *
 *  A fixed table rather than the innerHTML round-trip. Decoding through a
 *  detached element resolves everything a browser knows, in a loop the caller
 *  cannot bound, which is exactly the behaviour the paragraph above refuses.
 */
const ENTITIES = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&apos;": "'",
  "&nbsp;": " ",
  "&ndash;": "\u2013",
  "&mdash;": "\u2014",
  "&hellip;": "\u2026",
  "&lsquo;": "\u2018",
  "&rsquo;": "\u2019",
  "&ldquo;": "\u201c",
  "&rdquo;": "\u201d",
};

export function decodeEntities(text) {
  return String(text ?? "").replace(
    /&(?:#(\d{1,7})|#[xX]([0-9a-fA-F]{1,6})|([a-zA-Z]+));/g,
    (whole, dec, hex, named) => {
      if (dec !== undefined || hex !== undefined) {
        const code = dec !== undefined ? parseInt(dec, 10) : parseInt(hex, 16);
        // Malformed or out of range is left exactly as written. A quotation is
        // not the place to guess what a broken code point meant.
        if (!Number.isFinite(code) || code <= 0 || code > 0x10ffff) return whole;
        if (code >= 0xd800 && code <= 0xdfff) return whole;
        return String.fromCodePoint(code);
      }
      return ENTITIES[`&${named};`] ?? whole;
    }
  );
}

export function excerptProse(raw, { limit = 320 } = {}) {
  const text = decodeEntities(
    String(raw ?? "")
      .replace(/\r\n/g, "\n")
      .replace(/ /g, " ")
  ).trim();
  if (!text) return "";

  const runs = proseRuns(text).map(unwrapInline).filter(Boolean);

  const chosen =
    runs.find(isProse) ||
    // Nothing reads as prose. Prefer the longest run over the raw string: it
    // has at least had the structure around it removed.
    runs.slice().sort((a, b) => b.length - a.length)[0] ||
    // Every line was structural, which happens when a source is a table and
    // nothing else — a banknote gallery, an equipment list. There is no
    // sentence on the page to quote, so the reader gets the page's own words in
    // the page's own order with the cell and heading markers taken off. It
    // reads as a run of captions, because that is what the source is. Showing
    // the pipes instead would be showing them the scraper.
    unwrapInline(
      text
        .split("\n")
        .map((line) => line.replace(/^#{1,6}\s+/, "").replace(/^[\s*+-]+/, "").replace(/\s*\|\s*/g, " "))
        .join(" ")
    );

  return capAtSentence(chosen, limit);
}
