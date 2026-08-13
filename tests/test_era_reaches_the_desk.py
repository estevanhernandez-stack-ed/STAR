"""The verification desk is told what year it is judging.

THE DEFECT, from the agent-door walk of 2026-08-13 and the surviving two thirds
of D1. A scene headed `NIGHT (1958)` said "a Vox AC30 amplifier". The AC30
shipped late 1959 into 1960 — the 1958 amp is the AC15 — and the room held a
finding written to the whole era. The scene's year sat inside the finding's
span, the desk called that overlap a match, and stamped CONFIRMED with a real
source under it.

The root was one line smaller than the symptom. The verifier's own standard is
whether a claim holds "for this story's era and place", and `check_state`
passed the scene, the room's files and a search budget. **The term the whole
standard rests on was never defined for the desk applying it.** So it inferred
the year from the slugline and from dates inside the room's findings, and when
those disagreed nothing arbitrated — the widest date in view won, because a
range containing the scene's year is the easiest thing to call a match.

The room always knew. `story_profile.era` is on every document, in every
listing, on the docket and stamped on every export, and it reached the
researchers at build time. It did not reach the desk that used it.

TWO STATE BUILDERS, ONE PROMPT. `check_state` feeds a scene check and
`verify_state` feeds a whole-draft sweep, and both hand their state to the SAME
verifier agent. A fix landing in one splits the product's two most visible
surfaces, which is the mistake `_file_notes` was extracted to stop repeating —
so the pair is asserted here rather than assumed.
"""

from star import server
from star.agents import sweep as agent_sweep
from star.agents.script_check import check_state, verifier

LIVERPOOL = ("r1", {"story_profile": {"title": "Liverpool", "era": "1958"}})
HAMBURG = ("r2", {"story_profile": {"title": "Hamburg", "era": "1960-1962"}})


def test_a_scene_check_is_told_the_era():
    assert check_state("a scene", "files", "1958")["era"] == "1958"


def test_a_sweep_is_told_the_era_too():
    """The same agent reads both. An era arriving by one road only means a
    sweep judges by a standard a scene check does not."""
    assert agent_sweep.verify_state({"claims": []}, "files", "1958")["era"] == "1958"


def test_both_builders_answer_to_the_same_prompt():
    """The seam, asserted directly. If either builder stopped naming the key
    the prompt reads, the rule would go quietly unreachable on that path and
    every other test in this file would still pass."""
    assert "{era?}" in verifier.instruction
    assert "era" in check_state("s", "f", "1958")
    assert "era" in agent_sweep.verify_state({"claims": []}, "f", "1958")


def test_the_desk_is_told_a_span_is_not_a_date():
    """Marking the era is half. The failure was not that the desk did not know
    the year — the slugline said 1958 — it was that a span CONTAINING the year
    was accepted as support. The rule is the load-bearing half."""
    prompt = verifier.instruction

    assert "A SPAN IS NOT A DATE" in prompt
    assert "true somewhere inside it rather than throughout it" in prompt
    assert "the verdict is unverifiable" in prompt
    assert "a range where the scene needed a year" in prompt


def test_the_rule_names_the_case_that_got_past_it():
    """A rule stated abstractly is a rule a model applies abstractly. The 1960
    product in a 1958 scene is the worked example, and it is in the prompt."""
    prompt = verifier.instruction

    assert "1960 is an anachronism in a 1958 scene" in prompt


def test_a_chain_names_each_rooms_era_rather_than_merging_them():
    """A Liverpool room set in 1958 and a Hamburg room set in 1960-62 are one
    story and two spans. Merging them to "1958-1962" would hand the desk a
    wider window than any scene sits in — the exact thing this change exists
    to take away."""
    era = server._chain_era([LIVERPOOL, HAMBURG])

    assert "Liverpool — 1958" in era
    assert "Hamburg — 1960-1962" in era
    assert "1958-1962" not in era, "the spans are not merged"


def test_a_room_with_no_era_contributes_nothing_rather_than_a_guess():
    """A build interrupted before its story profile was written has no era.
    `{era?}` degrades to "nobody told me", which is honest; inventing one from
    the findings is how this defect worked in the first place."""
    assert server._chain_era([("r", {})]) == ""
    assert server._chain_era([("r", {"story_profile": {"era": "  "}})]) == ""
    assert server._chain_era([]) == ""


def test_a_room_with_an_era_and_no_title_still_says_the_era():
    assert server._chain_era([("r", {"story_profile": {"era": "1958"}})]) == "1958"


def test_the_era_travels_from_the_stored_room_to_the_state():
    """End to end over the two functions that actually run, rather than over a
    string I typed. `_chain_era` reads the same `story_profile` the docket and
    every export read, and its output is what the prompt renders."""
    era = server._chain_era([LIVERPOOL])

    assert check_state("scene", "", era)["era"] == "Liverpool — 1958"
    assert agent_sweep.verify_state({"claims": []}, "", era)["era"] == "Liverpool — 1958"


def test_the_era_is_optional_everywhere_it_is_accepted():
    """Both builders keep working uncalled-with-era, because a caller that has
    no room — or a room with no profile — must still be able to run a check."""
    assert check_state("scene", "files")["era"] == ""
    assert agent_sweep.verify_state({"claims": []}, "files")["era"] == ""
