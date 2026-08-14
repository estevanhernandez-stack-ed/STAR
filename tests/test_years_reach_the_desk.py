"""The desk judges by a year, and the era is not in the prompt at all.

THE HISTORY, because this file has been rewritten twice and the reasons matter
more than the assertions.

It was first written when `check_state` passed the scene, the room's files and a
search budget, and the verifier's own standard was whether a claim held "for
this story's era and place" — a term never defined for the desk applying it. So
the era was passed in. That made things worse. Four sweeps, four notes, every
one reasoning from the span: "fitting the 1958-1962 era", "key year within the
1958-1962 era", "opening year of the 1958-1962 story era". The desk had been
handed the widest date in the building and checked membership in it, which
turned a vague rubber stamp into a reasoned one.

Then each claim was given the years of the scenes asserting it, and a scene
dated 1962 by a SUPER still came back judged against 1958.

WHAT SETTLED IT was rendering this prompt with ADK's own `inject_session_state`
and reading it, rather than guessing. The years were arriving — `years:
['1962']` sat plainly on the claim. The era had a labelled block on its own
line, in a tag named after what it means; the year was a key inside a dict
repr, inside a list, inside another dict. One of those reads like a fact. We
gave the wrong number the better seat and wrote a paragraph asking for the
other one.

So the seat is reassigned and the era is gone. It was misused in every note it
ever appeared in, it is the widest date in the room, and it now has a
replacement that is right. A date that can only mislead has no job left.

AND THE SCENE CHECK HAS A YEAR FOR THE FIRST TIME. The verifier never sees
`{scene}` — only the extractor does — so a single-scene check could not read a
slugline even in principle. It judged by the room's era or by nothing at all,
and nothing in four rounds of investigation had looked at that path.
"""

from star import server, sweep
from star.agents import sweep as agent_sweep
from star.agents.script_check import check_state, verifier

DRAFT = [
    {"index": 1, "text": "INT. CELLAR - NIGHT (1958)\n\nTea goes cold.\n\nJOHN\nLater."},
    {"index": 2, "text": "INT. BACK ROOM - NIGHT\n\nAn amp sits there.\n\nPAUL\nWhose?"},
    {"index": 3, "text": "EXT. DOCKS - DAY\n\nGulls.\n\nSUPER: \"Hamburg, 1962.\"\n\nA crate."},
]


def test_the_era_is_not_in_the_prompt_at_all():
    """The load-bearing assertion of this whole file. Every wrong verdict in
    four rounds cited the era, and it is the one thing that cannot be half
    removed — a desk that can still see a span will reach for it."""
    prompt = verifier.instruction

    assert "{era" not in prompt
    assert "story_era" not in prompt
    assert "Nothing else in this prompt is a date you may judge by" in prompt


def test_a_scene_check_is_told_its_year():
    """Never true before. The verifier does not see `{scene}`, so a one-scene
    check had no way to know the year even in principle."""
    assert check_state("a scene", "files", "1958")["years"] == "1958"


def test_a_sweep_is_told_the_draft_s_years():
    assert agent_sweep.verify_state({"claims": []}, "files", "1958, 1962")["years"] == "1958, 1962"


def test_both_builders_fill_the_same_slot():
    """The seam. Two builders feed one agent, and a slot filled by only one of
    them means a sweep judges by a standard a scene check does not."""
    assert "{years?}" in verifier.instruction
    assert "years" in check_state("s", "f", "1958")
    assert "years" in agent_sweep.verify_state({"claims": []}, "f", "1958")


def test_the_draft_s_years_are_stated_oldest_first_and_deduped():
    assert server._draft_years(DRAFT) == "1958, 1962"


def test_a_draft_that_states_no_year_yields_nothing_to_judge_by():
    """`{years?}` renders empty and the prompt tells the desk to say so rather
    than reach for a period. There is no era left to fall back on."""
    assert server._draft_years([{"index": 1, "text": "INT. A ROOM - DAY\n\nHe waits."}]) == ""
    assert server._draft_years([]) == ""


def test_the_desk_is_told_to_write_the_year_into_the_note():
    """Four wrong answers in a row all had notes that did not name the year
    they judged against. A verdict whose working is invisible is the one that
    cannot be caught by reading it."""
    prompt = verifier.instruction

    assert "WRITE THE YEAR INTO YOUR NOTE, every time" in prompt
    assert "'Fits the period' is not" in prompt


def test_the_desk_is_told_what_to_do_with_no_year_rather_than_left_to_guess():
    prompt = verifier.instruction

    assert "the draft states no year" in prompt
    assert "do not reach for a period, a decade or a setting to stand in for one" in prompt


def test_a_claim_must_still_hold_in_every_year_it_appears():
    prompt = verifier.instruction

    assert "MUST HOLD IN ALL OF THEM" in prompt
    assert "correct from 1959, so wrong in the 1958 scene" in prompt


def test_the_check_path_reads_its_year_off_the_scene_it_was_given():
    """End to end over the two functions that run, not over a string I typed."""
    scene = DRAFT[2]["text"]

    assert check_state(scene, "", sweep.scene_year(scene))["years"] == "1962"


def test_both_builders_still_work_with_no_year():
    assert check_state("scene", "files")["years"] == ""
    assert agent_sweep.verify_state({"claims": []}, "files")["years"] == ""


def test_the_definition_of_confirmed_does_not_send_the_desk_back_to_the_era():
    """THE ONE THAT PROBABLY BROKE EVERY EARLIER ATTEMPT.

    `confirmed` was defined as "a source you actually read holds the claim up
    for this story's era and place" — while four paragraphs above it said not
    to judge by an era. A desk being told what a word MEANS and then told not
    to apply the meaning is being asked to disobey a definition, which is not
    an argument a rule wins.

    Four rounds of investigation rewrote the instructions and never once looked
    at what the instructions were instructing ABOUT. It was found by grepping
    the RENDERED prompt for the word, rather than trusting that deleting the
    era block had deleted the era.
    """
    prompt = verifier.instruction

    assert "holds the claim up IN THE YEAR it is asserted in" in prompt
    assert "story's era and place" not in prompt
    assert "puts it outside that year or that place" in prompt


def test_the_word_era_survives_in_exactly_one_place_and_it_is_the_refusal():
    """A whole-prompt audit rather than a spot check, because this word has now
    been removed three times and turned up again twice. The only mention left
    is the sentence telling the desk there is no era to fall back on."""
    import re

    mentions = [m.start() for m in re.finditer(r"era", verifier.instruction)]

    assert len(mentions) == 1, [
        verifier.instruction[max(0, m - 60) : m + 40] for m in mentions
    ]
    assert "There is no era in this prompt to fall back on" in verifier.instruction
