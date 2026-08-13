"""The half of the department a desktop agent could not reach.

Sweeping a draft, exporting the files, filing somebody else's export, writing
the bible an imported room arrives without, and drawing a chain. Every one of
these existed behind the browser first, and the point of this file is that the
agent door reaches the SAME function rather than a second implementation of it
— an agent importing a room and a writer importing one must not end up with
different rules about what an imported room is.

The seam is `Calls`, so nothing here runs a model or touches Firestore. What is
testable is what an agent is told, what it is refused, and what it is charged.
"""

import json

import pytest

from star.mcp import tools
from tests.test_mcp_protocol import IDENTITY, invoke, said


def data(result: dict) -> dict:
    """The JSON half of a `_payload`, which is what follows the last blank line."""
    return json.loads(said(result).rsplit("\n\n", 1)[-1])


RESEARCH_CSV = (
    "drawer,fact,source_title,source_url,source_excerpt,retrieved_at,"
    "requisition,room,era,continues,run_id\r\n"
    "setting,Mona Best opened the Casbah.,The Casbah,https://casbah.example,"
    "A cellar.,2026-08-13,,Liverpool,1958-1962,,liv-1\r\n"
)


# -- sweep_draft --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_sweep_reports_the_arithmetic_that_justifies_it():
    """The gap between claims raised and claims asked about IS the feature. An
    agent told only "12 claims" cannot tell this from twelve scene checks."""
    seen = {}

    async def _sweep(uid, run_id, scenes):
        seen["scenes"] = scenes
        return {
            "sweep_id": "sw1",
            "scenes_read": 3,
            "claims_raised": 9,
            "claims": [
                {"text": "a '61 Impala", "verdict": "confirmed", "scenes": [1, 2]},
                {"text": "a cassette deck", "verdict": "anachronism", "scenes": [3]},
            ],
            "search_count": 4,
        }

    result = await invoke(
        "sweep_draft",
        {"run_id": "abc", "scenes": ["INT. A\n\nOne.", "INT. B\n\nTwo.", "INT. C\n\nThree."]},
        run_sweep=_sweep,
    )
    text = said(result)

    assert "made 9 claims" in text and "2 of them were distinct" in text
    assert "1 confirmed, 1 anachronism" in text
    assert "sw1" in text and "get_sweep" in text, "and where to read it back for free"
    assert [scene["index"] for scene in seen["scenes"]] == [1, 2, 3], (
        "numbered from the array's own order, which is the order on the page"
    )
    assert seen["scenes"][0]["heading"] == "INT. A", "the slug, off the scene's first line"


@pytest.mark.asyncio
async def test_a_draft_sent_as_one_string_is_refused_with_what_to_do():
    """Nothing on this side splits a screenplay, so an agent that sent the whole
    thing has to be told to split it rather than quietly handed a one-scene
    sweep of a ninety-page draft."""
    result = await invoke("sweep_draft", {"run_id": "abc", "scenes": "INT. A\n\nOne."})

    assert result["isError"] is True
    assert "array of strings" in said(result)


@pytest.mark.asyncio
async def test_an_empty_scene_in_the_draft_is_named_rather_than_dropped():
    result = await invoke("sweep_draft", {"run_id": "abc", "scenes": ["INT. A\n\nOne.", "  "]})

    assert result["isError"] is True
    assert "empty" in said(result)


@pytest.mark.asyncio
async def test_a_sweep_that_ran_out_of_budget_says_what_is_missing():
    async def _sweep(uid, run_id, scenes):
        return {
            "sweep_id": "sw1",
            "scenes_read": 2,
            "claims_raised": 2,
            "claims": [],
            "budget_exhausted": True,
        }

    result = await invoke(
        "sweep_draft", {"run_id": "abc", "scenes": ["INT. A\n\nx", "INT. B\n\ny"]}, run_sweep=_sweep
    )

    assert "what is missing was never asked" in said(result)


# -- get_sweep ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_room_with_no_sweeps_is_an_answer_and_not_an_error():
    async def _none(uid, run_id):
        return []

    result = await invoke("get_sweep", {"run_id": "abc"}, read_sweeps=_none)

    assert result["isError"] is False
    assert "not an error" in said(result)
    assert data(result) == {"sweeps": []}


@pytest.mark.asyncio
async def test_reading_one_sweep_back_tallies_its_verdicts():
    async def _sweep(uid, run_id, sweep_id):
        return {
            "sweep_id": sweep_id,
            "scenes_read": 24,
            "claims": [
                {"text": "a", "verdict": "confirmed"},
                {"text": "b", "verdict": "anachronism"},
                {"text": "c", "verdict": "anachronism"},
            ],
        }

    result = await invoke("get_sweep", {"run_id": "abc", "sweep_id": "sw1"}, read_sweep=_sweep)

    assert "1 confirmed, 2 anachronism, 0 unverifiable" in said(result)
    assert "not a check of the line against the world" in said(result), (
        "the same sentence the browser prints over a sweep, for the same reason"
    )


# -- export_room --------------------------------------------------------------


async def _export(uid, run_id, kind, sweep_id=""):
    if kind == "bible":
        return {
            "filename": "liverpool-bible-2026-08-13.md",
            "media_type": "text/markdown; charset=utf-8",
            "text": "# Liverpool\n\n*1958-1962*\n\n## Setting\n\nA cellar.\n",
        }
    return {
        "filename": "liverpool-research-2026-08-13.csv",
        "media_type": "text/csv; charset=utf-8",
        "text": RESEARCH_CSV,
    }


@pytest.mark.asyncio
async def test_an_export_defaults_to_the_shape_of_the_file_not_the_file():
    """THE DEFAULT THAT MATTERS. A room's research export runs to hundreds of
    kilobytes, most of it quoted excerpts, and reading one into a model's
    context costs more than every other tool on this door put together."""
    result = await invoke("export_room", {"run_id": "abc"}, export_room=_export)
    payload = data(result)

    assert "SHAPE, not the file" in said(result)
    assert payload["rows"] == 1
    assert payload["columns"][0] == "drawer" and "continues" in payload["columns"]
    assert payload["first_rows"][0][1] == "Mona Best opened the Casbah."
    assert "text" not in payload, "the whole file is what `shape: file` is for"


@pytest.mark.asyncio
async def test_asking_for_the_file_gets_the_file_and_says_what_to_do_with_it():
    result = await invoke(
        "export_room", {"run_id": "abc", "shape": "file"}, export_room=_export
    )

    assert data(result)["text"] == RESEARCH_CSV
    assert "writes files rather than reading it as prose" in said(result)
    assert "import_rooms" in said(result), "and where the round trip goes"


@pytest.mark.asyncio
async def test_a_sweep_export_without_a_sweep_id_is_refused_before_anything_is_read():
    result = await invoke("export_room", {"run_id": "abc", "kind": "sweep"})

    assert result["isError"] is True
    assert "get_sweep" in said(result) and "Nothing was read" in said(result)


@pytest.mark.asyncio
async def test_a_sweep_id_sent_with_the_wrong_kind_is_refused_by_name():
    """Rather than ignored. An agent that sent both meant one of them, and
    guessing which would export something it did not ask for."""
    result = await invoke(
        "export_room", {"run_id": "abc", "kind": "research", "sweep_id": "sw1"}
    )

    assert result["isError"] is True
    assert "kind: research" in said(result)


@pytest.mark.asyncio
async def test_a_bible_summary_shows_its_opening_rather_than_csv_columns():
    result = await invoke("export_room", {"run_id": "abc", "kind": "bible"}, export_room=_export)
    payload = data(result)

    assert "columns" not in payload
    assert payload["opening"].startswith("# Liverpool")


# -- import_rooms -------------------------------------------------------------


async def _import(uid, text, apply):
    return {
        "filed": apply,
        "rooms": [
            {
                "run_id": "new-1",
                "title": "Liverpool",
                "era": "1958-1962",
                "continues": "",
                "findings": 1,
                "sources": 1,
                "drawers": ["setting"],
            }
        ],
        "complaints": [],
    }


@pytest.mark.asyncio
async def test_the_first_import_call_files_nothing_and_hands_back_a_token():
    result = await invoke("import_rooms", {"csv": RESEARCH_CSV}, import_rooms=_import)
    text = said(result)

    assert "**Nothing has been filed.**" in text
    assert data(result)["confirm"], "and a one-time token to file with"
    assert "counted from the addresses in the file, not read off it" in text


@pytest.mark.asyncio
async def test_the_token_files_the_file_it_was_minted_for_and_no_other():
    """Keyed on the file, for the reason a delete confirmation is keyed on its
    room: an agent that previewed a story and then sent a different file with
    the first file's token is one argument away from filing something nobody
    looked at."""
    first = await invoke("import_rooms", {"csv": RESEARCH_CSV}, import_rooms=_import)
    token = data(first)["confirm"]

    wrong = await invoke(
        "import_rooms",
        {"csv": RESEARCH_CSV.replace("Casbah", "Cavern"), "confirm": token},
        import_rooms=_import,
    )

    assert wrong["isError"] is True
    assert "does not carry from one file to another" in said(wrong)
    assert "Nothing was filed" in said(wrong)


@pytest.mark.asyncio
async def test_the_second_call_files_and_says_what_cannot_be_undone_about_it():
    first = await invoke("import_rooms", {"csv": RESEARCH_CSV}, import_rooms=_import)
    token = data(first)["confirm"]

    filed = await invoke(
        "import_rooms", {"csv": RESEARCH_CSV, "confirm": token}, import_rooms=_import
    )
    text = said(filed)

    assert "Filed 1 room" in text
    assert "no search was spent" in text
    assert "does not come off" in text, (
        "the provenance is the property, and an agent has to be told it is not "
        "something a later call removes"
    )
    assert "write_bible" in text, "and where the missing document comes from"


@pytest.mark.asyncio
async def test_a_confirmation_that_is_not_the_one_held_files_nothing():
    """The right file with the wrong token. Comparing the two is the whole of
    the arming: without it, ANY string sent as `confirm` files a preview, and
    the two-call shape becomes a formality an agent can skip by guessing."""
    filed = []

    async def _watch(uid, text, apply):
        filed.append(apply)
        return await _import(uid, text, apply)

    await invoke("import_rooms", {"csv": RESEARCH_CSV}, import_rooms=_watch)

    forged = await invoke(
        "import_rooms",
        {"csv": RESEARCH_CSV, "confirm": "not-the-one-that-was-minted"},
        import_rooms=_watch,
    )

    assert forged["isError"] is True
    assert filed == [False], "and the importer was never asked to file"


@pytest.mark.asyncio
async def test_a_wrong_confirmation_burns_the_one_that_was_held():
    """Single use, spent on the attempt rather than on the success. A token
    that survived a wrong guess would be a token worth guessing at."""
    first = await invoke("import_rooms", {"csv": RESEARCH_CSV}, import_rooms=_import)
    real = data(first)["confirm"]

    await invoke("import_rooms", {"csv": RESEARCH_CSV, "confirm": "wrong"}, import_rooms=_import)
    after = await invoke(
        "import_rooms", {"csv": RESEARCH_CSV, "confirm": real}, import_rooms=_import
    )

    assert after["isError"] is True, "the real token no longer files it either"
    assert "Nothing was filed" in said(after)


@pytest.mark.asyncio
async def test_a_token_cannot_be_spent_twice():
    first = await invoke("import_rooms", {"csv": RESEARCH_CSV}, import_rooms=_import)
    token = data(first)["confirm"]
    await invoke("import_rooms", {"csv": RESEARCH_CSV, "confirm": token}, import_rooms=_import)

    again = await invoke(
        "import_rooms", {"csv": RESEARCH_CSV, "confirm": token}, import_rooms=_import
    )

    assert again["isError"] is True


@pytest.mark.asyncio
async def test_a_sweep_export_sent_to_the_room_importer_is_told_where_it_belongs():
    async def _nothing(uid, text, apply):
        return {"filed": False, "rooms": [], "complaints": ["no `fact` column"]}

    result = await invoke(
        "import_rooms", {"csv": "claim,verdict\nx,confirmed\n"}, import_rooms=_nothing
    )

    assert "goes back through the sweep it came from" in said(result)


# -- write_bible and link_room ------------------------------------------------


@pytest.mark.asyncio
async def test_writing_a_bible_says_what_it_did_not_spend_and_did_not_launder():
    async def _write(uid, run_id):
        return {"run_id": run_id, "research_bible": "## Setting\n\nA cellar.\n"}

    result = await invoke("write_bible", {"run_id": "abc"}, write_bible=_write)
    text = said(result)

    assert "No search was spent" in text
    assert "still says so" in text, (
        "a document written about research does not make the research this "
        "account's, and an agent must not be able to read otherwise"
    )


@pytest.mark.asyncio
async def test_linking_says_what_the_chain_buys_and_unlinking_says_what_it_costs():
    async def _link(uid, run_id, parent):
        return {"run_id": run_id, "continues": parent}

    linked = await invoke(
        "link_room", {"run_id": "abc", "continues": "def"}, link_room=_link
    )
    cleared = await invoke("link_room", {"run_id": "abc"}, link_room=_link)

    assert "now follows def" in said(linked)
    assert "spends no new searches" in said(linked)
    assert "export_room" in said(linked), "and what else the link changes"
    assert "follows nothing and stands alone" in said(cleared)
    assert data(cleared)["continues"] == "", "omitting it is how a link is cleared"


# -- the door itself ----------------------------------------------------------


def test_every_new_tool_is_reachable_and_scoped():
    from star.oauth import validate

    added = {
        "sweep_draft",
        "get_sweep",
        "export_room",
        "import_rooms",
        "write_bible",
        "link_room",
    }

    assert added <= set(tools._RUNNERS)
    assert added <= set(tools._TOOLS_BY_NAME)
    assert added <= set(validate.SCOPE_BY_TOOL)
    assert validate.SCOPE_BY_TOOL["export_room"] == "rooms:read", "reading a file is a read"
    for spender in ("sweep_draft", "write_bible", "import_rooms", "link_room"):
        assert validate.SCOPE_BY_TOOL[spender] == "rooms:write", (
            f"{spender} changes an account, so a read token must not reach it"
        )


@pytest.mark.asyncio
async def test_an_unknown_tool_names_every_tool_that_does_exist():
    """DERIVED, both the count and the names.

    This asserted the literal "14" and carried the word `fourteen` in its own
    name, so shipping a fifteenth tool failed a test whose title was the thing
    that had gone stale. That is the `six tools` defect this repo already fixed
    once in INSTRUCTIONS, reappearing one directory over: a count written down
    beside the list it counts only ever drifts one way.
    """
    from star.mcp import tools as mcp_tools

    result = await invoke("export_the_room")
    text = said(result)

    assert result["isError"] is True
    assert str(len(mcp_tools.TOOLS)) in text, text
    for tool in mcp_tools.TOOLS:
        assert tool["name"] in text, f"{tool['name']} is served and the refusal hides it"


def test_identity_is_the_one_this_file_asserts_against():
    """A guard on the import above rather than a claim about behaviour: every
    test here passes `IDENTITY` through `invoke`, and a uid that stopped
    reaching the calls would make all of them pass against nothing."""
    assert IDENTITY.uid
