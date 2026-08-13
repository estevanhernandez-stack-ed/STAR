"""The sweep endpoint: what it refuses, what it reports, and what it spends.

The sweep's whole claim is that a whole draft costs ONE slot and ONE search
budget instead of one of each per scene. Everything below is about that
promise being kept, and about the refusals that keep a paste of a series
bible from turning into a request nobody bounded.

The two agents are faked at the runner seam, the same way tests/test_scenes.py
fakes the check: what a model returns is not testable here and is not tested
here. What is testable is how many times extraction ran, that it ran without a
search budget, that verification ran ONCE over the deduped set, and what the
reply says about the difference.
"""

import contextlib
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from star import config, server
from tests.test_scenes import (
    AUTH,
    CASSETTE,
    ROOM,
    UID,
    _FakeCheckRunner,
    _FakeEvent,
    _FakeResponse,
    a_store,
    filed_room,
)

# Two scenes that raise the same claim, plus one that raises another. The
# duplicate is the point: it must be extracted twice and asked about once.
SCENES = [
    {"index": 1, "heading": "INT. CASBAH — NIGHT", "text": "INT. CASBAH — NIGHT\n\nA '61 Impala."},
    {"index": 2, "heading": "EXT. STREET — DAY", "text": "EXT. STREET — DAY\n\nA '61 Impala again."},
    {"index": 3, "heading": "INT. CLUB — NIGHT", "text": "INT. CLUB — NIGHT\n\nA cassette deck."},
]

EXTRACTED = {
    1: [{"text": "a '61 Impala", "claim_type": "object"}],
    2: [{"text": "the '61 Impala", "claim_type": "object"}],
    3: [{"text": "a cassette deck", "claim_type": "technology"}],
}

VERDICTS = (
    "- confirmed | a '61 Impala | https://impala.example/1961 | Sold new that year.\n"
    "- anachronism | a cassette deck | https://cassette.example/history | "
    "The cassette arrives in 1963.\n"
)


class _FakeExtractRunner:
    """Answers with whatever the scene in state maps to, and counts its turns."""

    def __init__(self):
        self.session_service = _FakeCheckRunner().session_service
        self.seen = []

    async def run_async(self, *, user_id, session_id, new_message):
        state = self.session_service.sessions[session_id].state
        scene = state.get("scene") or ""
        self.seen.append(scene)
        index = next((i for i, s in enumerate(SCENES, 1) if s["text"] == scene), None)
        state["claims"] = {"claims": EXTRACTED.get(index, [])}
        return
        yield  # pragma: no cover - makes this an async generator


@contextlib.contextmanager
def sweeping(store, extract=None, verify=None, runs=None):
    extract = extract or _FakeExtractRunner()
    verify = verify or _FakeCheckRunner(
        produces={"verdicts": VERDICTS, "search_count": 2},
        events=[_FakeEvent(responses=[_FakeResponse([CASSETTE])])],
    )
    with (
        mock.patch("star.server.verify_token", return_value=UID),
        mock.patch("star.server._store", store),
        mock.patch("star.server.agent_sweep.extract_runner", extract),
        mock.patch("star.server.agent_sweep.verify_runner", verify),
        mock.patch.dict(server._runs, runs or {}, clear=True),
    ):
        yield extract, verify


def post(client, scenes=None, run_id=ROOM):
    return client.post(
        f"/api/rooms/{run_id}/sweep",
        json={"scenes": scenes if scenes is not None else SCENES},
        headers=AUTH,
    )


def test_a_whole_draft_is_read_scene_by_scene_and_asked_about_once():
    """The arithmetic the feature exists for, as counted calls.

    Three scenes in, three extractions, ONE verification. Scene by scene this
    would be three verifications, three search budgets and three slots of an
    hourly window that admits five.
    """
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store) as (extract, verify):
        body = post(TestClient(server.app)).json()

    assert len(extract.seen) == 3, "every scene is read"
    assert len(verify.messages) == 1, "and the whole draft is checked in one pass"
    assert body["scenes_read"] == 3
    assert body["claims_raised"] == 3, "three claims raised across the draft"
    assert len(body["claims"]) == 2, "two distinct — the Impala was asked about once"


def test_a_claim_comes_back_beside_every_scene_that_made_it():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store):
        body = post(TestClient(server.app)).json()

    impala = next(c for c in body["claims"] if "Impala" in c["text"])
    assert impala["scenes"] == [1, 2], (
        "the answer names both pages, which is the thing a scene-by-scene check "
        "cannot say however many times it is run"
    )
    assert impala["verdict"] == "confirmed"

    cassette = next(c for c in body["claims"] if "cassette" in c["text"])
    assert cassette["scenes"] == [3]
    assert cassette["verdict"] == "anachronism"


def test_extraction_is_seeded_with_no_search_budget():
    """The claim desk holds no tools, and the state it runs on says so.

    Seeding a budget here would imply to the next reader that extraction can
    spend, which is the assumption the whole cost argument rests on being
    false.
    """
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store) as (extract, _):
        post(TestClient(server.app))

    for state in extract.session_service.seeded:
        assert "search_budget" not in state
        assert "scene" in state


def test_verification_runs_under_the_sweeps_own_ceiling():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store) as (_, verify):
        post(TestClient(server.app))

    seeded = verify.session_service.seeded[0]
    assert seeded["search_budget"] == config.max_searches_per_sweep()
    assert seeded["search_budget"] != config.max_searches_per_check(), (
        "a draft is not a scene, and one budget for the draft is the feature"
    )


def test_a_draft_that_asserts_nothing_is_a_result_and_costs_nothing():
    """A stretch of pure dialogue asserts little about the world. Saying so is
    not the same as failing to read it, and it must not reach the verifier."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    class _Empty(_FakeExtractRunner):
        async def run_async(self, *, user_id, session_id, new_message):
            self.session_service.sessions[session_id].state["claims"] = {"claims": []}
            self.seen.append("")
            return
            yield  # pragma: no cover

    with sweeping(store, extract=_Empty()) as (_, verify):
        body = post(TestClient(server.app)).json()

    assert body["claims"] == []
    assert body["claims_raised"] == 0
    assert body["search_count"] == 0
    assert len(verify.messages) == 0, "nothing to ask about, so nothing was asked"


def test_one_scene_the_extractor_chokes_on_does_not_cost_the_others():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    class _Flaky(_FakeExtractRunner):
        # An async GENERATOR, like the runner it stands in for. Written as a
        # plain coroutine, `async for` in the server rejects it and every scene
        # fails — which passed as "one bad scene" while actually proving the
        # opposite.
        async def run_async(self, *, user_id, session_id, new_message):
            state = self.session_service.sessions[session_id].state
            scene = state.get("scene") or ""
            self.seen.append(scene)
            if "CASBAH" in scene:
                raise RuntimeError("model said no")
            index = next((i for i, s in enumerate(SCENES, 1) if s["text"] == scene), None)
            state["claims"] = {"claims": EXTRACTED.get(index, [])}
            return
            yield  # pragma: no cover

    with sweeping(store, extract=_Flaky()):
        body = post(TestClient(server.app)).json()

    assert body["scenes_read"] == 3
    assert [c["text"] for c in body["claims"]] == ["the '61 Impala", "a cassette deck"], (
        "scene 1 came back empty and scenes 2 and 3 were still read — one bad "
        "scene in a feature must not cost the writer the rest of it"
    )
    impala = body["claims"][0]
    assert impala["scenes"] == [2], (
        "and the scene map does not claim a page that never reported it. Scene "
        "1 raised the same Impala and was lost, so saying [1, 2] here would "
        "send a writer to a page this sweep never actually read"
    )


def test_a_series_bible_is_refused_rather_than_sat_on():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    too_many = [{"index": i, "heading": "INT. X", "text": "INT. X\n\nA thing."} for i in range(200)]

    with sweeping(store) as (extract, _):
        response = post(TestClient(server.app), scenes=too_many)

    assert response.status_code == 400
    assert str(config.max_scenes_per_sweep()) in response.json()["detail"]
    assert extract.seen == [], "refused before a single scene was read"


def test_an_empty_draft_is_refused():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store):
        response = post(TestClient(server.app), scenes=[{"index": 1, "text": "   "}])

    assert response.status_code == 400
    assert "scenes in it" in response.json()["detail"]


def test_a_sweep_into_a_room_still_being_built_is_refused():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    live = {ROOM: {"uid": UID, "status": "running"}}

    with sweeping(store, runs=live) as (extract, _):
        response = post(TestClient(server.app))

    assert response.status_code == 409
    assert extract.seen == [], "nothing read, so nothing spent"


def test_a_sweep_of_another_accounts_room_is_simply_not_found():
    store, _ = a_store()

    with sweeping(store):
        response = post(TestClient(server.app), run_id="someone-elses")

    assert response.status_code == 404


@pytest.mark.parametrize("field", ["claims_raised", "scenes_read"])
def test_the_reply_carries_both_numbers(field):
    """The difference between them is what a reader cannot work out alone, and
    it is the whole reason a sweep costs less than the same scenes one by one."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store):
        body = post(TestClient(server.app)).json()

    assert field in body
