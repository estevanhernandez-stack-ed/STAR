"""A claim is judged against the years its scenes state, not the story's era.

THE DEFECT, measured live on sweep `0b65b4d842a1`. One scene, one claim, no
deduplication possible:

    INT. CASBAH CELLAR - NIGHT (1958)
    ... A Vox AC30 amplifier hums in the corner ...

    "Vox AC30 amplifier" — confirmed
    "Introduced in 1959 by British manufacturer Vox, fitting the 1958-1962 era."

The desk wrote its reasoning down. The AC30 is 1959, the era is 1958-1962, 1959
sits inside it, therefore confirmed. **It compared the object's date to the
ERA and never to the SCENE'S YEAR.** The slugline said 1958 and played no part,
because the era was the only date it had ever been handed.

Two earlier attempts missed this. The first blamed the import path — real, and
not this. The second passed the room's era into the prompt, which handed the
desk the widest window in the building and turned a vague rubber stamp into a
reasoned one.

Nothing in this codebase parsed a year from a scene. The server held every
scene's text at the moment it mattered, read it for extraction, and threw it
away.

WHY THE YEARS RIDE ON THE CLAIM rather than splitting the dedup: two claims
with identical text come back from the verifier indistinguishable, so `attach`
could not put the verdicts beside the right scenes, and the desk would be asked
— and paid — twice for one question. One claim carrying every year it is
asserted in is both cheaper and the only shape that can say "right on page 40,
wrong on page 2."
"""

from star import sweep
from star.agents.script_check import verifier

SLUG_1958 = "INT. CASBAH CELLAR - NIGHT (1958)\n\nA Vox AC30 hums.\n\nJOHN\nGive it here."
SLUG_1961 = "INT. KAISERKELLER - NIGHT (1961)\n\nThe same Vox AC30.\n\nPAUL\nAll of it."
NO_YEAR = "INT. A ROOM - NIGHT\n\nSomebody waits."


def test_a_slugline_year_is_read():
    assert sweep.scene_year(SLUG_1958) == "1958"
    assert sweep.scene_year(SLUG_1961) == "1961"


def test_a_scene_that_states_no_year_says_so():
    assert sweep.scene_year(NO_YEAR) == ""
    assert sweep.scene_year("") == ""


def test_a_year_deep_in_dialogue_is_not_the_scene_s_year():
    """A character talking ABOUT a year does not move the scene to it. "My dad
    was born in 1931" is a line, not a slugline, and reading the whole scene
    would let any remembered date relocate the page."""
    scene = "INT. PUB - NIGHT\n\nThey drink.\n\nJOHN\nMy dad was born in 1931.\n"

    assert sweep.scene_year(scene) == ""


def test_a_super_under_the_slugline_still_counts():
    """Where a screenplay actually puts a date it wants read."""
    scene = 'EXT. DOCKS - DAY\n\nSUPER: "Hamburg, 1960."\n\nThe crane swings.'

    assert sweep.scene_year(scene) == "1960"


def test_numbers_that_are_not_years_are_not_years():
    """A room number, a price and a running time all look like this."""
    assert sweep.scene_year("INT. ROOM 402 - NIGHT\n\nHe pays 1s 8d.") == ""
    assert sweep.scene_year("INT. SUITE 1200 - DAY\n\nA wait.") == ""
    assert sweep.scene_year("INT. HALL - DAY\n\n2400 people.") == ""


def test_an_unstated_year_inherits_the_last_one_stated():
    """THE POINT. A screenplay states its year once and carries it — scene 1
    says 1958 and scenes 2 and 3 say nothing because a reader knows. Reading
    each scene alone would leave every scene but the first undated, which is
    the state that produced the defect."""
    years = sweep.scene_years([
        {"index": 1, "text": SLUG_1958},
        {"index": 2, "text": NO_YEAR},
        {"index": 3, "text": SLUG_1961},
        {"index": 4, "text": NO_YEAR},
    ])

    assert years == {1: "1958", 2: "1958", 3: "1961", 4: "1961"}


def test_scenes_before_any_stated_year_carry_none_rather_than_a_guess():
    years = sweep.scene_years([
        {"index": 1, "text": NO_YEAR},
        {"index": 2, "text": SLUG_1958},
    ])

    assert years == {1: "", 2: "1958"}


def test_inheritance_follows_the_page_and_not_the_call_order():
    """`scene_years` sorts by index itself. A caller handing scenes back in
    completion order — which the sweep's own bounded gather does — must not get
    1961 inherited backwards into scene 1."""
    years = sweep.scene_years([
        {"index": 3, "text": SLUG_1961},
        {"index": 1, "text": SLUG_1958},
        {"index": 2, "text": NO_YEAR},
    ])

    assert years == {1: "1958", 2: "1958", 3: "1961"}


def test_a_claim_carries_every_year_it_is_asserted_in():
    """The AC30 case, end to end through the real gather. One claim, both
    years — not two claims, which `attach` could not tell apart on return."""
    claims, scenes = sweep.gather(
        [(1, [{"text": "Vox AC30 amplifier"}]), (2, [{"text": "Vox AC30 amplifier"}])],
        {1: "1958", 2: "1961"},
    )

    assert len(claims) == 1, "still one question, still asked once"
    assert claims[0]["years"] == ["1958", "1961"]
    assert scenes["vox ac30 amplifier"] == [1, 2]


def test_years_are_sorted_so_the_desk_reads_the_early_one_first():
    claims, _ = sweep.gather(
        [(1, [{"text": "a thing"}]), (2, [{"text": "a thing"}])],
        {1: "1961", 2: "1958"},
    )

    assert claims[0]["years"] == ["1958", "1961"]


def test_a_draft_that_states_no_year_puts_no_years_on_its_claims():
    """`{era?}`'s posture, one level down: say nothing rather than guess. The
    prompt tells the desk to fall back to the era and to admit it did."""
    claims, _ = sweep.gather([(1, [{"text": "a thing"}])], {1: ""})

    assert "years" not in claims[0]


def test_gather_still_works_uncalled_with_years():
    """Every existing caller and test passes two arguments' worth of nothing."""
    claims, _ = sweep.gather([(1, [{"text": "a thing"}])])

    assert claims[0]["text"] == "a thing"
    assert "years" not in claims[0]


def test_the_desk_is_told_the_years_outrank_the_era():
    """The rule the live sweep needed and did not have. Asserted against the
    assembled prompt, because the sentences live across string literals."""
    prompt = verifier.instruction

    assert "JUDGE AGAINST THE CLAIM'S OWN YEARS, NOT THE STORY'S ERA" in prompt
    assert "NEVER a licence for a scene" in prompt
    assert "'it fits the era' is not a verdict" in prompt


def test_the_desk_is_told_a_claim_must_hold_in_every_year_it_appears():
    """One verdict for a claim asserted twice means the failing year decides.
    Without this, "true in 1961" would be enough to confirm a claim a 1958
    scene also makes."""
    prompt = verifier.instruction

    assert "MUST HOLD IN ALL OF THEM" in prompt
    assert "the verdict is anachronism and the note says which year breaks it" in prompt
    assert "correct from 1959, so wrong in the 1958 scene" in prompt


def test_the_fallback_is_named_rather_than_silent():
    prompt = verifier.instruction

    assert "carrying no years at all" in prompt
    assert "say in the note that you did" in prompt


# --- what the agent's test of the fix turned up ------------------------------


def test_a_super_below_two_action_lines_is_still_the_scene_s_date():
    """FOUND BY THE AGENT TESTING THE FIX, 2026-08-13. This read four lines
    flat, and two lines of action before a SUPER is ordinary screenwriting. The
    flat window missed it and then inherited the PREVIOUS scene's year over the
    top of the writer's own on-page date — a silent wrong answer, which is
    worse than no answer."""
    scene = (
        "EXT. DOCKS - DAY\n\nGulls. The water is flat.\n\n"
        'A crane swings.\n\nSUPER: "Hamburg, 1958."'
    )

    assert sweep.scene_year(scene) == "1958"


def test_dialogue_below_a_character_cue_is_still_not_the_scene_s_date():
    """The window widened, so the guard that made it narrow has to hold at the
    new width. Everything after the first character cue is somebody speaking."""
    scene = (
        "INT. PUB - NIGHT\n\nThey drink. The fire is low.\n\n"
        "Somebody laughs.\n\nPAUL\nMy dad was born in 1931.\n"
    )

    assert sweep.scene_year(scene) == ""


def test_a_transition_is_not_a_character_cue():
    """`CUT TO:` and `FADE IN:` are upper-case and are not somebody speaking.
    Stopping at one would cut the head short of a SUPER below it."""
    scene = 'FADE IN:\n\nEXT. DOCKS - DAY\n\nSUPER: "Hamburg, 1958."\n\nGulls.'

    assert sweep.scene_year(scene) == "1958"


def test_a_scene_of_pure_action_does_not_scan_forever():
    """No cue to stop at, so the twelve-line cap is the only thing that does."""
    scene = "INT. HALL - DAY\n" + "\n".join(f"Line {n}." for n in range(30)) + "\n1958."

    assert sweep.scene_year(scene) == ""


def test_a_heading_naming_a_span_takes_the_earliest_year():
    """A montage. The earliest year is the safe end: a thing that did not exist
    in 1958 is wrong in the montage's first beat, so judging against 1958
    catches it and judging against 1962 lets it through. This was already the
    behaviour and it was accidental — it is a decision now."""
    assert sweep.scene_year("INT. STUDIO - NIGHT (1958-1962)\n\nThey play.") == "1958"


def test_the_extractor_is_told_a_scene_s_own_date_is_not_a_claim():
    """THE LAST ERA-REASONING NOTE. An agent testing the year fix found a scene
    headed NIGHT (1961) whose heading year was extracted as a timing claim and
    confirmed with "1961 is valid within the story setting" — judged against an
    era derived from the same writer's treatment. The department agreeing with
    the writer about when their own scene is set, and calling it verification.

    The heading year is the input the whole check runs on. It cannot also be
    its subject.
    """
    from star.agents.script_check import claim_extractor

    prompt = claim_extractor.instruction

    assert "THE SCENE'S OWN DATE STAMP IS NEVER A CLAIM" in prompt
    assert "Do not extract it" in prompt
    assert "the Empire opened in 1925" in prompt, "and the real date claim still is one"
