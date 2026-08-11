"""What the annotator does with a verifier's prose, and with its silences.

Everything here runs with no network and no spend. The fixture below is
hand-built against the grammar `star/agents/script_check.py` instructs the
verifier to write, because item 5's live run was deferred to a verification
checkpoint that spends real money against a stored room. When that run
happens, its raw prose replaces `VERIFIER_PROSE` and its claim set replaces
`SCENE_CLAIMS`; the assertions below are written against what the two say
about each other rather than against their literal text, so the swap is an
edit to two constants.
"""

import re

from star import verdicts
from star.findings import parse_finding_line
from star.ledger import SourceLedger
from star.models import Claim, ClaimResult, Verdict
from star.verdicts import annotate, parse_verdict_line

# -- the two ledgers ---------------------------------------------------------
#
# Room sources are what a finished build filed; run sources are what this
# check's own searches returned. The split is the whole provenance question:
# nothing else in the payload says which of the two answered.

STAX = {
    "title": "Stax Museum — History",
    "url": "https://staxmuseum.example/history",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}
SOULSVILLE = {
    "title": "The Sound of Soulsville",
    "url": "https://rollingstone.example/soulsville",
    "excerpts": ["They never leveled the floor."],
}
IMPALA = {
    "title": "1961 Chevrolet Impala",
    "url": "https://impala.example/1961",
    "excerpts": ["The third generation ran from 1961 through 1964."],
}
CASSETTE = {
    "title": "The Compact Cassette at Sixty",
    "url": "https://cassette.example/history",
    "excerpts": ["Philips showed the Compact Cassette in 1963."],
}
INVENTED = "https://nowhere.example/slang-attestation"
UNFILED = "https://nowhere.example/interstate-opening"


def room_ledger():
    ledger = SourceLedger()
    ledger.record("room:setting", [STAX, SOULSVILLE])
    return ledger


def run_ledger():
    ledger = SourceLedger()
    ledger.record("verifier", [IMPALA, CASSETTE])
    return ledger


# -- the golden fixture ------------------------------------------------------

SCENE_CLAIMS = [
    Claim(text="a '61 Impala", claim_type="object"),
    Claim(text="the Stax studio floor still sloped", claim_type="geography"),
    Claim(text="punches it into the cassette deck", claim_type="technology"),
    Claim(text="dials the operator for a long-distance line", claim_type="behavior"),
    Claim(text="That's groovy", claim_type="language"),
    Claim(text="the interstate runs clear to Nashville", claim_type="geography"),
    Claim(text="a Fender Jazzmaster", claim_type="object"),
    Claim(text="the neon sign over Beale", claim_type="object"),
]

VERIFIER_PROSE = (
    f"- confirmed | a '61 Impala | {IMPALA['url']} | Sold new that year.\n"
    "- confirmed | the Stax studio floor still sloped | "
    f"{STAX['url']}, {SOULSVILLE['url']} | The theatre rake was never taken out.\n"
    "- anachronism | punches it into the cassette deck | "
    f"{CASSETTE['url']} | The cassette arrives in 1963, two years after the scene.\n"
    "- unverifiable | dials the operator for a long-distance line |  | Looked for "
    "Memphis operator practice in 1961 and found nothing about this exchange.\n"
    f"- unverifiable | That's groovy | {INVENTED} | Looked for a dated attestation "
    "in Memphis speech and could not place one.\n"
    f"- confirmed | the interstate runs clear to Nashville | {UNFILED} | Open by "
    "the year the scene is set.\n"
    "- unverifiable | a Fender Jazzmaster |  | budget: would have checked the "
    "Jazzmaster's introduction year against the scene's date.\n"
    f"- confirmed | a Studebaker in the alley | {IMPALA['url']} | Answered a claim "
    "the scene never made.\n"
    "- unverifiable | the neon sign over Beale | | Looked for the sign | and found "
    "two of them.\n"
    "Three claims leaned on the room's own files; the rest needed a search.\n"
)


def annotated(prose=VERIFIER_PROSE, claims=None, budget_exhausted=False, **kwargs):
    return annotate(
        prose,
        SCENE_CLAIMS if claims is None else claims,
        room_ledger(),
        run_ledger(),
        budget_exhausted,
        **kwargs,
    )


def by_text(result, text):
    return next(claim for claim in result.claims if claim.text == text)


# -- parse_verdict_line ------------------------------------------------------


def test_parse_line_pulls_all_four_fields():
    parsed = parse_verdict_line(
        "- confirmed | a '61 Impala | https://a.example/x | Sold new that year."
    )

    assert parsed == (
        "confirmed",
        "a '61 Impala",
        ["https://a.example/x"],
        "Sold new that year.",
    )


def test_parse_line_pulls_two_urls():
    _, _, urls, _ = parse_verdict_line(
        "- confirmed | a claim | https://a.example/x, https://b.example/y | Both agree."
    )

    assert urls == ["https://a.example/x", "https://b.example/y"]


def test_parse_line_accepts_an_empty_sources_field():
    """A claim with no source is a real answer, unlike in findings.py where a
    finding with no source is a finding with no receipts."""
    _, _, urls, note = parse_verdict_line(
        "- unverifiable | a claim |  | Looked in the trade papers and found nothing."
    )

    assert urls == []
    assert note.startswith("Looked in")


def test_parse_line_accepts_an_empty_note_on_a_sourced_verdict():
    parsed = parse_verdict_line("- confirmed | a claim | https://a.example/x | ")

    assert parsed[3] == ""


def test_parse_line_rejects_a_bare_unverifiable_with_no_note():
    """`prd.md` requires every unverifiable to say what was looked for. A line
    that says nothing is worth less than a field note admitting as much."""
    assert parse_verdict_line("- unverifiable | a claim |  | ") is None


def test_parse_line_rejects_a_fourth_pipe():
    """A fourth separator means a field was cut and half of it would be
    silently reassigned — the same call findings.py makes on a second `::`."""
    assert (
        parse_verdict_line(
            "- confirmed | a claim | https://a.example/x | note | extra"
        )
        is None
    )


def test_parse_line_rejects_a_missing_pipe():
    assert parse_verdict_line("- confirmed | a claim | https://a.example/x") is None


def test_parse_line_rejects_an_unrecognised_verdict():
    """`unverifiable` is the safe-looking landing spot, and coercing to it
    would file a claim nobody judged as one the desk judged and could not
    settle."""
    assert parse_verdict_line("- probably | a claim | | Seems right.") is None


def test_parse_line_rejects_an_empty_claim_text():
    assert parse_verdict_line("- confirmed |  | https://a.example/x | note") is None


def test_parse_line_rejects_a_non_bullet():
    assert (
        parse_verdict_line("confirmed | a claim | https://a.example/x | note") is None
    )


def test_parse_line_accepts_an_asterisk_bullet():
    """Same bullet class findings.py accepts, and for the same reason: a model
    that reaches for `*` has written a list, not a broken line."""
    assert parse_verdict_line("* confirmed | a claim | https://a.example/x | ")


def test_parse_line_tolerates_pipes_written_without_spaces():
    """The verifier is told to write ' | ', but only the count is load-bearing:
    a dropped space is a readable line, not a broken one."""
    parsed = parse_verdict_line("- confirmed|a claim|https://a.example/x|Fine.")

    assert parsed == ("confirmed", "a claim", ["https://a.example/x"], "Fine.")


def test_parse_line_strips_a_trailing_period_from_a_url():
    _, _, urls, _ = parse_verdict_line(
        "- confirmed | a claim | https://a.example/x. | note"
    )

    assert urls == ["https://a.example/x"]


def test_the_two_line_grammars_cannot_be_read_as_each_other():
    """Checked in both directions against both real parsers. A findings line
    carries no pipes and a verdict line carries no `::`, and the collision
    that would matter is a researcher's prose being read as a verdict."""
    finding = "- Stax used the old Capitol Theatre :: https://a.example/x"
    verdict = "- anachronism | a '61 Impala | https://a.example/x | Arrives in 1958."

    assert parse_verdict_line(finding) is None
    assert parse_finding_line(verdict) is None


# -- (1) parse, keeping what does not parse ----------------------------------


def test_an_unparseable_line_becomes_a_field_note_and_lowers_the_parse_rate():
    result = annotated()

    assert "the neon sign over Beale" in result.field_notes
    assert result.parse_rate == round(8 / 9, 3)


def test_prose_between_the_lines_is_kept_and_not_counted_against_the_rate():
    """A closing paragraph is legitimate prose. Charging it against the parse
    rate would make the metric lie about the format it exists to measure."""
    result = annotated()

    assert "Three claims leaned on the room's own files" in result.field_notes


def test_an_empty_claim_set_is_a_result_not_a_failure():
    result = annotate("", [], room_ledger(), run_ledger(), False)

    assert result.claims == []
    assert result.parse_rate == 0.0
    assert result.unsourced_count == 0


def test_none_prose_is_treated_as_empty():
    result = annotate(None, SCENE_CLAIMS, room_ledger(), run_ledger(), False)

    assert len(result.claims) == len(SCENE_CLAIMS)
    assert all(claim.reason == "unreached" for claim in result.claims)


# -- (2) match by exact text; orphans to field notes -------------------------


def test_a_verdict_for_text_no_claim_carries_becomes_a_field_note():
    result = annotated()

    assert "a Studebaker in the alley" in result.field_notes
    assert not any(claim.text == "a Studebaker in the alley" for claim in result.claims)


def test_an_orphan_still_counts_as_parsed():
    """The grammar held; the claim set is a separate question. Charging one
    against the other would make a clean parse read as a broken one."""
    orphan = "- confirmed | a claim nobody made | https://a.example/x | note"
    result = annotate(orphan, [], room_ledger(), run_ledger(), False)

    assert result.parse_rate == 1.0
    assert "a claim nobody made" in result.field_notes


def test_a_second_line_for_an_answered_claim_does_not_overwrite_it():
    claims = [Claim(text="a '61 Impala", claim_type="object")]
    prose = (
        f"- confirmed | a '61 Impala | {IMPALA['url']} | The first answer.\n"
        "- anachronism | a '61 Impala |  | The second answer.\n"
    )
    result = annotate(prose, claims, room_ledger(), run_ledger(), False)

    assert result.claims[0].verdict is Verdict.CONFIRMED
    assert result.claims[0].note == "The first answer."
    assert "The second answer." in result.field_notes


def test_a_scene_making_the_same_claim_twice_can_receive_two_verdicts():
    claims = [
        Claim(text="a '61 Impala", claim_type="object"),
        Claim(text="a '61 Impala", claim_type="object"),
    ]
    prose = (
        f"- confirmed | a '61 Impala | {IMPALA['url']} | First.\n"
        f"- confirmed | a '61 Impala | {IMPALA['url']} | Second.\n"
    )
    result = annotate(prose, claims, room_ledger(), run_ledger(), False)

    assert [claim.note for claim in result.claims] == ["First.", "Second."]


def test_claims_come_back_in_scene_order_not_in_the_order_answered():
    prose = (
        "- unverifiable | That's groovy |  | Second claim in the scene.\n"
        f"- confirmed | a '61 Impala | {IMPALA['url']} | First claim in the scene.\n"
    )
    claims = [SCENE_CLAIMS[0], SCENE_CLAIMS[4]]
    result = annotate(prose, claims, room_ledger(), run_ledger(), False)

    assert [claim.text for claim in result.claims] == [
        "a '61 Impala",
        "That's groovy",
    ]


# -- (3) hydrate against the room first, then the run ------------------------


def test_a_room_ledger_hit_is_hydrated_and_recorded_as_the_room():
    claim = by_text(annotated(), "the Stax studio floor still sloped")

    assert claim.citation_sources == ["room", "room"]
    assert claim.citations[0].url == STAX["url"]
    assert claim.citations[0].title == "Stax Museum — History"
    assert claim.citations[0].excerpt == STAX["excerpts"][0]


def test_a_run_ledger_hit_is_recorded_as_a_fresh_search():
    claim = by_text(annotated(), "a '61 Impala")

    assert claim.citation_sources == ["search"]
    assert claim.citations[0].title == "1961 Chevrolet Impala"
    assert claim.citations[0].excerpt == IMPALA["excerpts"][0]


def test_the_room_answers_first_when_both_ledgers_hold_the_url():
    """The department consults its own files before it spends, and the report
    of which one answered is this ordering, not the model's account of it."""
    shared = {"title": "Shared", "url": "https://shared.example/x", "excerpts": ["e"]}
    room, run = SourceLedger(), SourceLedger()
    room.record("room:setting", [shared])
    run.record("verifier", [shared])
    claims = [Claim(text="a claim", claim_type="object")]

    result = annotate(
        "- confirmed | a claim | https://shared.example/x | note",
        claims,
        room,
        run,
        False,
    )

    assert result.claims[0].citation_sources == ["room"]


def test_the_model_never_authors_a_title_or_an_excerpt():
    """Every title and excerpt in the payload is a ledger entry's, and the
    line format has no field either could have come from."""
    result = annotated()
    ledger_titles = {s["title"] for s in (STAX, SOULSVILLE, IMPALA, CASSETTE)}
    ledger_excerpts = {s["excerpts"][0] for s in (STAX, SOULSVILLE, IMPALA, CASSETTE)}

    for claim in result.claims:
        for citation in claim.citations:
            assert citation.title in ledger_titles
            assert citation.excerpt in ledger_excerpts


def test_a_truncated_url_recovers_through_the_ladder_against_the_room():
    """`_resolve_citation` is findings.py's, imported rather than reimplemented,
    so a URL that resolved during the build resolves during a check against
    the room that build filed."""
    url = "https://en.wikipedia.org/wiki/Stax_(record_label)"
    room = SourceLedger()
    room.record("room:setting", [{"title": "Stax", "url": url, "excerpts": ["A label."]}])
    claims = [Claim(text="Stax was a label", claim_type="object")]

    result = annotate(
        f"- confirmed | Stax was a label | {url[:-1]} | note",
        claims,
        room,
        SourceLedger(),
        False,
    )

    assert result.claims[0].citations[0].url == url
    assert result.claims[0].citation_sources == ["room"]
    assert result.claims[0].unsourced_urls == []


def test_the_ladder_does_not_walk_a_fabricated_url_onto_a_real_one():
    claims = [Claim(text="a claim", claim_type="object")]
    fabricated = STAX["url"] + "-fake"

    result = annotate(
        f"- unverifiable | a claim | {fabricated} | Could not place it.",
        claims,
        room_ledger(),
        run_ledger(),
        False,
    )

    assert result.claims[0].citations == []
    assert result.claims[0].unsourced_urls == [fabricated]


# -- (4) a URL in neither ledger, and the claim stays ------------------------


def test_a_url_in_neither_ledger_is_unsourced_and_the_claim_stays_on_screen():
    result = annotated()
    claim = by_text(result, "That's groovy")

    assert claim.verdict is Verdict.UNVERIFIABLE
    assert claim.citations == []
    assert claim.unsourced_urls == [INVENTED]
    assert claim.note.startswith("Looked for a dated attestation")


def test_unsourced_urls_are_counted_across_the_whole_check():
    result = annotated()

    assert result.unsourced_count == 2


# -- (5) the downgrade -------------------------------------------------------


def test_a_confirmed_with_no_hydrated_citation_is_downgraded():
    """`prd.md` requires every CONFIRMED and ANACHRONISM to carry a real
    citation. This is where that becomes true instead of hoped for."""
    claim = by_text(annotated(), "the interstate runs clear to Nashville")

    assert claim.verdict is Verdict.UNVERIFIABLE
    assert claim.citations == []


def test_the_downgrade_note_names_the_source_that_could_not_be_checked():
    claim = by_text(annotated(), "the interstate runs clear to Nashville")

    assert UNFILED in claim.note
    assert "nothing to check it against" in claim.note
    assert "Open by the year the scene is set." in claim.note


def test_a_downgrade_with_no_source_at_all_says_so():
    claims = [Claim(text="a claim", claim_type="object")]

    result = annotate(
        "- anachronism | a claim |  | Feels late for the period.",
        claims,
        room_ledger(),
        run_ledger(),
        False,
    )

    assert result.claims[0].verdict is Verdict.UNVERIFIABLE
    assert "no source named" in result.claims[0].note
    assert "Feels late for the period." in result.claims[0].note


def test_a_downgrade_is_not_charged_to_the_department_as_a_reason():
    """`reason` carries the department's reasons — budget, unreached. A verdict
    with nothing behind it is the world's answer, not the desk's excuse."""
    claim = by_text(annotated(), "the interstate runs clear to Nashville")

    assert claim.reason == ""


def test_every_confirmed_and_anachronism_carries_a_hydrated_citation():
    """The acceptance criterion, asserted over the whole fixture rather than
    one line of it."""
    result = annotated()
    stamped = [
        claim
        for claim in result.claims
        if claim.verdict in (Verdict.CONFIRMED, Verdict.ANACHRONISM)
    ]

    assert stamped
    for claim in stamped:
        assert claim.citations
        for citation in claim.citations:
            assert citation.url and citation.title and citation.excerpt


def test_every_unverifiable_carries_a_note():
    result = annotated()

    for claim in result.claims:
        if claim.verdict is Verdict.UNVERIFIABLE:
            assert claim.note


# -- (6) the budget prefix ---------------------------------------------------


def test_a_budget_prefix_is_honoured_when_the_budget_was_spent():
    claim = by_text(annotated(budget_exhausted=True), "a Fender Jazzmaster")

    assert claim.reason == "budget"
    assert claim.note.startswith("The check ran out of searches")
    assert "Jazzmaster's introduction year" in claim.note
    assert "budget:" not in claim.note


def test_a_budget_prefix_is_stripped_when_the_budget_was_not_spent():
    """The model is not the authority on which happened. The server counts the
    searches, so a `budget:` note on a run with searches left is an ordinary
    not-found wearing the department's excuse."""
    claim = by_text(annotated(budget_exhausted=False), "a Fender Jazzmaster")

    assert claim.reason == ""
    assert "budget" not in claim.note.lower()
    assert "ran out of searches" not in claim.note
    assert claim.note.startswith("Would have checked the Jazzmaster")


def test_a_budget_note_with_nothing_after_the_prefix_still_says_something():
    """The one path that empties a note: the prefix was the whole note and the
    run had searches left. An unverifiable with no note fails the criterion
    this function exists to keep."""
    claims = [Claim(text="a claim", claim_type="object")]

    result = annotate(
        "- unverifiable | a claim |  | budget:", claims, room_ledger(), run_ledger(), False
    )

    assert result.claims[0].note
    assert result.claims[0].reason == ""


def test_the_prefix_never_reaches_a_note_even_on_a_line_that_downgrades():
    """`budget:` is a signal to this module, not copy. A confirmed line
    wearing one is already contradicting itself, and the answer to that is to
    strip the shorthand and let the downgrade speak, not to print the
    department's internal marker under a stamp."""
    claims = [Claim(text="a claim", claim_type="object")]
    prose = f"- confirmed | a claim | {UNFILED} | budget: ran dry before this one."

    spent = annotate(prose, claims, room_ledger(), run_ledger(), True)
    unspent = annotate(prose, claims, room_ledger(), run_ledger(), False)

    for result in (spent, unspent):
        assert result.claims[0].verdict is Verdict.UNVERIFIABLE
        assert "budget:" not in result.claims[0].note
    assert spent.claims[0].reason == "budget"
    assert unspent.claims[0].reason == ""


def test_the_budget_flag_is_carried_onto_the_filed_check():
    assert annotated(budget_exhausted=True).budget_exhausted is True
    assert annotated(budget_exhausted=False).budget_exhausted is False


# -- (7) claims no line answered ---------------------------------------------


def test_a_claim_with_no_verdict_line_comes_back_unverifiable_and_says_so():
    """The malformed line for this claim went to field notes, so nothing
    usable came back for it. Both paths land here and the note is true of
    both."""
    claim = by_text(annotated(), "the neon sign over Beale")

    assert claim.verdict is Verdict.UNVERIFIABLE
    assert claim.reason == "unreached"
    assert "did not come back with a verdict" in claim.note
    assert claim.citations == []


def test_a_claim_the_verifier_never_mentioned_is_not_dropped():
    claims = [*SCENE_CLAIMS, Claim(text="a fourth wall", claim_type="object")]
    result = annotated(claims=claims)

    assert len(result.claims) == len(claims)
    assert by_text(result, "a fourth wall").reason == "unreached"


def test_the_claim_type_survives_the_round_trip():
    result = annotated()

    assert by_text(result, "That's groovy").claim_type == "language"
    assert by_text(result, "the neon sign over Beale").claim_type == "object"


# -- the note is copy, and copy has a rule -----------------------------------


def test_the_bare_word_verified_never_reaches_a_note():
    """No copy on any surface says it about a source. The prompt could not
    enforce it — naming a word is a reliable way to get it — and the MCP door
    has no renderer between this payload and its reader, so the deterministic
    layer both consumers share is the only place it can hold."""
    claims = [Claim(text="a claim", claim_type="object")]

    result = annotate(
        f"- confirmed | a claim | {IMPALA['url']} | Verified against two sources, "
        "and independently verified by the archive.",
        claims,
        room_ledger(),
        run_ledger(),
        False,
    )

    assert "verified" not in result.claims[0].note.lower()
    assert result.claims[0].note.startswith("Checked against two sources")
    assert "independently checked" in result.claims[0].note


def test_unverifiable_and_unverified_are_left_alone():
    """Neither word is a claim about what a source proves; one is a verdict
    and the other is Pipeline A's own field name."""
    claims = [Claim(text="a claim", claim_type="object")]

    result = annotate(
        "- unverifiable | a claim |  | Unverifiable from the unverified list alone.",
        claims,
        room_ledger(),
        run_ledger(),
        False,
    )

    assert result.claims[0].note == "Unverifiable from the unverified list alone."


# -- what the caller owns ----------------------------------------------------


def test_annotate_takes_its_identity_and_its_clock_from_the_caller():
    """This module reads no clock and counts no searches, which is what lets a
    golden fixture replay through it and come back identical."""
    bare = annotated()
    filed = annotated(scene_id="sc-1", created_at="2026-08-10T00:00:00Z", search_count=6)

    assert (bare.scene_id, bare.created_at, bare.search_count) == ("", "", 0)
    assert filed.scene_id == "sc-1"
    assert filed.created_at == "2026-08-10T00:00:00Z"
    assert filed.search_count == 6


def test_the_same_prose_annotates_the_same_way_twice():
    assert annotated().model_dump() == annotated().model_dump()


def test_the_whole_fixture_files_every_claim_it_was_given():
    """Nothing silently dropped, stated as a count: eight claims in, eight
    out, and the three lines that answered no claim all legible in field
    notes."""
    result = annotated()

    assert len(result.claims) == len(SCENE_CLAIMS)
    assert [claim.text for claim in result.claims] == [
        claim.text for claim in SCENE_CLAIMS
    ]
    assert result.field_notes.count("\n") == 2


# --- the scope note: what the check did NOT look at -------------------------


def _typed(*types):
    """Claims that differ only in kind, which is all the scope note reads."""
    return [
        ClaimResult(text=f"claim {i}", claim_type=t, verdict=Verdict.CONFIRMED, note="n")
        for i, t in enumerate(types)
    ]


def test_a_check_that_found_only_nouns_says_so():
    """The Gdansk shape, and the reason this function exists.

    Nine confirmed and one anachronism on a scene salted with three procedural
    errors, none of which was ever extracted. Every stamp was honest; the
    summary was not, because nothing said which kinds of claim had been looked
    at. The note has to name the absence, not just the presence.
    """
    note = verdicts._scope_note(_typed("object", "object", "technology", "geography"))

    assert "examined 4 claims" in note
    assert "objects" in note and "technology" in note and "places" in note
    assert "not examined" in note, "the absence is the half that matters"
    assert "how people behaved" in note


def test_a_check_that_did_reach_the_verbs_claims_no_gap():
    """The warning has to be earned, or it becomes noise a reader learns to
    skip past on the checks where it is true."""
    note = verdicts._scope_note(_typed("object", "behavior", "timing"))

    assert "examined 3 claims" in note
    assert "not examined" not in note
    assert "Nothing here is a claim about" not in note


def test_the_note_never_counts_what_it_did_not_find():
    """It says a KIND is missing, never a number of missed claims.

    Knowing how many unexamined assertions a scene held would mean having found
    them, and anything findable would have been checked. A number here would be
    the same invention the hydration and downgrade rules exist to refuse.
    """
    note = verdicts._scope_note(_typed("object", "object", "object"))

    assert "3 claims" in note, "it counts what it examined"
    # No second number anywhere: nothing claims a count of what was missed.
    assert len(re.findall(r"\d+", note)) == 1


def test_a_scene_with_no_claims_gets_no_scope_note():
    """`cover_note` already says the scene asserted nothing about the world.
    A second sentence listing what was not examined would be true and useless."""
    assert verdicts._scope_note([]) == ""


def test_annotate_puts_the_scope_note_on_the_result():
    """Computed in the annotator rather than in a renderer, for the same reason
    the `verified` rule is: the MCP door hands this payload to an agent with no
    renderer between it and the reader."""
    claims = [Claim(text="a 1961 Impala", claim_type="object")]
    prose = "- confirmed | a 1961 Impala | https://cars.example/i | Matches."
    ledger = SourceLedger()
    ledger.record("verifier", [{"url": "https://cars.example/i", "title": "I",
                                "excerpts": ["The 1961 Impala."]}])

    result = verdicts.annotate(prose, claims, SourceLedger(), ledger, False)

    assert "examined 1 claim" in result.scope_note
    assert "not examined" in result.scope_note
