"""One draft's claims, gathered across its scenes and asked once.

WHAT THIS IS FOR. `check_scene` takes one scene and is right to: a filed check
marks the scene it checked, and the marks have to sit on text. But a draft's
errors are not all inside one scene. A guitar that is fine in Liverpool in 1958
is wrong in Hamburg in 1960, and neither scene is wrong on its own — the draft
is. Checking twenty-four scenes one at a time also asks a writer to pay
twenty-four times for a world that barely changes between them.

THE ARITHMETIC IS THE WHOLE ARGUMENT. Extraction is a schema'd model call with
NO tools (star/agents/script_check.py's claim_extractor); only the verifier
holds `parallel_search`. So pulling the claims out of every scene in a feature
costs nothing but model time, and what costs money is asking about them. A
draft repeats itself — the TARDIS, the bus, the Kaiserkeller stage, the drum
kit — so the set of DISTINCT things a screenplay asserts is far smaller than
the number of times it asserts them. Gather first, dedupe, then ask once.

WHAT COUNTS AS THE SAME CLAIM, and why the rule is dull on purpose. Two claims
are the same when their quoted text matches after case and whitespace are
folded and surrounding punctuation is dropped. Nothing cleverer. A fuzzy match
would merge "a '61 Impala" with "a '62 Impala" and answer one with the other's
sources — the same failure star/defence.py refuses when it will not find a fact
by approximation, and worse here because the merged answer is then reported
against every scene both appeared in.

The cost of being dull is a missed merge: "the TARDIS" and "TARDIS" are one
object quoted two ways, and this asks about both. That is a wasted search, not
a wrong answer, and those are not the same kind of mistake.

Pure. No IO, no clock, no model.
"""

import re

_EDGE = re.compile(r"^[\s\"'‘’“”(\[.,;:!?-]+|[\s\"'‘’“”)\].,;:!?-]+$")

# A leading article, and nothing else fuzzy. Measured against the real draft:
# without this, `kaiserkeller` and `the kaiserkeller` are two claims and the
# writer pays to ask about one place twice. It merged five pairs in a
# twenty-four scene feature and did not merge the case that matters — `a '61
# Impala` and `a '62 Impala` stay apart, because the digit is the claim.
#
# `the doctor` and `a doctor` do merge, which is the honest cost. For a
# question about the world they are the same object, and a verdict about one
# is the answer for the other; this is not the citation card, where merging two
# facts would put real sources behind a sentence nobody wrote.
_ARTICLE = re.compile(r"^(the|a|an)\s+")


def normalised(text: object) -> str:
    """One claim, comparable.

    Case, runs of whitespace, punctuation at the ENDS, and a leading article.
    Punctuation INSIDE is left exactly where it is, because it is doing work:
    `9:36 PM` and `936 PM` are a time and a number.

    Deliberately looser than star/defence.py's rule and deliberately not by
    much. That one is finding the single fact a writer is holding, where a near
    match is a wrong answer wearing a citation. This one is deciding whether to
    ask the same question twice, where a missed merge costs a search and a
    wrong merge costs a verdict reported against a scene that never said it.
    Both are real; only one of them is a lie.
    """
    folded = " ".join(str(text or "").split()).casefold()
    while folded and _EDGE.match(folded[0]):
        folded = folded[1:]
    while folded and _EDGE.match(folded[-1]):
        folded = folded[:-1]
    return _ARTICLE.sub("", folded)


def gather(per_scene: list[tuple[int, list[dict]]]) -> tuple[list[dict], dict[str, list[int]]]:
    """Every scene's claims, collapsed to the distinct set, in first-seen order.

    Takes `[(scene_index, claims)]` and returns the deduped claims plus a map
    from each claim's normalised text to every scene index it appeared in.

    FIRST-SEEN ORDER, not sorted. The order a draft raises things in is the
    order a writer reads them in, and a set sorted by frequency or alphabet
    would hand back a list whose shape says something about the draft that the
    draft does not say about itself.

    The FIRST occurrence's wording is kept. A later scene quoting the same
    claim with different capitalisation does not get to rewrite what the writer
    is shown, and the scene list underneath already records that both said it.
    """
    claims: list[dict] = []
    scenes: dict[str, list[int]] = {}

    for index, found in per_scene:
        for claim in found or []:
            text = str((claim or {}).get("text") or "").strip()
            if not text:
                continue
            key = normalised(text)
            if not key:
                continue
            if key not in scenes:
                scenes[key] = []
                claims.append(dict(claim))
            if index not in scenes[key]:
                scenes[key].append(index)

    return claims, scenes


def attach(claims: list[dict], scenes: dict[str, list[int]]) -> list[dict]:
    """Put each verified claim back beside the scenes that made it.

    Done AFTER verification rather than before, because the verifier is given
    the deduped set and knows nothing about scenes — and should not. Its job is
    whether a claim holds, which is not a question about where in a draft it
    was said.

    A claim the verifier returned that this map has never heard of keeps an
    empty list rather than being dropped. Losing a verdict because its wording
    came back altered would be losing the answer to protect the bookkeeping.
    """
    out = []
    for claim in claims:
        found = scenes.get(normalised((claim or {}).get("text")), [])
        out.append({**claim, "scenes": list(found)})
    return out
