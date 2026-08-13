import asyncio
import json
import logging
import os
import re
from unittest import mock

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from star import config, server
from star.ledger import SourceLedger
from star.models import Category, Citation, Finding

AUTH = {"Authorization": "Bearer good.token.here"}

STAX = {
    "title": "Stax Museum — History",
    "url": "https://staxmuseum.example/history",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}


class _FakeRequest:
    """Stand-in for FastAPI's `Request` when calling `create_room` directly
    instead of through `TestClient` — direct calls bypass ASGI, so nothing
    builds a real `Request` for us. Only what `_caller_key` reads."""

    def __init__(self, host="127.0.0.1", headers=None):
        self.client = mock.Mock(host=host)
        self.headers = headers or {}


def test_category_map_covers_every_researcher_author():
    for category in Category:
        assert server._CATEGORY_BY_AUTHOR[f"researcher_{category.value}"] == category


def test_category_map_returns_none_for_non_researchers():
    assert server._CATEGORY_BY_AUTHOR.get("synthesis") is None


def test_build_categories_parses_every_category_from_state():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX])
    state = {"findings_setting": f"- Stax used a converted theater :: {STAX['url']}"}

    categories = server._build_categories(state, ledger)

    assert set(categories) == {c.value for c in Category}
    assert len(categories["setting"].findings) == 1
    assert categories["setting"].findings[0].citations[0].title == "Stax Museum — History"
    assert categories["setting"].parse_rate == 1.0
    assert categories["logistics"].findings == []


def test_categories_serialize_to_the_api_shape():
    """The seam the endpoint test cannot reach: real ResearchDoc -> JSON."""
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX])
    state = {"findings_setting": f"- Stax used a converted theater :: {STAX['url']}"}

    payload = jsonable_encoder(server._build_categories(state, ledger))

    setting = payload["setting"]
    assert setting["category"] == "setting"
    assert setting["parse_rate"] == 1.0
    assert setting["unverified_count"] == 0
    assert setting["findings"][0]["fact"] == "Stax used a converted theater"
    assert setting["findings"][0]["citations"][0]["title"] == "Stax Museum — History"
    assert setting["findings"][0]["citations"][0]["excerpt"]
    assert setting["findings"][0]["unverified_urls"] == []
    assert payload["logistics"]["findings"] == []


def test_a_researcher_that_never_wrote_is_distinguishable_from_one_that_filed_nothing():
    """The room view depends on this and cannot recover it any other way.

    `_build_categories` emits all four keys unconditionally, so a run salvaged
    mid-flight (`_salvage`) sends categories for researchers that never
    produced a word. `markdown` is the only field that separates the two: empty
    means the agent never reached its output_key, non-empty with no findings
    means it wrote prose the parser could not file. web/app.js's categoryFiled
    reads exactly this to decide whether a drawer mounts FILED or FAILED, and
    to count how many researchers filed in the partial room's copy — so a
    change that gave `markdown` a non-empty default would silently stamp FILED
    over a researcher that never filed, and put a false number on the page
    next to it.
    """
    ledger = SourceLedger()
    state = {
        # Wrote, but nothing the parser could turn into a finding.
        "findings_setting": "No usable sources came back for this category.",
        # Never reached its output_key at all.
    }

    payload = jsonable_encoder(server._build_categories(state, ledger))

    assert payload["setting"]["findings"] == []
    assert payload["setting"]["markdown"].strip() != ""

    assert payload["logistics"]["findings"] == []
    assert payload["logistics"]["markdown"] == ""


def test_room_endpoint_exposes_categories():
    client = TestClient(server.app)
    server._runs["testrun"] = {
        "events": [],
        "status": "complete",
        "search_count": 3,
        "ledger": SourceLedger(),
        "result": {
            "story_profile": {"title": "1962 Memphis"},
            "research_plan": None,
            "research_bible": "# Bible",
            "search_count": 3,
            "categories": {
                "setting": {
                    "category": "setting",
                    "markdown": "raw",
                    "findings": [],
                    "field_notes": "",
                    "parse_rate": 0.0,
                    "unverified_count": 0,
                }
            },
        },
        "uid": "test-uid",
    }

    with mock.patch("star.server.verify_token", return_value="test-uid"):
        response = client.get("/api/rooms/testrun", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert "categories" in body["result"]
    assert body["result"]["categories"]["setting"]["parse_rate"] == 0.0

    del server._runs["testrun"]


def test_a_live_run_reports_created_at_the_same_way_a_stored_room_does():
    """The two branches of get_room serve the same room minutes apart — this
    one right after a build, the Firestore one from the rail tomorrow. The
    browser stamps `created_at` on every receipt as the day the sources came
    back, so a field present on one path and absent on the other would make a
    provenance claim appear or vanish depending on who answered."""
    client = TestClient(server.app)
    server._runs["timed"] = {
        "events": [],
        "status": "complete",
        "search_count": 3,
        "ledger": SourceLedger(),
        "result": {"story_profile": {"title": "1962 Memphis"}, "categories": {}},
        "uid": "test-uid",
        "created_at": "2026-08-09T12:00:00+00:00",
    }

    with mock.patch("star.server.verify_token", return_value="test-uid"):
        response = client.get("/api/rooms/timed", headers=AUTH)

    assert response.json()["result"]["created_at"] == "2026-08-09T12:00:00+00:00"

    del server._runs["timed"]


def test_a_run_with_no_result_yet_still_answers_without_a_created_at_merge():
    """`result` is None until the pipeline populates it. The merge must not
    manufacture a payload out of a room that has nothing in it."""
    client = TestClient(server.app)
    server._runs["early"] = {
        "events": [],
        "status": "running",
        "search_count": 0,
        "ledger": SourceLedger(),
        "result": None,
        "uid": "test-uid",
        "created_at": "2026-08-09T12:00:00+00:00",
    }

    with mock.patch("star.server.verify_token", return_value="test-uid"):
        response = client.get("/api/rooms/early", headers=AUTH)

    assert response.json()["result"] is None

    del server._runs["early"]


def test_persisting_twice_keeps_the_first_created_at():
    """Every build writes its document twice — once at creation, once at its
    terminal status — and `.set()` replaces the whole document. A fresh
    timestamp on the second write moved created_at to the moment the run
    finished, which for a build spanning midnight put the wrong date on real
    sources."""
    run = {
        "status": "complete",
        "events": [],
        "result": {"research_bible": "x"},
        "uid": "uid-one",
        "created_at": "2026-08-09T23:58:00+00:00",
    }
    fake_store = mock.Mock()

    with mock.patch("star.server._store", fake_store):
        server._persist(run, "midnight", "running")
        server._persist(run, "midnight", "complete")

    first, second = [call.args[2] for call in fake_store.save.call_args_list]
    assert first["created_at"] == "2026-08-09T23:58:00+00:00"
    assert second["created_at"] == "2026-08-09T23:58:00+00:00"
    assert second["status"] == "complete"


def test_unknown_room_still_404s():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        assert client.get("/api/rooms/does-not-exist", headers=AUTH).status_code == 404


# -- Finding 6: a fifth ADK envelope must fail loud, not silently -----------


def test_maybe_warn_empty_ledger_pushes_a_warning_when_searches_ran_dry():
    """Simulates a hypothetical fifth envelope shape unwrap_results can't
    recognize: searches happened but nothing landed in the ledger."""
    run = {"events": [], "search_count": 3, "ledger": SourceLedger()}

    server._maybe_warn_empty_ledger(run)

    assert len(run["events"]) == 1
    assert run["events"][0]["type"] == "warning"


def test_maybe_warn_empty_ledger_stays_quiet_when_the_ledger_has_sources():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX])
    run = {"events": [], "search_count": 3, "ledger": ledger}

    server._maybe_warn_empty_ledger(run)

    assert run["events"] == []


def test_maybe_warn_empty_ledger_stays_quiet_when_no_searches_ran():
    run = {"events": [], "search_count": 0, "ledger": SourceLedger()}

    server._maybe_warn_empty_ledger(run)

    assert run["events"] == []


# -- Task 3: auth and persistence --------------------------------------------


def test_api_rejects_a_request_with_no_token():
    client = TestClient(server.app)
    assert client.get("/api/rooms").status_code == 401


def test_api_rejects_a_forged_token():
    client = TestClient(server.app)
    with mock.patch("star.server.verify_token", return_value=None):
        assert client.get("/api/rooms", headers=AUTH).status_code == 401


def test_list_rooms_returns_only_the_callers_rooms():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.list_rooms.return_value = [{"run_id": "abc", "title": "1962 Memphis"}]
    # A Mock returns a Mock, which is not serialisable — and the rail now asks
    # for the deleted list in the same answer, so the double has to model it.
    fake_store.list_deleted_rooms.return_value = []

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["rooms"][0]["run_id"] == "abc"
    assert body["deleted"] == [], "the rail is told about deleted rooms too"
    fake_store.list_rooms.assert_called_once_with("uid-one")
    fake_store.list_deleted_rooms.assert_called_once_with("uid-one")


def test_get_room_falls_back_to_firestore_when_not_in_memory():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "persisted",
        "status": "complete",
        "story_profile": {"title": "1962 Memphis"},
        "research_bible": "# Bible",
        "search_count": 14,
        "categories": {},
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms/persisted", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["result"]["story_profile"]["title"] == "1962 Memphis"
    fake_store.get.assert_called_once_with("uid-one", "persisted")


def test_get_room_404s_when_neither_memory_nor_firestore_has_it():
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        assert client.get("/api/rooms/nope", headers=AUTH).status_code == 404


def test_an_in_memory_run_is_not_readable_by_a_different_uid():
    """Memory must be scoped by uid too, not just Firestore."""
    client = TestClient(server.app)
    server._runs["owned"] = {
        "events": [], "status": "complete", "search_count": 1,
        "ledger": SourceLedger(), "result": {"research_bible": "x"}, "uid": "uid-one",
    }
    fake_store = mock.Mock()
    fake_store.get.return_value = None

    with (
        mock.patch("star.server.verify_token", return_value="uid-two"),
        mock.patch("star.server._store", fake_store),
    ):
        assert client.get("/api/rooms/owned", headers=AUTH).status_code == 404

    del server._runs["owned"]


def test_get_room_404s_when_the_document_vanishes_between_read_and_mark_interrupted():
    """Task 1's creation-time write made this race genuinely reachable: the
    document existed for _store.get(), but is gone by the time
    mark_interrupted's update() runs. get_room must treat that False as
    "this room is gone" and 404, not report a status it never actually set."""
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "vanished", "status": "running", "story_profile": {},
        "research_bible": "", "search_count": 0, "categories": {},
    }
    fake_store.mark_interrupted.return_value = False

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms/vanished", headers=AUTH)

    assert response.status_code == 404


def test_a_run_stored_as_running_but_absent_from_memory_becomes_interrupted():
    """The asyncio task did not survive a restart; the UI must stop spinning."""
    client = TestClient(server.app)
    fake_store = mock.Mock()
    fake_store.get.return_value = {
        "run_id": "stuck", "status": "running", "story_profile": {},
        "research_bible": "", "search_count": 0, "categories": {},
    }

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms/stuck", headers=AUTH)

    assert response.json()["status"] == "interrupted"
    fake_store.mark_interrupted.assert_called_once_with("uid-one", "stuck")


# -- Task 3 review round 1: persistence must never rewrite the outcome ------


def test_a_persistence_failure_does_not_relabel_a_successful_run():
    """The pipeline succeeded. Losing durability must not become an error."""
    run = {
        "status": "complete",
        "events": [],
        "result": {"research_bible": "x"},
        "uid": "uid-one",
    }
    fake_store = mock.Mock()
    fake_store.save.side_effect = RuntimeError("Firestore unavailable")

    with mock.patch("star.server._store", fake_store):
        server._persist(run, "some-run-id", "complete")  # must not raise

    assert run["status"] == "complete"
    assert run["events"] == []
    fake_store.save.assert_called_once()


def test_post_rooms_rejects_a_request_with_no_token():
    client = TestClient(server.app)
    response = client.post("/api/rooms", json={"treatment": "x" * 60})
    assert response.status_code == 401


# --- run bounding (added 2026-08-09 after a nine-minute runaway build) ---


@pytest.mark.asyncio
async def test_a_run_that_overruns_its_ceiling_ends_as_a_visible_error():
    """The failure this exists to prevent: a build that never finishes and
    never says so, leaving the UI spinning and the connection held open."""
    server._runs["slow"] = {
        "events": [], "status": "running", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
    }

    async def _never_finishes(run_id, treatment):
        await asyncio.sleep(5)

    with (
        mock.patch("star.server._run_pipeline", _never_finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=1),
        mock.patch("star.server._store", mock.Mock()),
    ):
        await server._execute("slow", "a treatment")

    run = server._runs["slow"]
    assert run["status"] == "error"
    errors = [e for e in run["events"] if e["type"] == "error"]
    assert len(errors) == 1
    assert "limit" in errors[0]["message"]
    assert "try again" in errors[0]["message"].lower()

    del server._runs["slow"]


@pytest.mark.asyncio
async def test_a_run_inside_its_ceiling_completes_normally():
    server._runs["quick"] = {
        "events": [], "status": "running", "search_count": 3,
        "ledger": SourceLedger(), "result": {"research_bible": "# Bible"}, "uid": "uid-one",
    }

    async def _finishes(run_id, treatment):
        return None

    with (
        mock.patch("star.server._run_pipeline", _finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=60),
        mock.patch("star.server._store", mock.Mock()),
    ):
        await server._execute("quick", "a treatment")

    run = server._runs["quick"]
    assert run["status"] == "complete"
    assert [e["type"] for e in run["events"]] == ["complete"]

    del server._runs["quick"]


# --- partial results: an overrun must not discard filed research ---


def _seed_run(run_id, uid="uid-one", session_id="sess-1"):
    server._runs[run_id] = {
        "events": [], "status": "running", "search_count": 12,
        "ledger": SourceLedger(), "result": None, "uid": uid,
        "session_id": session_id,
    }
    return server._runs[run_id]


class _FakeSession:
    def __init__(self, state):
        self.state = state


@pytest.mark.asyncio
async def test_an_overrun_keeps_the_research_the_researchers_already_filed():
    """A build costs a dozen live searches and several minutes. Losing all of
    it because the editor was mid-sentence is the wrong trade."""
    run = _seed_run("overran")
    run["ledger"].record("researcher_setting", [STAX])
    state = {
        "story_profile": {"title": "1962 Memphis"},
        "findings_setting": f"- Stax used a converted theater :: {STAX['url']}",
    }

    async def _never_finishes(run_id, treatment):
        await asyncio.sleep(5)

    async def _get_session(**kwargs):
        return _FakeSession(state)

    with (
        mock.patch("star.server._run_pipeline", _never_finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=1),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch.object(server._runner.session_service, "get_session", _get_session),
    ):
        await server._execute("overran", "a treatment")

    assert run["status"] == "partial"
    assert run["result"]["categories"]["setting"]["findings"][0]["fact"]
    assert run["result"]["research_bible"] == ""
    events = [e for e in run["events"] if e["type"] == "partial"]
    assert len(events) == 1
    assert "findings" in events[0]["message"]
    assert not [e for e in run["events"] if e["type"] == "error"]

    del server._runs["overran"]


@pytest.mark.asyncio
async def test_an_overrun_with_nothing_filed_is_still_an_error():
    """Salvage is not an excuse to call an empty run a success."""
    run = _seed_run("empty")

    async def _never_finishes(run_id, treatment):
        await asyncio.sleep(5)

    async def _get_session(**kwargs):
        return _FakeSession({})

    with (
        mock.patch("star.server._run_pipeline", _never_finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=1),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch.object(server._runner.session_service, "get_session", _get_session),
    ):
        await server._execute("empty", "a treatment")

    assert run["status"] == "error"
    assert not [e for e in run["events"] if e["type"] == "partial"]

    del server._runs["empty"]


def test_the_defence_endpoint_and_the_agent_door_answer_from_one_function():
    """The property that makes the printed sheet trustworthy.

    A writer prints this card and an agent returns it, and both are read by
    someone who is already sceptical. Two implementations of "which finding did
    they mean" would eventually disagree, and the disagreement would surface in
    front of that person. Both call star/defence.py, and this is the assertion
    that says so in a way a refactor cannot quietly undo.
    """
    from star import defence
    from star.mcp import tools

    assert tools.defence is defence, "the agent door's card comes from here"
    assert server.defence is defence, "and so does the browser's"


def test_the_defence_card_refuses_a_fact_the_room_did_not_file():
    room = {
        "run_id": "abc",
        "status": "complete",
        "story_profile": {"title": "BROWNOUT"},
        "created_at": "2026-08-09T12:00:00Z",
        "categories": {
            "setting": {"findings": [{"fact": "The heat broke.", "citations": []}]}
        },
    }
    store = mock.Mock()
    store.get.return_value = room

    async def _ask(fact):
        with mock.patch("star.server._store", store):
            return await server.get_defence("abc", fact=fact, authorization=None)

    with mock.patch("star.server._require_uid", return_value="uid-one"):
        found = asyncio.run(_ask("The heat broke."))
        assert found["fact"] == "The heat broke."

        with pytest.raises(HTTPException) as raised:
            asyncio.run(_ask("The heat broke on the fourteenth."))

    assert raised.value.status_code == 404
    assert "nearest match" in raised.value.detail, (
        "and it says why it will not guess — a card built around a near match "
        "puts real sources behind a claim the room never made"
    )


def test_a_requisition_appends_to_a_drawer_without_disturbing_the_rest():
    """The append is pure, so it can be asserted without a model or a network.

    The drawer it targets may not exist. A build files all four, but a room
    recovered by `_salvage` keeps only what survived — and a thin room is
    exactly the one a writer asks a question about, so the missing-drawer case
    is the normal path here rather than the edge.
    """
    document = {
        "search_count": 17,
        "categories": {
            "setting": {"findings": [{"fact": "A gate.", "citations": [{"url": "u"}]}]}
        },
    }
    filed = [Finding(fact="A curfew.", citations=[Citation(url="v", title="T", excerpt="e")])]

    out = server._file_findings(document, Category.LOGISTICS, filed, 2)

    assert [f["fact"] for f in out["categories"]["logistics"]["findings"]] == ["A curfew."]
    assert out["categories"]["setting"]["findings"][0]["fact"] == "A gate.", (
        "the drawer that was already there is untouched"
    )
    assert out["search_count"] == 19, "the room's cost grows by what this spent"
    assert out["source_count"] == 1, (
        "one url the room was not already citing. Not a recount of citations "
        "across the drawers, which is a different quantity from the stored "
        "one — `_persist` files the size of the build's LEDGER, and a recount "
        "moved a real room from 99 sources to 74 the first time this ran live"
    )
    assert document["search_count"] == 17, "and the input document is not mutated"


def test_a_requisition_does_not_count_a_source_the_room_already_had():
    """The half a recount gets wrong in the other direction.

    Two findings citing one url are one source, and a requisition that lands
    on a page the room already cited has not found the room a new one. Without
    this the number inflates every time a researcher returns to a good site,
    which on a well-researched subject is most of the time.
    """
    document = {
        "source_count": 40,
        "categories": {
            "setting": {
                "findings": [
                    {"fact": "A gate.", "citations": [{"url": "https://a.example"}]}
                ]
            }
        },
    }
    filed = [
        Finding(
            fact="A curfew.",
            citations=[
                Citation(url="https://a.example", title="A", excerpt="e"),
                Citation(url="https://b.example", title="B", excerpt="e"),
            ],
        )
    ]

    out = server._file_findings(document, Category.LOGISTICS, filed, 1)

    assert out["source_count"] == 41, (
        "b.example is new and a.example was already cited — one source, not two"
    )


def test_a_requisition_never_lowers_the_count_of_sources_behind_a_room():
    """The property the live run broke, stated as the property.

    A room that says it stands on fewer sources after research was added to it
    is telling a writer their room got thinner by growing. Whatever the delta
    is computed from, it cannot be negative.
    """
    document = {
        # Higher than any walk of the drawers can see, which is the real shape:
        # `_persist` files the size of the build's ledger, and a ledger holds
        # every url a search returned including ones no finding ended up citing.
        "source_count": 99,
        "categories": {
            "setting": {
                "findings": [
                    {"fact": "A gate.", "citations": [{"url": "https://a.example"}]}
                ]
            }
        },
    }

    out = server._file_findings(
        document,
        Category.LOGISTICS,
        [Finding(fact="A curfew.", citations=[Citation(url="https://a.example", title="A", excerpt="e")])],
        1,
    )

    assert out["source_count"] >= 99, "adding research cannot shrink the room"
    assert out["source_count"] == 99, "and nothing new was cited, so it does not grow"


def test_a_requisition_into_an_existing_drawer_keeps_what_was_there():
    document = {
        "categories": {"logistics": {"findings": [{"fact": "First.", "citations": []}]}}
    }
    filed = [Finding(fact="Second.", citations=[])]

    out = server._file_findings(document, Category.LOGISTICS, filed, 1)

    assert [f["fact"] for f in out["categories"]["logistics"]["findings"]] == [
        "First.",
        "Second.",
    ], "appended, and after — a room reads in the order it was researched"


@pytest.mark.asyncio
async def test_a_requisition_is_refused_into_a_room_still_being_built():
    """Not tidiness: `_persist` calls `.set()`, which replaces the document.

    A finding filed in the seconds before a build's terminal write would be
    overwritten by a room assembled from session state that never knew about
    it — and the writer would have been told their question was researched and
    filed. The refusal is the only thing standing between them and a fact that
    silently is not there.
    """
    server._runs["live"] = {"uid": "uid-one", "status": "running"}
    store = mock.Mock()
    store.get.return_value = {"run_id": "live", "status": "running"}

    try:
        with (
            mock.patch("star.server._store", store),
            pytest.raises(HTTPException) as raised,
        ):
            await server._run_requisition(
                "uid-one", "live", "how were the gates guarded", Category.SETTING
            )
    finally:
        del server._runs["live"]

    assert raised.value.status_code == 409
    assert "still being built" in raised.value.detail
    assert "overwritten" in raised.value.detail, "and why waiting is not politeness"


@pytest.mark.asyncio
async def test_a_requisition_into_another_accounts_room_is_simply_not_found():
    """Isolation by construction, not by a check anyone has to remember.

    `_store.get` is rooted at `users/{uid}`, so another caller's room is not
    found and refused — it is not found, which is the answer a room that never
    existed gets, down to the string.
    """
    store = mock.Mock()
    store.get.return_value = None

    with (
        mock.patch("star.server._store", store),
        pytest.raises(HTTPException) as raised,
    ):
        await server._run_requisition(
            "uid-two", "someone-elses", "how were the gates guarded", Category.SETTING
        )

    assert raised.value.status_code == 404
    assert raised.value.detail == "Unknown run"


@pytest.mark.asyncio
async def test_a_failed_run_files_its_own_account_of_why_it_stopped():
    """The explanation has to outlive the stream that carried it.

    A run that fails already says why, in plain language, down the SSE
    connection. That connection dies with the run, so what a writer found the
    next morning — and what every `get_room` call has ever returned — was
    `status: "error"` and nothing else: a room that had failed and would not
    say what happened. A timeout and a crash read identically, though only one
    of them means a shorter treatment would work.

    The sentence stored is the SAME OBJECT pushed to the stream, not a second
    copy written for the database. Two versions of one explanation is how the
    stored one drifts, and the stored one is the copy nobody is watching.
    """
    run = _seed_run("accounted")

    async def _never_finishes(run_id, treatment):
        await asyncio.sleep(5)

    async def _get_session(**kwargs):
        return _FakeSession({})

    store = mock.Mock()
    with (
        mock.patch("star.server._run_pipeline", _never_finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=1),
        mock.patch("star.server._store", store),
        mock.patch.object(server._runner.session_service, "get_session", _get_session),
    ):
        await server._execute("accounted", "a treatment")

    assert run["status"] == "error"

    stored = store.save.call_args.args[2]
    assert stored["status"] == "error"
    note = stored["note"]
    assert note, "a room that failed has to be able to say why it failed"
    assert "minute limit" in note, (
        "and specifically why THIS one did — the timeout branch names the "
        "ceiling it ran past, which is the half a crash cannot claim"
    )

    pushed = [e for e in run["events"] if e["type"] == "error"]
    assert pushed, "the stream still gets its message"
    assert pushed[0]["message"] == note, (
        "one sentence, pushed and stored. Written twice they drift, and the "
        "copy that drifts is the one no reader was watching being written"
    )

    del server._runs["accounted"]


@pytest.mark.asyncio
async def test_salvage_gives_up_quietly_when_the_session_cannot_be_read():
    run = _seed_run("unreadable")

    async def _boom(**kwargs):
        raise RuntimeError("session service unavailable")

    with mock.patch.object(server._runner.session_service, "get_session", _boom):
        assert await server._salvage(run, "unreadable") is False

    del server._runs["unreadable"]


# --- Finding 1: _salvage must never raise, only its get_session call was
# guarded; the parsing work after it (_build_categories, jsonable_encoder)
# ran unguarded, and an exception there used to escape `except TimeoutError`
# uncaught (a sibling `except Exception` cannot catch it), leaving the run
# stuck at status "running" forever with no terminal SSE event. ---


@pytest.mark.asyncio
async def test_salvage_returns_false_rather_than_raising_when_its_internals_blow_up():
    run = _seed_run("salvage-internals-blow-up")

    async def _get_session(**kwargs):
        return _FakeSession({})

    with (
        mock.patch.object(server._runner.session_service, "get_session", _get_session),
        mock.patch("star.server._build_categories", side_effect=RuntimeError("boom")),
    ):
        assert await server._salvage(run, "salvage-internals-blow-up") is False

    del server._runs["salvage-internals-blow-up"]


@pytest.mark.asyncio
async def test_a_run_whose_salvage_blows_up_still_ends_as_a_visible_error_not_stuck_running():
    """The exact silent hang the timeout was added to prevent, reintroduced
    through the recovery path. Without the Finding 1 fix, the RuntimeError
    below escapes `except TimeoutError`, run["status"] never leaves
    "running", and nothing is ever pushed to the client."""
    run = _seed_run("salvage-blows-up-end-to-end")

    async def _never_finishes(run_id, treatment):
        await asyncio.sleep(5)

    async def _get_session(**kwargs):
        return _FakeSession({})

    with (
        mock.patch("star.server._run_pipeline", _never_finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=1),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch.object(server._runner.session_service, "get_session", _get_session),
        mock.patch("star.server._build_categories", side_effect=RuntimeError("boom")),
    ):
        await server._execute("salvage-blows-up-end-to-end", "a treatment")

    assert run["status"] != "running"
    assert run["status"] == "error"
    assert any(e["type"] == "error" for e in run["events"])

    del server._runs["salvage-blows-up-end-to-end"]


# --- Minor: a mid-pipeline failure (e.g. a Gemini 5xx during synthesis) must
# salvage filed research too, not just a timeout. ---


@pytest.mark.asyncio
async def test_a_synthesis_failure_also_salvages_filed_research():
    run = _seed_run("synth-fails")
    run["ledger"].record("researcher_setting", [STAX])
    state = {
        "story_profile": {"title": "1962 Memphis"},
        "findings_setting": f"- Stax used a converted theater :: {STAX['url']}",
    }

    async def _boom(run_id, treatment):
        raise RuntimeError("Gemini 503")

    async def _get_session(**kwargs):
        return _FakeSession(state)

    with (
        mock.patch("star.server._run_pipeline", _boom),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch.object(server._runner.session_service, "get_session", _get_session),
    ):
        await server._execute("synth-fails", "a treatment")

    assert run["status"] == "partial"
    assert run["result"]["categories"]["setting"]["findings"][0]["fact"]
    events = [e for e in run["events"] if e["type"] == "partial"]
    assert len(events) == 1
    # The client message must not name the exception class. That is thinner
    # than leaking a full message, but it is still our vocabulary in a
    # stranger's browser on a public endpoint. The type belongs in the log.
    assert "RuntimeError" not in events[0]["message"]
    assert "Gemini" not in events[0]["message"]
    assert "findings" in events[0]["message"]
    assert not [e for e in run["events"] if e["type"] == "error"]

    del server._runs["synth-fails"]


# --- Finding 6: nothing was ever persisted with status "running", so a
# Cloud Run recycle mid-build 404s the room out of existence instead of
# reporting it interrupted. create_room must write a recoverable placeholder
# before the background task starts. ---


@pytest.mark.asyncio
async def test_create_room_persists_a_running_placeholder_before_the_task_starts():
    fake_store = mock.Mock()

    async def _noop(run_id, treatment):
        return None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
        mock.patch("star.server._execute", _noop),
    ):
        response = await server.create_room(
            server.RoomRequest(treatment="x" * 60),
            request=_FakeRequest(),
            authorization=AUTH["Authorization"],
        )
    run_id = response["run_id"]

    fake_store.save.assert_called_once()
    saved_uid, saved_run_id, saved_doc = fake_store.save.call_args[0]
    assert saved_uid == "uid-one"
    assert saved_run_id == run_id
    assert saved_doc["status"] == "running"
    # room_to_document expects a result dict; at creation there is none yet.
    # The "no story_profile" case is already covered in test_store.py and
    # yields this exact title.
    assert saved_doc["title"] == "Untitled room"

    del server._runs[run_id]


@pytest.mark.asyncio
async def test_a_run_that_recycles_mid_build_recovers_as_interrupted_end_to_end():
    """Closes the loop the existing hand-written-fake interrupted test left
    open: before Finding 6, create_room wrote nothing to Firestore, so this
    recovery path was reachable only via a document nothing in production
    ever produced. Now the placeholder create_room writes is exactly what
    get_room needs to recover after a simulated instance recycle (the
    in-memory run disappears, the Firestore document survives)."""
    written = {}
    fake_store = mock.Mock()
    fake_store.save.side_effect = lambda uid, run_id, doc: written.__setitem__((uid, run_id), doc)
    fake_store.get.side_effect = lambda uid, run_id: written.get((uid, run_id))

    async def _noop(run_id, treatment):
        return None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
        mock.patch("star.server._execute", _noop),
    ):
        response = await server.create_room(
            server.RoomRequest(treatment="x" * 60),
            request=_FakeRequest(),
            authorization=AUTH["Authorization"],
        )
        run_id = response["run_id"]

        # Simulate the recycle: the in-memory run is gone, but the placeholder
        # document create_room wrote survives in Firestore.
        del server._runs[run_id]

        with mock.patch("star.server.verify_token", return_value="uid-one"):
            result = await server.get_room(run_id, authorization=AUTH["Authorization"])

    assert result["status"] == "interrupted"
    fake_store.mark_interrupted.assert_called_once_with("uid-one", run_id)


# --- Test-shape gap: route enumeration instead of hand-named routes --------


def test_every_api_route_requires_auth_except_the_explicitly_open_sse_stream():
    """Every existing auth test names its route by hand, so a route added
    later under /api/ that forgets _require_uid would pass the whole suite
    silently. Walk the actual registered routes instead. The SSE stream is
    the one deliberate exception — EventSource can't set a bearer header —
    and is allow-listed here by route *name*, not by path, so the exemption
    stays visible rather than being an unexplained gap in the loop."""
    client = TestClient(server.app)
    OPEN_ROUTE_NAMES = {"stream_events"}

    def body_for(method: str) -> dict:
        if method == "POST":
            # One body that satisfies every POST route's schema at once.
            # Pydantic ignores the keys a given model does not declare, and
            # the alternative — a per-route body table — puts a hand-named
            # route back in the middle of a test whose whole point is that it
            # names none. A POST route whose body this does not satisfy fails
            # validation with a 422 before _require_uid ever runs, so it would
            # read here as "did not require auth" and the fix would be a new
            # key in this dict, not an exemption.
            # `category` carries a real drawer name rather than filler: the
            # question route validates it against the Category enum, and a
            # bogus value 422s before _require_uid runs, which this test would
            # read as a route that does not require auth.
            return {
                "json": {
                    "treatment": "x" * 60,
                    "scene": "x" * 60,
                    "question": "x" * 20,
                    "category": "setting",
                }
            }
        return {}

    checked = []
    for route in server.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path.startswith("/api/") or not methods:
            continue
        stub_path = re.sub(r"\{[^}]+\}", "route-audit-stub", path)
        for method in methods - {"HEAD", "OPTIONS"}:
            checked.append((route.name, method))
            response = client.request(method, stub_path, **body_for(method))
            if route.name in OPEN_ROUTE_NAMES:
                assert response.status_code != 401, (
                    f"{method} {stub_path} ({route.name}) is allow-listed open "
                    f"but returned 401"
                )
            else:
                assert response.status_code == 401, (
                    f"{method} {stub_path} ({route.name}) did not require auth "
                    f"(got {response.status_code}) — missing _require_uid?"
                )

    # Guards against the walk silently matching nothing (e.g. a path-prefix typo).
    checked_names = {name for name, _ in checked}
    assert {
        "create_room",
        "list_rooms",
        "get_room",
        "stream_events",
        "create_scene",
        "list_scenes",
        "get_scene",
        "delete_scene",
        "create_token",
        "list_tokens",
        "revoke_token",
    } <= checked_names


# --- Test-shape gap: /config.js must serve only the public keys ------------


def test_api_schema_routes_are_disabled_on_a_public_endpoint():
    """/docs, /redoc, and /openapi.json expose no secrets, but they hand an
    attacker a map of every route and shape. Not worth it on a public,
    unauthenticated surface."""
    client = TestClient(server.app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def _exported_config(body: str) -> dict:
    """Parse `/config.js` back into `{export name: payload}`.

    The endpoint serves ES module source rather than JSON, so the test has to
    read it as source. Splitting on the export statements rather than
    partitioning once is what lets the assertions below check the exact SET of
    exports: a second export used to land inside the first one's parse and
    break it, which is a failure that says "the test is stale" when the thing
    worth hearing is "something new is on this wire".
    """
    exported = {}
    for statement in body.split("export const ")[1:]:
        name, _, payload = statement.partition(" = ")
        exported[name.strip()] = json.loads(payload.strip().rstrip(";"))
    return exported


def test_config_js_exposes_only_the_public_firebase_keys_and_no_secrets():
    client = TestClient(server.app)
    secret_google = "sk-google-should-never-leave-the-server"
    secret_parallel = "sk-parallel-should-never-leave-the-server"

    with mock.patch.dict(
        os.environ,
        {
            "FIREBASE_API_KEY": "public-web-key",
            "FIREBASE_PROJECT_ID": "star-project",
            "GOOGLE_OAUTH_CLIENT_ID": "public-oauth-client-id",
            "GOOGLE_API_KEY": secret_google,
            "PARALLEL_API_KEY": secret_parallel,
        },
    ):
        response = client.get("/config.js")

    assert response.status_code == 200
    body = response.text
    assert response.headers["content-type"].startswith("application/javascript")

    exported = _exported_config(body)
    # Exact key sets, not a subset check. This file is the one place server
    # environment crosses into the browser, and the test that guards it has to
    # fail on an ADDED key rather than only on a changed one — a leak arrives
    # as something new in the payload, never as something missing from it.
    assert set(exported) == {"FIREBASE", "GOOGLE", "LIMITS"}
    assert set(exported["FIREBASE"]) == {"apiKey", "projectId"}
    assert exported["FIREBASE"]["apiKey"] == "public-web-key"
    assert exported["FIREBASE"]["projectId"] == "star-project"
    assert set(exported["GOOGLE"]) == {"clientId"}
    assert exported["GOOGLE"]["clientId"] == "public-oauth-client-id"

    # LIMITS carries caps the browser has to agree with, and nothing else. It
    # is here rather than typed into JS because a cap duplicated across two
    # languages is two sources of truth and only one of them ever moves — the
    # defect web/consent.js shipped when it advertised "four calls" on the day
    # a fifth tool landed. Each entry is a number: a limit is a number, and a
    # string in this block would be a value from the environment wearing a
    # limit's name.
    assert set(exported["LIMITS"]) == {"roomTitleChars"}
    assert exported["LIMITS"]["roomTitleChars"] == config.max_room_title_chars()
    assert all(isinstance(value, int) for value in exported["LIMITS"].values())

    # GOOGLE_OAUTH_CLIENT_ID is public and GOOGLE_API_KEY is the Gemini
    # credential, and as of this cycle they share a prefix. Anything that ever
    # reaches for the environment by pattern rather than by name puts the
    # second one on this wire, so both secrets are asserted absent from the
    # whole body rather than only from the payload that was parsed.
    assert secret_google not in body
    assert secret_parallel not in body


def test_config_js_serves_an_empty_client_id_rather_than_failing_to_boot():
    """An absent OAuth client id is loud, not fatal.

    `config.validate_env()` deliberately does not list it. That function fails
    the process on anything whose absence would be silent; this one's absence
    reaches the browser as `""`, `linkingAvailable()` reads false, and the card
    says linking is unavailable while every other path keeps working. Deleting
    the variable is the whole test, and the assertion is that the response is
    still a 200 carrying a well-formed empty string.
    """
    client = TestClient(server.app)

    with mock.patch.dict(os.environ, {"FIREBASE_API_KEY": "k"}):
        os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
        response = client.get("/config.js")

    assert response.status_code == 200
    assert _exported_config(response.text)["GOOGLE"] == {"clientId": ""}


# --- Task 1: abuse guards on a publicly reachable endpoint ------------------


def test_a_caller_past_the_hourly_limit_is_refused():
    client = TestClient(server.app)
    treatment = {"treatment": "x" * 60}

    async def _noop(run_id, treatment):
        return None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._execute", _noop),
        mock.patch("star.server._ip_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)),
        mock.patch("star.server._daily_cap", server.DailyCap(max_per_day=1000)),
    ):
        first = client.post("/api/rooms", json=treatment, headers=AUTH)
        second = client.post("/api/rooms", json=treatment, headers=AUTH)

    assert first.status_code == 200
    assert second.status_code == 429

    for run_id in (first.json()["run_id"],):
        server._runs.pop(run_id, None)


def test_the_daily_cap_refuses_everyone_once_it_trips():
    client = TestClient(server.app)
    treatment = {"treatment": "x" * 60}

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._ip_limiter", server.RateLimiter(max_per_window=99, window_seconds=3600)),
        mock.patch("star.server._daily_cap", server.DailyCap(max_per_day=0)),
    ):
        response = client.post("/api/rooms", json=treatment, headers=AUTH)

    assert response.status_code == 429


# --- Finding 2: the per-IP key must not be attacker-controlled -------------
#
# X-Forwarded-For is a left-to-right chain and proxies APPEND to it, they do
# not replace it. GCP's load balancer appends the connection's real address
# as the last hop, so the rightmost entry is the one to trust; the leftmost
# entry is whatever the client itself sent and is not even validated as an
# IP. Demonstrated: 50 requests with a rotating leftmost header value were
# all allowed against a 5/hour limit under the old (leftmost) key.


def test_caller_key_takes_the_rightmost_forwarded_for_entry():
    request = _FakeRequest(
        headers={"x-forwarded-for": "totally-not-an-ip, 203.0.113.5"}
    )
    assert server._caller_key(request) == "203.0.113.5"


def test_caller_key_ignores_a_spoofed_leftmost_entry_when_the_real_one_trails():
    request = _FakeRequest(headers={"x-forwarded-for": "attacker-controlled"})
    # No trusted proxy hop present at all — still take the last (only) entry
    # rather than trusting it blindly as "the client"; this documents intent
    # more than it changes behavior for a single-entry header.
    assert server._caller_key(request) == "attacker-controlled"


def test_caller_key_falls_back_to_request_client_host_without_the_header():
    request = _FakeRequest(host="127.0.0.1")
    assert server._caller_key(request) == "127.0.0.1"


def test_rotating_the_leftmost_forwarded_for_entry_does_not_evade_the_ip_limiter():
    """The exact demonstrated failure: an attacker who rotates a spoofed
    leftmost X-Forwarded-For value while the real, trusted-proxy-appended
    entry stays fixed must still be rate-limited as one caller."""
    client = TestClient(server.app)
    treatment = {"treatment": "x" * 60}

    async def _noop(run_id, treatment):
        return None

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._execute", _noop),
        mock.patch(
            "star.server._ip_limiter",
            server.RateLimiter(max_per_window=1, window_seconds=3600),
        ),
        mock.patch("star.server._daily_cap", server.DailyCap(max_per_day=1000)),
    ):
        responses = []
        for i in range(5):
            headers = {**AUTH, "X-Forwarded-For": f"spoofed-{i}, 203.0.113.5"}
            responses.append(client.post("/api/rooms", json=treatment, headers=headers))

    assert responses[0].status_code == 200
    assert [r.status_code for r in responses[1:]] == [429, 429, 429, 429]

    server._runs.pop(responses[0].json()["run_id"], None)


# --- Finding 3: a request the IP limiter refuses must not spend a daily
# slot. Verified failure: 10 POSTs from one IP against a per-IP limit of 1
# produced one build and consumed all 10 daily slots, because the daily cap
# was checked — and DailyCap.check() increments on the allow path — before
# the per-IP check. ---


def test_a_request_refused_by_the_ip_limiter_does_not_consume_a_daily_slot():
    client = TestClient(server.app)
    treatment = {"treatment": "x" * 60}

    async def _noop(run_id, treatment):
        return None

    daily_cap = server.DailyCap(max_per_day=100)
    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._execute", _noop),
        mock.patch(
            "star.server._ip_limiter",
            server.RateLimiter(max_per_window=1, window_seconds=3600),
        ),
        mock.patch("star.server._daily_cap", daily_cap),
    ):
        responses = [
            client.post("/api/rooms", json=treatment, headers=AUTH) for _ in range(10)
        ]

    assert responses[0].status_code == 200
    assert [r.status_code for r in responses[1:]] == [429] * 9
    assert daily_cap.count_for() == 1, (
        "a request the IP limiter refused still spent a daily slot"
    )

    server._runs.pop(responses[0].json()["run_id"], None)


@pytest.mark.asyncio
async def test_a_pipeline_failure_does_not_leak_exception_detail_to_the_client(caplog):
    """The message a stranger sees must not describe our internals — but the
    real detail must still reach the server log, or losing it there would be
    just as bad as leaking it to the client."""
    server._runs["leaky"] = {
        "events": [], "status": "running", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "session_id": None,
    }

    async def _explode(run_id, treatment):
        raise RuntimeError(
            "psycopg2.OperationalError: password authentication failed for user 'star'"
        )

    with (
        mock.patch("star.server._run_pipeline", _explode),
        mock.patch("star.server._store", mock.Mock()),
        caplog.at_level(logging.ERROR, logger="star.server"),
    ):
        await server._execute("leaky", "a treatment")

    run = server._runs["leaky"]
    errors = [e for e in run["events"] if e["type"] == "error"]
    assert len(errors) == 1
    message = errors[0]["message"]

    assert "psycopg2" not in message
    assert "password" not in message
    assert "RuntimeError" not in message
    assert "unexpected problem" in message

    logged = "\n".join(record.getMessage() for record in caplog.records) + caplog.text
    assert "psycopg2" in logged
    assert "password" in logged

    del server._runs["leaky"]


# --- Task 2: SSE reconnect must not replay the whole history ---------------


# Every one of these runs is reached through the stream's per-run
# capability (star/server.py's stream_events). These tests are about the
# Last-Event-ID cursor, so the key is fixture plumbing here; the tests that
# actually pin the capability live at the end of this file.
_SSE_KEY = "sse-fixture-key"
_SSE_PARAMS = {"k": _SSE_KEY}


def _sse_ids(response) -> list[int]:
    """Parse `id: N` lines out of a raw SSE response body, in event order."""
    ids = []
    for block in response.text.strip("\n").split("\n\n"):
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("id: "):
                ids.append(int(line.removeprefix("id: ")))
    return ids


def test_push_assigns_each_event_a_monotonic_id():
    run = {"events": [], "status": "running", "search_count": 0}
    server._push(run, "started")
    server._push(run, "search", agent="x", objective="q", category=None)
    server._push(run, "agent_done", agent="x")

    assert [e["id"] for e in run["events"]] == [0, 1, 2]


def test_stream_events_replays_everything_with_no_last_event_id():
    client = TestClient(server.app)
    run = server._runs["sse-fresh"] = {
        "events": [], "status": "complete", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "stream_key": _SSE_KEY,
    }
    for i in range(5):
        server._push(run, "search", agent="x", objective=f"q{i}", category=None)

    response = client.get("/api/rooms/sse-fresh/events", params=_SSE_PARAMS)

    assert _sse_ids(response) == [0, 1, 2, 3, 4]

    del server._runs["sse-fresh"]


def test_stream_events_honours_last_event_id_and_skips_replayed_events():
    """EventSource sends Last-Event-ID automatically on reconnect. Without a
    cursor computed from it, every reconnect re-sends the run's entire
    history and web/app.js double-counts every search."""
    client = TestClient(server.app)
    run = server._runs["sse-reconnect"] = {
        "events": [], "status": "complete", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "stream_key": _SSE_KEY,
    }
    for i in range(5):
        server._push(run, "search", agent="x", objective=f"q{i}", category=None)

    response = client.get(
        "/api/rooms/sse-reconnect/events",
        headers={"Last-Event-ID": "1"},
        params=_SSE_PARAMS,
    )

    # Event 1 was already delivered before the (simulated) reconnect; only
    # 2, 3, 4 are new.
    assert _sse_ids(response) == [2, 3, 4]

    del server._runs["sse-reconnect"]


def test_stream_events_treats_a_malformed_last_event_id_as_no_cursor():
    client = TestClient(server.app)
    run = server._runs["sse-malformed"] = {
        "events": [], "status": "complete", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "stream_key": _SSE_KEY,
    }
    for i in range(3):
        server._push(run, "search", agent="x", objective=f"q{i}", category=None)

    response = client.get(
        "/api/rooms/sse-malformed/events",
        headers={"Last-Event-ID": "not-a-number"},
        params=_SSE_PARAMS,
    )

    assert _sse_ids(response) == [0, 1, 2]

    del server._runs["sse-malformed"]


# --- Minor: Last-Event-ID parsing was too loose. `int()` alone accepts
# underscore-grouped digits ("1_000") and places no upper bound on the
# result, so a large value silently starves the client of every event until
# the run ends (the replay loop only fires once cursor < len(events)). Gate
# on str.isdigit() and clamp to the run's current event count. ---


def test_resume_cursor_defaults_to_zero_with_no_header():
    assert server._resume_cursor(None, total_events=5) == 0


def test_resume_cursor_resumes_one_past_the_last_seen_event():
    assert server._resume_cursor("1", total_events=5) == 2


def test_resume_cursor_rejects_non_numeric_strings():
    assert server._resume_cursor("not-a-number", total_events=5) == 0


def test_resume_cursor_rejects_underscore_grouped_digits():
    """int("1_000") == 1000, but _push never emits an id with an underscore
    in it — str.isdigit() correctly refuses what int() alone would accept."""
    assert server._resume_cursor("1_000", total_events=5) == 0


def test_resume_cursor_clamps_to_the_current_event_count():
    """Verified failure: an unbounded cursor set past the run's actual event
    count used to silently starve the client of every event until the run
    ended. Clamping resumes at the current tip instead of going dark."""
    assert server._resume_cursor("999999", total_events=3) == 3


def test_stream_events_treats_an_underscore_grouped_last_event_id_as_malformed():
    client = TestClient(server.app)
    run = server._runs["sse-underscore"] = {
        "events": [], "status": "complete", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "stream_key": _SSE_KEY,
    }
    for i in range(3):
        server._push(run, "search", agent="x", objective=f"q{i}", category=None)

    response = client.get(
        "/api/rooms/sse-underscore/events",
        headers={"Last-Event-ID": "1_000"},
        params=_SSE_PARAMS,
    )

    assert _sse_ids(response) == [0, 1, 2]

    del server._runs["sse-underscore"]


def test_stream_events_with_an_out_of_range_last_event_id_does_not_error():
    """Wiring check: a huge Last-Event-ID against a terminal run must not
    raise or hang the stream — it clamps to the tip and yields nothing new,
    which is correct once nothing new exists."""
    client = TestClient(server.app)
    run = server._runs["sse-out-of-range"] = {
        "events": [], "status": "complete", "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
        "stream_key": _SSE_KEY,
    }
    for i in range(3):
        server._push(run, "search", agent="x", objective=f"q{i}", category=None)

    response = client.get(
        "/api/rooms/sse-out-of-range/events",
        headers={"Last-Event-ID": "999999"},
        params=_SSE_PARAMS,
    )

    assert response.status_code == 200
    assert _sse_ids(response) == []

    del server._runs["sse-out-of-range"]


# --- Task 2: unbounded _runs must evict finished runs, never a live one ----


def _bare_run(status: str) -> dict:
    return {
        "events": [], "status": status, "search_count": 0,
        "ledger": SourceLedger(), "result": None, "uid": "uid-one",
    }


def test_evict_old_runs_drops_the_oldest_terminal_entries_beyond_the_bound():
    fake_runs = {
        "oldest": _bare_run("complete"),
        "middle": _bare_run("error"),
        "newest": _bare_run("partial"),
    }

    with (
        mock.patch.object(server, "_runs", fake_runs),
        mock.patch("star.server.config.max_runs_in_memory", return_value=2),
    ):
        server._evict_old_runs()
        remaining = set(server._runs)

    assert remaining == {"middle", "newest"}


def test_evict_old_runs_never_evicts_a_running_entry_regardless_of_age():
    """A running entry is the oldest thing in the dict here — eviction must
    still skip it, or a live build gets orphaned and its SSE stream breaks."""
    fake_runs = {
        "running-oldest": _bare_run("running"),
        "t1": _bare_run("complete"),
        "t2": _bare_run("complete"),
        "t3": _bare_run("complete"),
    }

    with (
        mock.patch.object(server, "_runs", fake_runs),
        mock.patch("star.server.config.max_runs_in_memory", return_value=1),
    ):
        server._evict_old_runs()
        remaining = set(server._runs)

    assert remaining == {"running-oldest"}


def test_evict_old_runs_never_evicts_the_excluded_run_even_if_it_is_oldest():
    """_execute pushes this run's own terminal event and then evicts in the
    same synchronous call, with no `await` in between — so this run can be
    the oldest terminal entry in `_runs` at the exact moment it finishes (a
    slow build often is). Without excluding it, eviction could drop it
    before its own SSE stream's next poll ever sees the terminal event."""
    fake_runs = {
        "just-finished": _bare_run("complete"),
        "t2": _bare_run("complete"),
        "t3": _bare_run("complete"),
    }

    with (
        mock.patch.object(server, "_runs", fake_runs),
        mock.patch("star.server.config.max_runs_in_memory", return_value=1),
    ):
        server._evict_old_runs(exclude="just-finished")
        remaining = set(server._runs)

    assert "just-finished" in remaining


def test_evict_old_runs_is_a_noop_under_the_bound():
    fake_runs = {"a": _bare_run("complete"), "b": _bare_run("running")}

    with (
        mock.patch.object(server, "_runs", fake_runs),
        mock.patch("star.server.config.max_runs_in_memory", return_value=20),
    ):
        server._evict_old_runs()
        remaining = set(server._runs)

    assert remaining == {"a", "b"}


@pytest.mark.asyncio
async def test_execute_evicts_old_runs_once_it_reaches_a_terminal_status():
    server._runs["evict-trigger"] = _bare_run("running")

    async def _finishes(run_id, treatment):
        return None

    with (
        mock.patch("star.server._run_pipeline", _finishes),
        mock.patch("star.server.config.run_timeout_seconds", return_value=60),
        mock.patch("star.server._store", mock.Mock()),
        mock.patch("star.server._evict_old_runs") as fake_evict,
    ):
        await server._execute("evict-trigger", "a treatment")

    fake_evict.assert_called_once_with(exclude="evict-trigger")

    del server._runs["evict-trigger"]


def test_agent_done_carries_the_category_so_the_ui_need_not_parse_prose():
    """Without this, the browser reverse-maps _FRIENDLY's English wording
    back to a category, which makes that wording a load-bearing API
    contract — rewording a label would silently stop a drawer filing."""
    run = {"events": []}

    for category in Category:
        server._push(run, "agent_done", agent="ignored", category=category.value)

    assert [e["category"] for e in run["events"]] == [c.value for c in Category]


def test_agent_done_from_a_non_researcher_has_a_null_category():
    """intake, planner and synthesis file no drawer."""
    run = {"events": []}

    server._push(run, "agent_done", agent="Editor", category=None)

    assert run["events"][0]["category"] is None


# --- The SSE stream's per-run capability -----------------------------------
#
# GET /api/rooms/{run_id}/events is the one /api route that cannot read the
# Authorization header, because EventSource does not send custom headers. It
# therefore checked nothing at all until a per-run key was added, and anyone
# holding a run_id could read another caller's live research. These tests pin
# the capability, not the plumbing: that a caller who starts a run is given
# the key, that the key is required, that a wrong key is indistinguishable
# from a nonexistent run, and that the key never leaves this process by any
# other route.


def _stream_run(**overrides) -> dict:
    run = {
        "events": [{"id": 0, "type": "started"}],
        "status": "complete",  # terminal, so the generator drains and stops
        "result": {"research_bible": "# Bible"},
        "search_count": 0,
        "uid": "uid-one",
        "stream_key": "k" * 32,
        "created_at": "2026-08-10T00:00:00+00:00",
    }
    run.update(overrides)
    return run


def test_the_event_stream_requires_the_runs_key():
    client = TestClient(server.app)
    with mock.patch.dict(server._runs, {"run-1": _stream_run()}, clear=True):
        assert client.get("/api/rooms/run-1/events").status_code == 404


def test_the_event_stream_accepts_the_runs_key():
    client = TestClient(server.app)
    with mock.patch.dict(server._runs, {"run-1": _stream_run()}, clear=True):
        response = client.get("/api/rooms/run-1/events", params={"k": "k" * 32})

    assert response.status_code == 200
    assert "started" in response.text


def test_a_wrong_key_is_indistinguishable_from_an_unknown_run():
    """A 403 here would confirm that a guessed run_id exists, turning the
    check into an oracle for the thing it protects. Both answers must be the
    same answer."""
    client = TestClient(server.app)
    with mock.patch.dict(server._runs, {"run-1": _stream_run()}, clear=True):
        wrong = client.get("/api/rooms/run-1/events", params={"k": "x" * 32})
        absent = client.get("/api/rooms/nope/events", params={"k": "x" * 32})

    assert wrong.status_code == absent.status_code == 404
    assert wrong.json() == absent.json()


def test_another_callers_key_does_not_open_this_stream():
    """The realistic attack: someone who has legitimately started their own
    run, and so holds a valid key, pointing it at a run_id that is not
    theirs."""
    client = TestClient(server.app)
    runs = {
        "mine": _stream_run(stream_key="a" * 32),
        "theirs": _stream_run(stream_key="b" * 32, uid="uid-two"),
    }
    with mock.patch.dict(server._runs, runs, clear=True):
        assert client.get(
            "/api/rooms/theirs/events", params={"k": "a" * 32}
        ).status_code == 404


def test_the_stream_key_is_returned_to_the_caller_that_starts_the_run():
    client = TestClient(server.app)
    treatment = "A period drama set in 1962 Memphis, with a session guitarist."

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._persist"),
        mock.patch("star.server._execute", new=mock.AsyncMock()),
        mock.patch.dict(server._runs, {}, clear=True),
    ):
        response = client.post("/api/rooms", json={"treatment": treatment}, headers=AUTH)
        body = response.json()
        run = server._runs[body["run_id"]]

    assert response.status_code == 200
    assert body["stream_key"] == run["stream_key"]
    # Long enough to be a secret rather than an identifier. run_id is a
    # truncated uuid because it is a name; this is not.
    assert len(body["stream_key"]) == 32


def test_the_stream_key_is_never_persisted_or_returned_by_get_room():
    """It lives and dies in this process, with the run it guards. If a future
    change serialises the run dict wholesale, this is the field that has to be
    stripped first — so both exits are pinned here."""
    fake_store = mock.Mock()
    client = TestClient(server.app)
    run = _stream_run()

    with mock.patch("star.server._store", fake_store):
        server._persist(run, "run-1", "complete")
    saved_document = fake_store.save.call_args[0][2]

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch.dict(server._runs, {"run-1": run}, clear=True),
    ):
        body = client.get("/api/rooms/run-1", headers=AUTH).json()

    assert "stream_key" not in saved_document
    assert "stream_key" not in json.dumps(body)
