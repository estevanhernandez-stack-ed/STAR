/* A Fountain draft, split into the scenes a writer checks one at a time.
 *
 *  WHY THIS EXISTS. `check_scene` takes one scene. A writer with ninety pages
 *  had to find each scene in their editor, select it, paste it, wait, and go
 *  back for the next one — fifty times. The check was already the thing they
 *  came for; the intake was shaped for a demo. Fountain is what screenwriters
 *  already have on disk (Highland, Slugline, Beat, WriterDuet all export it),
 *  so the draft itself is the input.
 *
 *  SPLITTING ONLY. This does not interpret a screenplay: no character
 *  extraction, no dialogue parsing, no page counting. It finds where scenes
 *  begin and hands back the text between those points, because that is all
 *  `check_scene` needs and every additional inference is a claim about the
 *  writer's draft this file would have to be right about.
 *
 *  THE SCENE TEXT IS VERBATIM. Whatever stood between two headings is what
 *  gets checked and what gets stored, character for character. A splitter that
 *  tidied indentation or dropped a stray line would send the department
 *  something the writer never wrote, and web/scriptcheck.js's whole design —
 *  no string in it ever becomes markup — assumes the scene it renders is the
 *  scene that was submitted.
 *
 *  Written against the Fountain 1.1 syntax reference (fountain.io/syntax). The
 *  places it deliberately diverges are commented where they occur. */

/** Scene headings, per the spec: a line beginning INT, EXT, EST or I/E, or one
 *  forced with a leading period.
 *
 *  The blank lines either side are what separate a heading from a sentence
 *  that happens to start with a preposition, and both are enforced in
 *  `isHeading` where the surrounding lines are visible. The spec calls the
 *  preceding one optional; the note there records why this parser does not.
 *
 *  Case is not enforced. The spec says headings are usually uppercase and many
 *  editors write them that way, but Fountain itself accepts `int. house` and a
 *  parser that silently dropped a scene because a writer typed in lowercase
 *  would be losing pages of their draft to a convention. */
const HEADING = /^(int\.?\/ext\.?|i\/e\.?|int\b|ext\b|est\b)/i;

/** A heading forced with a period: `.SNOW GLOBE`. Two periods is an ellipsis
 *  in action, not a forced heading, which is the spec's own caveat. */
const FORCED = /^\.[^.\s]/;

/** Boneyard comments, which are invisible to everyone downstream and can span
 *  lines. Removed before anything else looks at the text: a heading inside one
 *  is not a scene, and a heading whose following blank line is inside one
 *  would otherwise stop being a heading. */
function stripBoneyard(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, "");
}

function isHeading(lines, index) {
  const line = (lines[index] || "").trim();
  if (!line) return false;
  if (!HEADING.test(line) && !FORCED.test(line)) return false;
  // The following blank line, which is most of what makes this a heading
  // rather than a sentence that starts with a preposition. End of file counts:
  // a draft that stops on its last heading still has a heading there.
  const next = lines[index + 1];
  if (next !== undefined && next.trim()) return false;
  // AND a blank line before it, which the 1.1 reference calls optional and
  // which this parser requires. The spec's own rule alone accepts the last
  // line of a paragraph: "He said INT. was short for interior. / EXT. is the
  // other one." — where the second line is followed by a blank and starts with
  // EXT, and is plainly action. Requiring the blank line above splits the
  // difference the way every editor that writes Fountain already formats, and
  // the cost of the alternative is a scene cut in half with each half checked
  // without the context that made it make sense.
  const previous = lines[index - 1];
  return previous === undefined || !previous.trim();
}

/** A heading's own text, as the writer will recognise it in their editor.
 *
 *  The forced period comes off — it is Fountain's escape character, not part
 *  of the slug — and nothing else is touched. Scene numbers in `#1#` are left
 *  where they are: they are the writer's, and a writer looking for scene 12
 *  is looking for `#12#`. */
function slug(line) {
  const text = line.trim();
  return FORCED.test(text) ? text.slice(1).trim() : text;
}

/** Every scene in a Fountain draft, in order.
 *
 *  Returns `[{ heading, text, index }]`, where `text` is the scene VERBATIM,
 *  heading line included — that is what a writer means by a scene and what the
 *  department should be checking.
 *
 *  Anything before the first heading is dropped, and that one rule is why
 *  there is no title-page handling here. A `Title:`/`Credit:`/`Author:` block
 *  sits above the first scene by definition, so it is already gone — a
 *  stripTitlePage written for this file was deleted on the day it shipped
 *  after a mutation test showed removing it changed no output on any input.
 *  Dead code carrying a confident comment about Fountain is worse than no
 *  code: the next reader budgets for a case that was never reachable.
 *
 *  In a pasted fragment the dropped part is the fragment itself, which is why
 *  `scenes()` returning empty is the signal the caller uses to fall back to
 *  treating the whole paste as one scene. A draft is not the only thing a
 *  writer pastes here and this file does not get to insist.
 */
export function scenes(draft) {
  const lines = stripBoneyard(String(draft ?? ""))
    .replace(/\r\n?/g, "\n")
    .split("\n");

  const starts = [];
  for (let i = 0; i < lines.length; i += 1) {
    if (isHeading(lines, i)) starts.push(i);
  }
  if (!starts.length) return [];

  return starts.map((start, n) => {
    const end = n + 1 < starts.length ? starts[n + 1] : lines.length;
    return {
      heading: slug(lines[start]),
      // Trailing blank lines trimmed from the END only. They are the gap
      // before the next heading rather than part of this scene, and they are
      // the difference between two identical scenes hashing the same across a
      // re-export that changed its spacing.
      text: lines.slice(start, end).join("\n").replace(/\s+$/, ""),
      index: n + 1,
    };
  });
}

/** A stable id for one scene's text, so a draft checked yesterday can say
 *  which of its scenes have moved.
 *
 *  Not a cryptographic hash and not trying to be: nothing here is a security
 *  boundary, and the question is only "is this the same text I checked
 *  before". FNV-1a because it is eight lines, has no dependencies, and this
 *  file runs in a browser with no build step.
 *
 *  Whitespace-normalised, so a re-export that reflowed the margins does not
 *  present every scene as new work. The scene TEXT sent for checking is still
 *  verbatim; only the comparison is loosened. */
export function sceneKey(text) {
  const normalised = String(text ?? "").replace(/\s+/g, " ").trim().toLowerCase();
  let hash = 0x811c9dc5;
  for (let i = 0; i < normalised.length; i += 1) {
    hash ^= normalised.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}
