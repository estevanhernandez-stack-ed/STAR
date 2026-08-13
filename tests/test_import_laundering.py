"""An imported room cannot launder a typed-in fact into a confirmed verdict.

FOUND BY AN AGENT WALKING THE DOOR, 2026-08-13, and it is the worst defect this
project has had. The agent typed "the Vox AC30 was accessible to British
musicians in the late 1950s" into a spreadsheet, imported it as a room with
`import_rooms`, and swept a 1958 scene against it. The scene came back
CONFIRMED, citing the room, with no search spent — a receipt indistinguishable
from a researched one, standing behind a claim nobody had ever checked.

Every other guard on the import path held. `import_rooms` refuses to let the
brand come off. The source count is counted from the addresses that arrived
rather than read off the file. A bible is refused on arrival because a document
about findings can describe research that did not survive the file. The room's
own summary says it was imported and claims zero searches.

And `_room_files` — the one function that decides what the verifier actually
SEES — printed a typed-in fact and a researched one in the same shape, with the
same grammar, under the same heading. The brand was on every surface a person
reads and on none the machine does.

The product's whole claim is that a verdict is only as good as the page under
it. This was the path by which a page nobody read became a verdict.
"""


from star import server
from star.agents import script_check

IMPORTED = {
    "imported_at": "2026-08-13T11:00:00+00:00",
    "search_count": 0,
    "categories": {
        "objects_and_props": {
            "findings": [
                {
                    "fact": "The Vox AC30 was accessible to British musicians in the late 1950s.",
                    "citations": [
                        {
                            "url": "https://example.invalid/vox",
                            "title": "Typed by whoever made the file",
                            "excerpt": "Anybody can put a sentence in a spreadsheet.",
                        }
                    ],
                }
            ]
        }
    },
}

RESEARCHED = {**IMPORTED, "imported_at": "", "search_count": 17}


def test_an_imported_rooms_files_declare_themselves_to_the_verifier():
    files = server._room_files(IMPORTED)

    assert "IMPORTED" in files, files
    assert "not a source" in files or "not as a source" in files, files
    assert "2026-08-13" in files, "and says when, so the reader can date it"


def test_the_banner_leads_the_block_rather_than_trailing_it():
    """A warning under the evidence is a warning read after the evidence has
    already been believed. It has to be the first thing about the block."""
    files = server._room_files(IMPORTED)

    assert files.index("IMPORTED") < files.index("Vox AC30"), files[:200]


def test_a_researched_room_carries_no_banner():
    """The mark has to MEAN something. Printing it on every room would make it
    furniture, and the verifier would learn to skip it in a week."""
    files = server._room_files(RESEARCHED)

    assert "IMPORTED" not in files
    assert "Vox AC30" in files, "but the findings are still there"


def test_an_empty_imported_room_produces_no_banner_over_nothing():
    """`_room_files` returning "" is load-bearing elsewhere: it is how
    `ledger_from_room` and the cover note agree that the room had nothing to
    say. A banner with no findings under it would break that agreement and
    make an empty room look like a full one."""
    empty = {"imported_at": "2026-08-13T11:00:00+00:00", "categories": {}}

    assert server._room_files(empty) == ""


def test_the_verifier_is_told_what_to_do_with_a_banner_it_finds():
    """Marking the files is half of it. A banner the prompt never mentions is
    a string the model may reasonably read as decoration — the fix has to
    change what the desk DOES, not only what it reads.

    ASSERTED AGAINST THE ASSEMBLED PROMPT, not the source text. This file first
    grepped `inspect.getsource` and went red on a rule that was present and
    correct, because the sentence is typed across three adjacent string
    literals and only exists as one sentence after Python joins them. The model
    reads the joined string; so does this.
    """
    prompt = script_check.verifier.instruction

    assert "PROVENANCE BANNER" in prompt
    assert "Never confirm a claim on imported material alone" in prompt
    assert "a claim cannot verify another claim" in prompt
    assert "the verdict is unverifiable" in prompt


def test_the_two_halves_use_the_same_word():
    """The prompt tells the verifier to look for a banner; `_room_files` writes
    one. If those two ever stop agreeing on the word, the rule is unreachable
    and every test above still passes — this is the seam, so it is asserted
    directly rather than trusted."""
    written = server._room_files(IMPORTED)
    instructed = script_check.verifier.instruction

    assert "PROVENANCE" in written, written[:120]
    assert "PROVENANCE" in instructed


def test_the_chain_marks_each_room_for_itself():
    """A story chain is several rooms, and importing one does not taint the
    others. The banner belongs to the room it describes."""
    files = server._room_files(IMPORTED) + "\n\n" + server._room_files(RESEARCHED)

    assert files.count("IMPORTED") == 1, "one room, one banner"
