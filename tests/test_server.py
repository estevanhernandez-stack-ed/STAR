import asyncio
import json
import logging
import os
import re
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
            return {"json": {"treatment": "x" * 60}}
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
    assert {"create_room", "list_rooms", "get_room", "stream_events"} <= checked_names


# --- Test-shape gap: /config.js must serve only the public keys ------------


def test_config_js_exposes_only_the_public_firebase_keys_and_no_secrets():
    client = TestClient(server.app)
    secret_google = "sk-google-should-never-leave-the-server"
    secret_parallel = "sk-parallel-should-never-leave-the-server"

    with mock.patch.dict(
        os.environ,
        {
            "FIREBASE_API_KEY": "public-web-key",
            "FIREBASE_PROJECT_ID": "star-project",
            "GOOGLE_API_KEY": secret_google,
            "PARALLEL_API_KEY": secret_parallel,
        },
    ):
        response = client.get("/config.js")

    assert response.status_code == 200
    body = response.text
    assert response.headers["content-type"].startswith("application/javascript")

    _, _, rest = body.partition("export const FIREBASE = ")
    payload = json.loads(rest.rstrip(";\n"))
    assert set(payload) == {"apiKey", "projectId"}
    assert payload["apiKey"] == "public-web-key"
    assert payload["projectId"] == "star-project"

    assert secret_google not in body
    assert secret_parallel not in body


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
