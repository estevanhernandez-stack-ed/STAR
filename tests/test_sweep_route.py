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

# The same three scenes carrying the opaque label the browser computes for
# each. Its own constant because most of this file predates the field and does
# not care about it, and the tests that DO care must not be reading a draft the
# rest of the file could quietly change out from under them.
KEYED = [{**scene, "key": f"k{scene['index']}"} for scene in SCENES]

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


def test_the_sweep_reports_confirmed_claims_holding_a_borrowed_receipt():
    """Counted off the claims actually filed, not off the pre-attach payload.

    This is a regression. The field existed on the check payload and was never
    added to the sweep's, so the first live run of a whole book reported None
    while the browser had every flag. Nothing caught it because the sweep
    assembles its own reply rather than passing the check's through.
    """
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    # The Impala is CONFIRMED against a page about cassettes: a real source,
    # genuinely searched, that says nothing about the claim it is filed under.
    verify = _FakeCheckRunner(
        produces={
            "verdicts": (
                "- confirmed | a '61 Impala | https://cassette.example/history | Checked.\n"
                "- anachronism | a cassette deck | https://cassette.example/history | 1963.\n"
            ),
            "search_count": 2,
        },
        events=[_FakeEvent(responses=[_FakeResponse([CASSETTE])])],
    )

    with sweeping(store, verify=verify):
        body = post(TestClient(server.app)).json()

    assert body["unmatched_citations"] == 1
    impala = next(c for c in body["claims"] if "Impala" in c["text"])
    assert impala["citations"][0]["shares_claim_wording"] is False
    # The anachronism cites the very same page and is never counted: a receipt
    # carrying a date routinely shares no wording with the line it contradicts.
    cassette = next(c for c in body["claims"] if "cassette" in c["text"])
    assert cassette["citations"][0]["shares_claim_wording"] is None


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


# -- what survives a reload --------------------------------------------------


def test_a_sweep_is_filed_so_a_reload_does_not_throw_it_away():
    """The whole reason this item came before the exports.

    A sweep costs a draft read and a search budget. Until it was filed, the
    answer lived only in the browser tab that ran it, and a reload discarded
    sixty-seven verdicts and the searches that bought them.
    """
    store, client = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store):
        body = post(TestClient(server.app)).json()

    sweep_id = body["sweep_id"]
    assert sweep_id, "the reply names the filing, so a caller can come back to it"
    assert f"users/{UID}/rooms/{ROOM}/sweeps/{sweep_id}" in client.data, (
        "a subcollection of the room, for the three reasons the scenes are: a "
        "room read must not pay for every sweep ever run against it, .set() on "
        "the room would clobber them, and one delete must be one delete"
    )

    filed = client.data[f"users/{UID}/rooms/{ROOM}/sweeps/{sweep_id}"]
    assert filed["claims_raised"] == body["claims_raised"]
    assert len(filed["claims"]) == len(body["claims"])
    assert filed["claims"][0]["citations"], (
        "THE CITATIONS ARE STORED WHOLE. A filed check keeps the scene text and "
        "re-derives its marks; a sweep has no single scene, so its claims ARE "
        "the record — dropping the sources would file a page of verdicts with "
        "nothing behind them"
    )
    assert filed["claims"][0]["scenes"], "and which pages each claim came from"


def test_a_filed_sweep_reads_back_as_it_returned():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    client = TestClient(server.app)

    with sweeping(store):
        # KEYED rather than SCENES so the scene-key assertion below is not two
        # empty lists agreeing with each other.
        ran = post(client, scenes=KEYED).json()
        listed = client.get(f"/api/rooms/{ROOM}/sweeps", headers=AUTH).json()["sweeps"]
        again = client.get(
            f"/api/rooms/{ROOM}/sweeps/{ran['sweep_id']}", headers=AUTH
        ).json()

    assert [s["sweep_id"] for s in listed] == [ran["sweep_id"]]
    assert listed[0]["claim_count"] == len(ran["claims"])
    assert "claims" not in listed[0], (
        "the list excludes them for the reason scene_summary excludes scene "
        "text: six filed sweeps would otherwise send four hundred claims and "
        "their citations to draw a list of six"
    )
    assert again["claims"] == ran["claims"], "every verdict, source and scene number"
    assert again["search_count"] == ran["search_count"]
    assert again["scene_keys"] == ran["scene_keys"], (
        "including which scenes it read. Carried on the single read as well as "
        "the list, because this is the faithful shape of the stored document "
        "and a field that only one of the two reads returns is a field that "
        "quietly disappears from the other"
    )


def test_a_sweep_records_which_scenes_it_read_not_only_how_many():
    """So the draft strip can say a scene was already swept.

    `scenes_read` is a count, and a count cannot mark a row of ticks. Without
    the keys, a sweep that read a whole screenplay left all 24 of its scenes
    looking untouched the moment the page reloaded — the writer's own record of
    what they had covered lasted exactly as long as the tab.
    """
    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store):
        client = TestClient(server.app)
        body = post(client, scenes=KEYED).json()
        listed = client.get(f"/api/rooms/{ROOM}/sweeps", headers=AUTH).json()["sweeps"]

    assert body["scene_keys"] == ["k1", "k2", "k3"]
    assert client_data.data[f"users/{UID}/rooms/{ROOM}/sweeps/{body['sweep_id']}"][
        "scene_keys"
    ] == ["k1", "k2", "k3"], "filed, so a reload gets them back"
    assert listed[0]["scene_keys"] == ["k1", "k2", "k3"], (
        "and carried on the LIST, which is what the strip compares a draft "
        "against — the alternative is fetching every sweep whole, four hundred "
        "claims and their excerpts, to draw a row of ticks"
    )


def test_a_scene_that_raised_no_claim_was_still_read():
    """EVERY scene sent, not only the productive ones. A scene of pure dialogue
    asserts nothing about the world and comes back with no claims; marking only
    the scenes that raised one would tell a writer their quiet scenes had been
    skipped, which is the opposite of what happened."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    quiet = [*KEYED, {"index": 4, "heading": "INT. TARDIS", "text": "Just talking.", "key": "k4"}]

    with sweeping(store):
        body = post(TestClient(server.app), scenes=quiet).json()

    assert "k4" in body["scene_keys"]
    assert not any(4 in (claim.get("scenes") or []) for claim in body["claims"]), (
        "and it genuinely raised nothing — this is the case, not a coincidence"
    )


def test_a_repeated_scene_is_one_key_and_a_long_one_is_cut():
    """The key is client-supplied text that gets stored and handed back, so it
    is bounded here the way the check route bounds its own."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    odd = [
        {"index": 1, "heading": "A", "text": "INT. A\n\nOne.", "key": "same"},
        {"index": 2, "heading": "B", "text": "INT. B\n\nTwo.", "key": "same"},
        {"index": 3, "heading": "C", "text": "INT. C\n\nThree.", "key": "x" * 200},
    ]

    with sweeping(store):
        body = post(TestClient(server.app), scenes=odd).json()

    assert body["scene_keys"] == ["same", "x" * 64]


def test_a_sweep_sent_without_keys_still_works():
    """An older browser tab, or the agent door. No keys, no ticks, nothing
    broken — the strip simply has nothing to mark, which is where it was."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with sweeping(store):
        body = post(TestClient(server.app)).json()

    assert body["scene_keys"] == []
    assert body["scenes_read"] == 3, "the sweep itself is unaffected"


def test_a_filed_sweep_can_be_deleted_and_takes_its_quotations_with_it():
    """A sweep's claims are exact quotations from across a whole draft — not
    one scene's pages but a sample of all of them."""
    store, client_data = a_store()
    store.save(UID, ROOM, filed_room())
    client = TestClient(server.app)

    with sweeping(store):
        ran = post(client).json()
        gone = client.delete(f"/api/rooms/{ROOM}/sweeps/{ran['sweep_id']}", headers=AUTH)
        twice = client.delete(f"/api/rooms/{ROOM}/sweeps/{ran['sweep_id']}", headers=AUTH)

    assert gone.status_code == 200
    assert f"users/{UID}/rooms/{ROOM}/sweeps/{ran['sweep_id']}" not in client_data.data
    assert twice.status_code == 404, (
        "and it answers honestly the second time. A delete that always reported "
        "success would tell a writer a draft's worth of their own text was gone "
        "on a sweep_id that was never theirs"
    )


def test_another_accounts_sweep_is_not_found_rather_than_refused():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    client = TestClient(server.app)

    with sweeping(store):
        ran = post(client).json()

    with mock.patch("star.server.verify_token", return_value="uid-two"),             mock.patch("star.server._store", store):
        assert client.get(f"/api/rooms/{ROOM}/sweeps", headers=AUTH).json()["sweeps"] == []
        assert client.get(
            f"/api/rooms/{ROOM}/sweeps/{ran['sweep_id']}", headers=AUTH
        ).status_code == 404
        assert client.delete(
            f"/api/rooms/{ROOM}/sweeps/{ran['sweep_id']}", headers=AUTH
        ).status_code == 404


def test_a_failure_to_file_does_not_cost_the_caller_the_answer():
    """The posture _run_check takes for the same write: the answer was decided
    before this and the caller is holding it, so a Firestore hiccup costs
    durability rather than the result they just paid for."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_sweep = mock.Mock(side_effect=RuntimeError("firestore said no"))

    with sweeping(store):
        response = post(TestClient(server.app))

    assert response.status_code == 200
    assert response.json()["claims"], "the sweep still came back"
