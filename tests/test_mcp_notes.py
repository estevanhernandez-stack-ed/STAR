"""The agent door gets the annotation import the browser had to itself.

A sweep could be exported from an agent and never marked up and brought back:
`get_sweep` and `export_room` were on the door, and nothing filed a writer's
notes. So the one loop this product is actually about — check a draft, take the
result away, mark it up, bring it back — stopped halfway for anyone who never
opened a browser.

WHAT THIS FILE IS REALLY GUARDING is that the agent gets the same answers a
writer does. The browser's version learned four things in a week, every one of
them from somebody using it:

  - a file from a different sweep is REFUSED, not reported, because a
    half-filed set of notes on the wrong document looks like success
  - the preview lists what would CHANGE, claim by claim, because "25 claims
    would take a note" is a count and a count is not a preview
  - an overwrite names the words it is replacing, because a stale copy of the
    file eats notes typed since and nothing else would say so
  - a claim the sweep does not hold is named back rather than dropped

All four live in `_file_notes`, which both doors call. These tests go through
the MCP handler to prove the door actually reaches them rather than
reimplementing a friendlier half.
"""

from unittest import mock

import pytest

from star import exports, server
from star.store import sweep_to_document
from tests.test_annotations import SWEEP
from tests.test_mcp_protocol import IDENTITY, carried, invoke, said
from tests.test_scenes import ROOM, UID, a_store, filed_room

SWEEP_ID = "aa11bb22cc33"


def a_door(prepare=None):
    """A store holding one filed sweep, and `_file_notes` bound to it.

    The handler is handed the SERVER'S OWN function rather than a stub. A stub
    here would pass while the door was wired to something friendlier than the
    browser's route, which is the single failure this file exists to prevent.
    """
    import copy

    document = sweep_to_document(copy.deepcopy(SWEEP), SWEEP_ID, "2026-08-13T13:35:00Z")
    if prepare:
        prepare(document)

    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep(UID, ROOM, SWEEP_ID, document)

    async def file_notes(uid, run_id, sweep_id, csv_text, apply):
        with mock.patch("star.server._store", store):
            return await server._file_notes(uid, run_id, sweep_id, csv_text, apply)

    return file_notes, client_data


def stored(client_data) -> dict:
    return client_data.data[f"users/{UID}/rooms/{ROOM}/sweeps/{SWEEP_ID}"]


async def call(csv_text, confirm=None, prepare=None, door=None):
    file_notes, client_data = door or a_door(prepare)
    arguments = {"run_id": ROOM, "sweep_id": SWEEP_ID, "csv": csv_text}
    if confirm:
        arguments["confirm"] = confirm
    result = await invoke("import_notes", arguments, file_notes=file_notes)
    return result, client_data


@pytest.mark.asyncio
async def test_the_first_call_previews_and_writes_nothing():
    result, client_data = await call("claim,writer_note\nKaiserkeller,Check the stage\n")

    assert result.get("isError") is not True, said(result)
    text = said(result)
    assert "Nothing has been changed" in text, text
    assert "writer_note" not in stored(client_data)["claims"][0], "and it means it"


@pytest.mark.asyncio
async def test_the_preview_names_each_claim_and_its_note():
    """Not a count. An agent reading "1 claim would take a mark" is in exactly
    the position the browser's reader was in, and cannot even scroll."""
    result, _ = await call("claim,writer_note\nKaiserkeller,Check the stage\n")
    text = said(result)

    assert "Kaiserkeller" in text, text
    assert "Check the stage" in text, text


@pytest.mark.asyncio
async def test_an_overwrite_names_the_words_it_replaces():
    """THE ONE THAT MATTERS. A stale copy of the file silently eats what the
    writer typed since, and no count anywhere would say so."""

    def prepare(document):
        document["claims"][0]["writer_note"] = "The note I typed on Tuesday"

    result, _ = await call(
        "claim,writer_note\nKaiserkeller,Something else\n", prepare=prepare
    )
    text = said(result)

    assert "REPLACING" in text, text
    assert "The note I typed on Tuesday" in text, text


@pytest.mark.asyncio
async def test_an_unstrike_is_named():
    """A blank `dismissed` cell restores a line struck on purpose."""

    def prepare(document):
        document["claims"][0]["dismissed"] = True

    result, _ = await call("claim,writer_note\nKaiserkeller,keep\n", prepare=prepare)

    assert "NO LONGER STRUCK" in said(result)


@pytest.mark.asyncio
async def test_a_file_that_moves_nothing_arms_nothing():
    """Re-sent unaltered. Arming a write with no effect teaches an agent that
    the confirmation is a formality, which is the opposite of its job."""

    def prepare(document):
        document["claims"][0]["writer_note"] = "Already said this"

    result, _ = await call(
        "claim,writer_note\nKaiserkeller,Already said this\n", prepare=prepare
    )
    text = said(result)

    assert "nothing to confirm" in text, text
    assert "confirm:" not in text, "and no token was offered"


@pytest.mark.asyncio
async def test_the_second_call_files_them():
    door = a_door()
    csv_text = "claim,writer_note\nKaiserkeller,Check the stage\n"

    first, client_data = await call(csv_text, door=door)
    token = carried(first)["confirm"]
    second, _ = await call(csv_text, confirm=token, door=door)

    assert "Filed 1 note" in said(second), said(second)
    claim = stored(client_data)["claims"][0]
    assert claim["writer_note"] == "Check the stage"
    assert claim["verdict"] == "confirmed", "and the department's own column is untouched"


@pytest.mark.asyncio
async def test_a_token_does_not_work_twice():
    door = a_door()
    csv_text = "claim,writer_note\nKaiserkeller,Check the stage\n"

    first, _ = await call(csv_text, door=door)
    token = carried(first)["confirm"]
    await call(csv_text, confirm=token, door=door)
    again, _ = await call(csv_text, confirm=token, door=door)

    assert again["isError"] is True
    assert "not one this file and sweep are holding" in said(again)


@pytest.mark.asyncio
async def test_a_token_minted_for_one_file_cannot_file_another():
    """Keyed on the file as well as the sweep, the way `import_rooms` is. An
    agent that previewed one file and sent a different one with the first
    file's token is one argument away from filing something nobody looked at."""
    door = a_door()

    first, _ = await call("claim,writer_note\nKaiserkeller,First file\n", door=door)
    token = carried(first)["confirm"]
    other, client_data = await call(
        "claim,writer_note\nKaiserkeller,A DIFFERENT note\n", confirm=token, door=door
    )

    assert other["isError"] is True
    assert "writer_note" not in stored(client_data)["claims"][0]


@pytest.mark.asyncio
async def test_a_file_from_another_sweep_is_refused_through_this_door_too():
    """The refusal lives in `_file_notes`, so it should arrive here for free —
    and this asserts it does rather than trusting that it does."""
    result, client_data = await call(
        "claim,sweep_id,writer_note\nKaiserkeller,f1d31518e372,keep it\n"
    )

    assert result["isError"] is True
    assert "Nothing was changed" in said(result)
    assert "writer_note" not in stored(client_data)["claims"][0]


@pytest.mark.asyncio
async def test_a_claim_this_sweep_does_not_hold_is_named_back():
    result, _ = await call(
        "claim,writer_note\n"
        "Kaiserkeller,Check the stage\n"
        "A claim that was never here,and this\n"
    )
    text = said(result)

    assert "A claim that was never here" in text, text
    assert "skipped" in text, text


@pytest.mark.asyncio
async def test_nothing_matching_is_an_answer_rather_than_an_error():
    result, _ = await call("claim,writer_note\nNot in this sweep,a note\n")
    text = said(result)

    assert result.get("isError") is not True
    assert "character for character" in text, "and it says WHY nothing matched"


@pytest.mark.asyncio
async def test_the_whole_marked_sweep_does_not_come_back_in_the_reply():
    """`claims` is the sweep's entire marked-up self and runs to hundreds of
    kilobytes on a whole-draft sweep. `changes` says everything this call did.
    Reading the other one into a model's context costs more than every other
    call on this door put together, which is the argument `export_room`'s
    summary default already makes."""
    result, _ = await call("claim,writer_note\nKaiserkeller,Check the stage\n")

    assert "claims" not in carried(result)
    assert carried(result)["changes"], "but the diff is there"


def test_the_tool_is_wired_to_the_browsers_own_function():
    """A source assertion, and the reason the rest of this file can be trusted:
    if the door were wired to its own implementation, every test above could
    pass while the two doors disagreed about what an import does."""
    import inspect

    source = inspect.getsource(server)

    assert "file_notes=_file_notes," in source, "the door is handed the shared function"
    assert "return await _file_notes(" in source, "and the browser's route calls it too"


def test_a_sweep_export_can_actually_be_read_by_the_thing_that_takes_it():
    """End to end over the real writer and the real reader rather than a
    hand-typed two-column file: `sweep_to_csv` produces what `read_annotations`
    consumes, and the id it stamps is the one the refusal checks."""
    document = sweep_to_document(SWEEP, SWEEP_ID, "2026-08-13T13:35:00Z")
    text = exports.sweep_to_csv(document)

    assert exports.annotation_origin(text) == SWEEP_ID
    marks, complaints = exports.read_annotations(text)
    assert complaints == [], "an untouched export complains about nothing"
    assert marks == {}, "and carries no marks, because nobody has typed any"


def test_the_identity_this_file_asserts_against_is_real():
    """A guard on the harness. Every call above goes through `invoke`, and a
    uid that stopped reaching the store would make all of them pass against
    nothing."""
    assert IDENTITY.uid == UID, (IDENTITY.uid, UID)
