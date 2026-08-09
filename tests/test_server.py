import asyncio
from unittest import mock

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from star import server
from star.ledger import SourceLedger
from star.models import Category

AUTH = {"Authorization": "Bearer good.token.here"}

STAX = {
    "title": "Stax Museum — History",
    "url": "https://staxmuseum.example/history",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}


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

    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake_store),
    ):
        response = client.get("/api/rooms", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["rooms"][0]["run_id"] == "abc"
    fake_store.list_rooms.assert_called_once_with("uid-one")


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
