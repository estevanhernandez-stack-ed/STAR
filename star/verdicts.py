"""Turn the verifier's prose into checked claims, or into an honest absence.

The verifier carries `parallel_search` and therefore cannot carry an
`output_schema`, so Pipeline B recovers structure after the fact exactly as
`star/findings.py` does for the researchers. The verifier writes one line per
claim:

    - <verdict> | <exact claim text> | <url>, <url> | <note>

Only the verdict and the note are the model's. Everything else in what this
module returns is computed: titles and excerpts are hydrated out of a ledger of
what search actually returned, and whether the **room** or a **fresh search**
answered a claim is decided by which of two ledgers holds the URL, never by
asking the model what it did. That is the whole reason the annotator is not a
third agent (`spec.md > Key technical decisions > Decision 2`) — a model
reporting which ledger answered is a model asserting something about its own
behaviour, and `prd.md` asks the check to report it per claim as a fact.

The one thing on the line the server can check for itself is the `budget:`
prefix, because the server counts the searches. So it is honoured only when the
run really did run out. Everything else the model says about its own effort
either holds up against a ledger or is stripped.

Nothing is dropped. A line that does not parse, a verdict for text no claim
carries, and a second line for a claim already answered all land in field
notes; a claim no line answered comes back `unverifiable` and says so.
"""

import re

# Four names from findings.py, imported rather than copied. `_resolve_citation`
# and `_best_excerpt` are named in `spec.md > File structure` as this module's
# imports; `_URL` and `_BULLET` come with them because the recovery ladder
# inside `_resolve_citation` is defined against that exact URL character class
# — it exists to undo the specific characters that regex has to exclude, so a
# second URL regex here would leave the ladder undoing exclusions that were
# never made. A URL that resolves during a room build has to resolve during a
# check against that same room, and one shared parser is what makes that so.
from star.findings import _BULLET, _URL, _best_excerpt, _resolve_citation, shares_claim_wording
from star.ledger import SourceLedger
from star.models import Citation, Claim, ClaimResult, ScriptCheckResult, Verdict

_SEPARATOR = "|"
_FIELDS = 4
_BUDGET_PREFIX = "budget:"
_VERDICTS = {verdict.value: verdict for verdict in Verdict}
_NEEDS_A_SOURCE = (Verdict.CONFIRMED.value, Verdict.ANACHRONISM.value)
_VERIFIED = re.compile(r"\bverified\b", re.IGNORECASE)


def parse_verdict_line(line: str) -> tuple[str, str, list[str], str] | None:
    """Split one verdict line into verdict, claim text, cited URLs, and note.

    Returns None for anything that is not a well-formed verdict line; the
    caller keeps those as field notes rather than dropping them. Three of the
    rejections are deliberate rather than incidental:

    `|` must appear exactly three times. A fourth means a field was cut in
    half and half of it would be silently reassigned to the next field — the
    same reasoning that makes a second `::` a parse failure in `findings.py`.
    The verifier is instructed to write ` | `, but only the count is
    load-bearing: a model that drops a space around a pipe has written a
    readable line, not a broken one.

    A bare `unverifiable` with no note is a failure, not a valid line. Every
    unverifiable a writer sees has to say what was looked for and not found
    (`prd.md > Script Check — The Pipeline`), and a line in field notes
    admitting the desk sent nothing usable is worth more than a verdict that
    says nothing.

    An unrecognised verdict word fails rather than being coerced to the
    nearest one. `unverifiable` is the safe-looking landing spot and choosing
    it here would file a claim the desk never judged as one the desk judged
    and could not settle.
    """
    match = _BULLET.match(line)
    if not match:
        return None

    body = match.group(1)
    if body.count(_SEPARATOR) != _FIELDS - 1:
        return None

    raw_verdict, text, sources, note = (
        field.strip() for field in body.split(_SEPARATOR)
    )

    verdict = raw_verdict.lower()
    if verdict not in _VERDICTS or not text:
        return None
    if verdict == Verdict.UNVERIFIABLE.value and not note:
        return None

    # Same extraction findings.py performs, including the trailing period, so
    # the ladder downstream sees candidates of the same shape in both pipelines.
    urls = [url.rstrip(".") for url in _URL.findall(sources)]
    return verdict, text, urls, note


def _same_case(match: re.Match) -> str:
    """Replace one match with `checked` in the case the model wrote."""
    word = match.group(0)
    if word.isupper():
        return "CHECKED"
    if word[0].isupper():
        return "Checked"
    return "checked"


def _restate_verified(note: str) -> str:
    """Say `checked` where the model said `verified`.

    No copy on any surface says the bare word "verified" about a source
    (`spec.md > What must not regress`), and a note is copy: it is printed
    under the stamp in the browser and returned raw to an agent over MCP. The
    rule could not be enforced upstream — `star/agents/script_check.py`
    deliberately carries no "do not say verified" instruction, because naming
    a word in a prompt is a reliable way to get that word — and it cannot be
    enforced downstream either, since the MCP door has no renderer between
    this payload and its reader. This is the one layer both consumers share,
    so this is where it goes.

    `\\b` keeps it to the standalone word: `unverified` is Pipeline A's own
    field name and `unverifiable` is a verdict, and neither is a claim about
    what a source proves.

    Field notes are deliberately left alone. They are the unparsed residue,
    kept so a low parse rate can be read back and diagnosed, and rewriting
    evidence to make it read better is a worse failure than an awkward word in
    a diagnostic block.
    """
    return _VERIFIED.sub(_same_case, note)


def _pending_by_text(claims: list[Claim]) -> dict[str, list[int]]:
    """Index the claim set by the exact text a verdict line has to repeat.

    A list of positions per text rather than a single position, so a scene
    that makes the same claim twice can receive two verdicts — and so a second
    line for a claim already answered has somewhere to fail. The list empties,
    the next match misses, and the duplicate lands in field notes instead of
    overwriting a verdict that was already filed.

    Keyed on the stripped text because parsing a `|` field necessarily strips
    it, so surrounding whitespace is the one part of the quote no line could
    carry back. The raw text is what goes out in `ClaimResult.text`, so
    `web/anchor.js` still string-matches the exact substring the extractor
    quoted.
    """
    pending: dict[str, list[int]] = {}
    for index, claim in enumerate(claims):
        pending.setdefault(claim.text.strip(), []).append(index)
    return pending


def _claim_index(pending: dict[str, list[int]], text: str) -> int | None:
    """Take the next unanswered claim carrying this text, or None."""
    positions = pending.get(text)
    if not positions:
        return None
    return positions.pop(0)


def _hydrate(
    urls: list[str], text: str, room_ledger: SourceLedger, run_ledger: SourceLedger
) -> tuple[list[Citation], list[str], list[str]]:
    """Turn cited URLs into citations two ledgers can vouch for.

    The room is asked first and the run second, so a URL both hold is recorded
    as the room's. That ordering is the department consulting its own files
    before spending, and it is what makes `citation_sources` a computed
    provenance rather than a model's account of its own searching.

    A URL neither ledger holds produces no citation at all. It comes back in
    the third list, where the claim keeps it and the surface stamps it
    UNSOURCED — the same posture `Finding.unverified_urls` takes, and the
    reason no title or excerpt in this payload can have been authored by a
    model: both are read off a ledger entry or the citation does not exist.
    """
    citations: list[Citation] = []
    sources: list[str] = []
    unsourced: list[str] = []

    for url in urls:
        for ledger, label in ((room_ledger, "room"), (run_ledger, "search")):
            entry = _resolve_citation(url, ledger)
            if entry is None:
                continue
            citations.append(
                Citation(
                    url=entry.url,
                    title=entry.title or entry.url,
                    excerpt=_best_excerpt(entry.excerpts, text),
                )
            )
            sources.append(label)
            break
        else:
            unsourced.append(url)

    return citations, sources, unsourced


def _downgrade_sentence(unsourced: list[str]) -> str:
    """Say which source could not be checked, by name where there is one."""
    if not unsourced:
        return (
            "This verdict came back with no source named, so there was nothing "
            "to check the claim against."
        )

    named = ", ".join(unsourced)
    subject = (
        f"The source named for this claim, {named}, is"
        if len(unsourced) == 1
        else f"The sources named for this claim, {named}, are"
    )
    return (
        f"{subject} in neither the room's files nor this check's search "
        "results, so there was nothing to check it against."
    )


def _open_sentence(text: str) -> str:
    """Capitalise a remainder that used to have a prefix in front of it.

    Stripping `budget:` leaves the model's clause starting mid-sentence, and
    it is either the whole note or follows a full stop. Skipped when the
    second character is already uppercase, which is what a lowercase-initial
    proper noun looks like: `iPhone` and `eBay` survive, and no other prose is
    touched.
    """
    if not text[:1].islower() or text[1:2].isupper():
        return text
    return text[0].upper() + text[1:]


def _split_budget_prefix(note: str) -> tuple[str, bool]:
    """Take `budget:` off the front of a note and report that it was there.

    The verifier is told to prefix `budget:` onto claims it could not reach
    once `parallel_search` refuses. Whether the searches actually ran out is
    the server's fact, not the model's: `star/tools/parallel_search.py` holds
    the ceiling and the count, and the caller passes the answer in. So the
    claim is separated from the note here and judged at the call site, and the
    prefix comes off either way. It is a signal to this module, not copy, and
    a note that reached a writer still wearing it would be the department's
    internal shorthand printed as an answer.
    """
    if note[: len(_BUDGET_PREFIX)].lower() != _BUDGET_PREFIX:
        return note, False
    return _open_sentence(note[len(_BUDGET_PREFIX) :].strip()), True


def _annotate_one(
    claim: Claim,
    verdict: str,
    urls: list[str],
    note: str,
    room_ledger: SourceLedger,
    run_ledger: SourceLedger,
    budget_exhausted: bool,
) -> ClaimResult:
    """Apply one parsed line to one claim: hydrate, downgrade, then budget."""
    citations, sources, unsourced = _hydrate(urls, claim.text, room_ledger, run_ledger)
    note, claimed_budget = _split_budget_prefix(note)
    reason = ""

    # `prd.md` requires every CONFIRMED and ANACHRONISM to carry at least one
    # real citation. This is where that becomes true rather than hoped for: a
    # verdict whose every source failed to resolve has nothing behind it, and
    # a stamp with nothing behind it is the overclaim the whole ledger
    # apparatus exists to prevent. `reason` stays empty — it carries the
    # department's reasons ("budget", "unreached") and this one is the world's.
    if verdict in _NEEDS_A_SOURCE and not citations:
        verdict = Verdict.UNVERIFIABLE.value
        note = f"{_downgrade_sentence(unsourced)} {note}".strip()

    # The claim is honoured only against the server's own count, and only for
    # a verdict that means the claim went unsettled. Conflating "we ran out of
    # money" with "we looked and it isn't there" is the same class of overclaim
    # the ledger check exists to prevent, and the two are answers the writer is
    # owed apart. Said in prose as well as in `reason`, because the MCP door
    # hands this payload to an agent with no renderer to turn a field into a
    # sentence.
    # Read the receipt the writer will actually be shown, and only once the
    # downgrade above has settled what the verdict is. CONFIRMED alone, for the
    # reason on `Citation.shares_claim_wording`: an anachronism is settled by a
    # page carrying a DATE, which routinely shares no wording with the line it
    # contradicts, and the measured cost of flagging those is the best row in
    # the sweep. This changes no verdict and files no note; it annotates a
    # citation the department already decided to show.
    if verdict == Verdict.CONFIRMED.value:
        citations = [
            citation.model_copy(
                update={
                    "shares_claim_wording": shares_claim_wording(
                        citation.excerpt, claim.text
                    )
                }
            )
            for citation in citations
        ]

    if claimed_budget and budget_exhausted and verdict == Verdict.UNVERIFIABLE.value:
        note = f"The check ran out of searches before reaching this claim. {note}"
        reason = "budget"
    note = note.strip()

    # One path arrives here empty: a line reading `budget:` and nothing else,
    # on a run that did not exhaust its budget. The prefix was the whole note,
    # stripping it left nothing, and an unverifiable with no note fails
    # `prd.md`'s criterion at the last step of a function whose job is to keep
    # it. What is true in that case is exactly this sentence.
    if verdict == Verdict.UNVERIFIABLE.value and not note:
        note = "The check did not settle this claim and did not say what it looked for."

    return ClaimResult(
        text=claim.text,
        claim_type=claim.claim_type,
        verdict=_VERDICTS[verdict],
        note=_restate_verified(note),
        citations=citations,
        citation_sources=sources,
        unsourced_urls=unsourced,
        reason=reason,
    )


def _unreached(claim: Claim) -> ClaimResult:
    """A claim no line answered, or none the parser could read.

    Two paths land here and the note has to be true of both: the verifier
    never wrote a line for this claim, or it wrote one that failed the grammar
    and is sitting in field notes. From the writer's side those are the same
    event — nothing came back — and the field notes are where the difference
    is legible.
    """
    return ClaimResult(
        text=claim.text,
        claim_type=claim.claim_type,
        verdict=Verdict.UNVERIFIABLE,
        note="The check did not come back with a verdict for this claim.",
        reason="unreached",
    )


# The claim vocabulary, grouped as a reader thinks rather than as the schema
# lists it. The split is the point of `_scope_note` below: the first group is
# what this check reliably finds, and the second is what it has been measured
# missing.
_NAMED_THINGS = {
    "object": "objects",
    "technology": "technology",
    "geography": "places",
    "language": "words and phrases",
}
_ASSERTED_HAPPENINGS = {
    "behavior": "how people behaved or what they were allowed to do",
    "timing": "timings and durations",
}


def _scope_note(claims: list[ClaimResult]) -> str:
    """What this check examined, and -- said out loud -- what it did not.

    THE FINDING THIS EXISTS FOR. A hostile reader salted a 1978 Gdansk scene
    with three period errors on 2026-08-11 and the check returned nine
    confirmed, one anachronism, zero unverifiable. Every planted error was
    procedural -- guards waving a shift through without a search, oranges
    bought without queueing, a duplicating machine that was the wrong machine
    -- and not one of them was ever EXTRACTED, so not one was ever checked. The
    scene came back with a clean bill of health it had not earned.

    Nothing malfunctioned at any step. Every claim that was checked was checked
    honestly, hydrated against a real ledger, and stamped correctly. The lie was
    in the shape of the summary: nine green stamps on a page carrying three
    errors, with nothing saying which parts had been looked at.

    That is the failure this project's own aversion research names -- citation
    presence reading as a trust signal independent of accuracy -- arriving
    through the one door every other guard here faces the other way. Hydration,
    the downgrade and the unsourced stamp all defend against OVERCLAIMING A
    SOURCE. None of them defends against underclaiming what the check left
    alone.

    So this counts what was actually extracted, by type, and names which kinds
    of assertion are missing from the claim set. It does NOT guess how many
    unchecked assertions the scene contained: knowing that would mean finding
    them, and anything findable would have been checked. Printing "three
    unexamined claims" without having found them would be the same invention
    the whole ledger apparatus exists to refuse.
    """
    if not claims:
        return ""

    seen = {str(c.claim_type or "").strip().lower() for c in claims}
    named = sorted({label for key, label in _NAMED_THINGS.items() if key in seen})
    asserted = sorted(
        {label for key, label in _ASSERTED_HAPPENINGS.items() if key in seen}
    )

    count = len(claims)
    plural = "claim" if count == 1 else "claims"
    examined = ", ".join(named + asserted) or "claims of no stated kind"
    note = f"This check examined {count} {plural}, about {examined}."

    missing = [label for key, label in _ASSERTED_HAPPENINGS.items() if key not in seen]
    if missing:
        note += (
            " Nothing here is a claim about "
            + " or ".join(sorted(missing))
            + ". If the scene asserts any of that, it was not examined."
        )
    return note


def annotate(
    prose: str | None,
    claims: list[Claim],
    room_ledger: SourceLedger,
    run_ledger: SourceLedger,
    budget_exhausted: bool,
    *,
    scene_id: str = "",
    created_at: str = "",
    search_count: int = 0,
) -> ScriptCheckResult:
    """Join the verifier's prose to two ledgers, producing a filed check.

    Claims come back in the order the extractor found them, not the order the
    verifier answered them, so the marked scene reads down the page.

    `parse_rate` counts parsed lines over bullet lines, the same measure and
    the same reason as `parse_findings`: it is what decides whether the prose
    format holds or the schema'd-structurer fallback gets built. A line that
    parses and then matches no claim counts as parsed — the grammar held, the
    claim set is a separate question, and charging one against the other would
    make a clean parse read as a broken one.

    `scene_id`, `created_at`, and `search_count` are the caller's to supply.
    This module reads no clock and counts no searches; that is what lets a
    golden fixture be replayed through it and come back byte-identical.

    `claims` is a list of validated `Claim`s. ADK leaves the extractor's
    output in session state as a plain dict, so the caller runs it through
    `ClaimSet` first — a check whose claim set failed validation is a failure
    worth seeing, not one to paper over here.
    """
    raw = prose or ""
    results: list[ClaimResult | None] = [None] * len(claims)
    pending = _pending_by_text(claims)
    notes: list[str] = []
    bullet_lines = 0
    parsed_lines = 0

    for line in raw.splitlines():
        if not _BULLET.match(line):
            # Headers and closing paragraphs are legitimate prose. Kept, like
            # everything else that is not a verdict, and not counted against
            # the parse rate.
            if line.strip():
                notes.append(line.rstrip())
            continue

        bullet_lines += 1
        parsed = parse_verdict_line(line)
        if parsed is None:
            notes.append(line.rstrip())
            continue

        parsed_lines += 1
        verdict, text, urls, note = parsed
        index = _claim_index(pending, text)
        if index is None:
            # A verdict for text that is not in the claim set, or a second
            # verdict for a claim already answered. Either way it is not a
            # claim this scene made, and it is not thrown away.
            notes.append(line.rstrip())
            continue

        results[index] = _annotate_one(
            claims[index],
            verdict,
            urls,
            note,
            room_ledger,
            run_ledger,
            budget_exhausted,
        )

    claim_results = [
        result if result is not None else _unreached(claim)
        for claim, result in zip(claims, results, strict=True)
    ]
    parse_rate = (parsed_lines / bullet_lines) if bullet_lines else 0.0

    return ScriptCheckResult(
        scene_id=scene_id,
        created_at=created_at,
        claims=claim_results,
        parse_rate=round(parse_rate, 3),
        unsourced_count=sum(len(result.unsourced_urls) for result in claim_results),
        # A claim counts once however many receipts it was shown, and only when
        # EVERY one of them missed. A claim holding one page that repeats it and
        # one that does not has an answer behind it, and counting that as a miss
        # would inflate the number the writer is being asked to trust.
        unmatched_citations=sum(
            1
            for result in claim_results
            if result.citations
            and all(
                citation.shares_claim_wording is False for citation in result.citations
            )
        ),
        field_notes="\n".join(notes).strip(),
        search_count=search_count,
        budget_exhausted=budget_exhausted,
        scope_note=_scope_note(claim_results),
    )
