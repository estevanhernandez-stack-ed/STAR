"""Gathering a draft's claims: what merges, what does not, and what it costs.

The whole feature rests on one number — how much smaller the distinct set is
than the raw one — and on one rule: two claims are the same only when they say
the same thing. Merge too eagerly and a verdict about a '61 Impala is reported
against a scene that said '62. Merge too shyly and the writer pays for the same
search four times.
"""

from star.sweep import attach, gather, normalised


def test_the_same_object_quoted_in_four_scenes_is_asked_about_once():
    """The arithmetic the feature exists for.

    A draft repeats its world. Extraction is free — the claim desk holds no
    tools — so the cost is the number of DISTINCT things asked about, not the
    number of times the draft asserts them.
    """
    per_scene = [
        (1, [{"text": "the TARDIS", "claim_type": "object"}]),
        (3, [{"text": "the TARDIS", "claim_type": "object"},
             {"text": "a Leyland Titan", "claim_type": "object"}]),
        (7, [{"text": "the TARDIS", "claim_type": "object"}]),
        (12, [{"text": "the TARDIS", "claim_type": "object"},
              {"text": "the Kaiserkeller", "claim_type": "place"}]),
    ]

    claims, scenes = gather(per_scene)

    assert [c["text"] for c in claims] == [
        "the TARDIS",
        "a Leyland Titan",
        "the Kaiserkeller",
    ], "three distinct claims out of six raised"
    assert scenes[normalised("the TARDIS")] == [1, 3, 7, 12], "and it knows where each was said"
    assert scenes[normalised("the Kaiserkeller")] == [12]


def test_two_claims_that_differ_by_a_digit_are_two_claims():
    """The merge that must not happen.

    A verdict about a '61 Impala reported against the scene that said '62 is
    worse than no sweep at all: it is a wrong answer wearing a citation, in a
    scene the writer was never warned about.
    """
    claims, _ = gather(
        [
            (1, [{"text": "a '61 Impala"}]),
            (2, [{"text": "a '62 Impala"}]),
            (3, [{"text": "9:36 PM"}]),
            (4, [{"text": "936 PM"}]),
        ]
    )

    assert len(claims) == 4, "a digit is the claim, not noise around it"


def test_the_same_claim_wearing_different_punctuation_is_one_claim():
    """The merge that must. A claim is an exact quotation from a scene, so the
    same object arrives wrapped in whatever the line wrapped it in."""
    claims, scenes = gather(
        [
            (1, [{"text": '"Candid Camera"'}]),
            (2, [{"text": "Candid Camera."}]),
            (5, [{"text": "  candid camera  "}]),
        ]
    )

    assert len(claims) == 1
    assert claims[0]["text"] == '"Candid Camera"', "the first wording is what the writer sees"
    assert scenes[normalised("Candid Camera")] == [1, 2, 5]


def test_a_leading_article_does_not_make_a_second_claim():
    """Measured against a real draft before it was written.

    `kaiserkeller` appeared in four scenes and `the kaiserkeller` in three, and
    without this they were two claims and the writer paid to ask about one
    place twice. Five such pairs in a twenty-four scene feature.
    """
    claims, scenes = gather(
        [
            (1, [{"text": "the Kaiserkeller"}]),
            (4, [{"text": "Kaiserkeller"}]),
            (9, [{"text": "a Vespa"}]),
            (11, [{"text": "Vespa"}]),
        ]
    )

    assert len(claims) == 2, "one club and one scooter"
    assert scenes[normalised("Kaiserkeller")] == [1, 4]
    assert scenes[normalised("Vespa")] == [9, 11]


def test_dropping_the_article_still_keeps_a_digit_apart():
    """The case the looseness must not reach. A verdict about a '61 Impala
    reported against the scene that said '62 is a wrong answer wearing a
    citation."""
    claims, _ = gather([(1, [{"text": "a '61 Impala"}]), (2, [{"text": "a '62 Impala"}])])

    assert len(claims) == 2


def test_punctuation_inside_a_claim_is_left_alone():
    # The article goes; the apostrophe in `'61` does not, because that is the
    # claim rather than punctuation around it.
    assert normalised("a '61 Impala") == "'61 impala"
    assert normalised("9:36 PM") == "9:36 pm"
    assert normalised('  "the TARDIS."  ') == "tardis"
    assert normalised("") == ""
    assert normalised(None) == ""
    # Only a LEADING article, and only as a whole word. A claim that is nothing
    # but an article is left as it is rather than emptied.
    assert normalised("the") == "the"
    assert normalised("anvil") == "anvil", "not an- + vil"


def test_a_claim_with_no_text_is_not_a_claim():
    claims, _ = gather([(1, [{"text": ""}, {"text": "   "}, {}, {"text": "real"}])])

    assert [c["text"] for c in claims] == ["real"]


def test_verdicts_come_back_beside_the_scenes_that_made_them():
    _, scenes = gather(
        [(1, [{"text": "the TARDIS"}]), (4, [{"text": "the TARDIS"}]), (4, [{"text": "a Vespa"}])]
    )
    verified = [
        {"text": "the TARDIS", "verdict": "confirmed"},
        {"text": "a Vespa", "verdict": "anachronism"},
    ]

    out = attach(verified, scenes)

    assert out[0]["scenes"] == [1, 4], "so a writer knows which pages to open"
    assert out[1]["scenes"] == [4]
    assert out[0]["verdict"] == "confirmed", "and the verdict is untouched"


def test_a_verdict_whose_wording_came_back_altered_keeps_its_answer():
    """Losing a verdict to protect the bookkeeping is the wrong trade.

    The verifier is a model and may return a claim it has tidied. The scene
    list is then unknown, and an empty list says exactly that — but the
    verdict, which is the thing the writer is paying for, survives.
    """
    _, scenes = gather([(1, [{"text": "the TARDIS"}])])

    out = attach([{"text": "The TARDIS, blue", "verdict": "unverifiable"}], scenes)

    assert out[0]["verdict"] == "unverifiable"
    assert out[0]["scenes"] == []


def test_gathering_nothing_is_a_result_rather_than_a_failure():
    claims, scenes = gather([])
    assert claims == [] and scenes == {}

    claims, scenes = gather([(1, []), (2, None)])
    assert claims == [] and scenes == {}
