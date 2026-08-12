"""The scene endpoints, the check runner, and what a filed check keeps.

Everything here runs with no network and no spend. The pipeline is faked at
the ADK runner seam — `_check_runner` is swapped out whole — because what a
model returns is not testable this way and is not tested here. What is
testable is everything around it: which rooms a check may read, what reaches
the model and in which position, which of two ledgers hydrated a citation,
which facts the server computes for itself rather than believing, and what is
left in Firestore afterwards.

The store is the same hand-written Firestore fake `tests/test_store.py`
drives, imported rather than copied, so a path assertion here is against the
same shape that file already pins against real Firestore behaviour.
"""

import asyncio
import contextlib
import json
import logging
import threading
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from star import config, server
from star.agents.pipelines import check_scene
from star.store import (
    RoomStore,
    document_to_scene,
    room_to_document,
    scene_summary,
    scene_to_document,
)
from tests.test_store import _FakeClient

AUTH = {"Authorization": "Bearer good.token.here"}
UID = "uid-one"
OTHER_UID = "uid-two"
ROOM = "room-1"
FILED = "2026-08-10T00:00:00+00:00"

SCENE = (
    "INT. STAX STUDIO - NIGHT\n\n"
    "BOBBY parks a '61 Impala out front and punches it into the cassette deck.\n"
)

# The room's own filed source, in the citation shape star/store.py stores and
# star/ledger.py's ledger_from_room walks.
IMPALA = {
    "url": "https://impala.example/1961",
    "title": "1961 Chevrolet Impala",
    "excerpt": "The third generation ran from 1961 through 1964.",
}
# What a fresh parallel_search returns mid-check, in the shape
# star/ledger.py's unwrap_results takes.
CASSETTE = {
    "url": "https://cassette.example/history",
    "title": "The Compact Cassette at Sixty",
    "excerpts": ["Philips showed the Compact Cassette in 1963."],
}

CLAIMS = {
    "claims": [
        {"text": "a '61 Impala", "claim_type": "object"},
        {"text": "punches it into the cassette deck", "claim_type": "technology"},
    ]
}
VERDICTS = (
    f"- confirmed | a '61 Impala | {IMPALA['url']} | Sold new that year.\n"
    f"- anachronism | punches it into the cassette deck | {CASSETTE['url']} | "
    "The cassette arrives in 1963, two years after the scene.\n"
)


# -- the room the check reads ------------------------------------------------


def filed_room(status="complete"):
    """A finished build with one cited finding in one drawer."""
    return room_to_document(
        ROOM,
        {
            "story_profile": {"title": "1962 Memphis", "era": "1960-1962"},
            "research_bible": "# Bible",
            "search_count": 14,
            "source_count": 1,
            "categories": {
                "setting": {
                    "category": "setting",
                    "markdown": "raw",
                    "findings": [
                        {
                            "fact": "Impalas of that generation ran 1961 to 1964",
                            "citations": [IMPALA],
                            "unverified_urls": [],
                        }
                    ],
                    "field_notes": "",
                    "parse_rate": 1.0,
                    "unverified_count": 0,
                }
            },
        },
        status,
        FILED,
    )


def barren_room(status="partial"):
    """A build that filed nothing: no drawers, no citations, no ledger."""
    return room_to_document(ROOM, {"search_count": 0}, status, FILED)


def a_store():
    client = _FakeClient()
    return RoomStore(client=client), client


# -- the ADK seam ------------------------------------------------------------


class _FakeSession:
    def __init__(self, session_id, state):
        self.id = session_id
        self.state = state


class _FakeSessionService:
    def __init__(self):
        self.sessions = {}
        self.seeded = []
        self.deleted = []

    async def create_session(self, *, app_name, user_id, state=None, session_id=None):
        new_id = session_id or f"check-{len(self.seeded)}"
        session = _FakeSession(new_id, dict(state or {}))
        self.sessions[session.id] = session
        self.seeded.append(session.state)
        return session

    async def get_session(self, *, app_name, user_id, session_id):
        return self.sessions.get(session_id)

    async def delete_session(self, *, app_name, user_id, session_id):
        self.deleted.append(session_id)
        self.sessions.pop(session_id, None)


class _FakeResponse:
    def __init__(self, payload):
        self.response = payload


class _FakeEvent:
    def __init__(self, author="verifier", responses=()):
        self.author = author
        self._responses = list(responses)

    def get_function_responses(self):
        return self._responses


class _FakeCheckRunner:
    """Stands in for the ADK runner Pipeline B runs on.

    `produces` is what the two agents would have left in session state by the
    end of the run — the extractor's `claims`, the verifier's `verdicts`, and
    the `search_count` parallel_search counts into state as it spends.
    `events` carry what the tool returned, in the envelope star/ledger.py
    unwraps, because the server records the ledger off the event stream rather
    than off anything the model wrote.
    """

    def __init__(self, produces=None, events=(), raises=None, hangs=False):
        self.session_service = _FakeSessionService()
        self.produces = produces or {}
        self.events = list(events)
        self.raises = raises
        self.hangs = hangs
        self.messages = []

    async def run_async(self, *, user_id, session_id, new_message):
        self.messages.append(new_message)
        if self.hangs:
            await asyncio.sleep(30)
        if self.raises is not None:
            raise self.raises
        self.session_service.sessions[session_id].state.update(self.produces)
        for event in self.events:
            yield event


def _produces(searches=1):
    """What the two agents leave in session state by the end of a run."""
    return {"claims": CLAIMS, "verdicts": VERDICTS, "search_count": searches}


def a_runner(**overrides):
    kwargs = {
        "produces": _produces(),
        "events": [_FakeEvent(responses=[_FakeResponse([CASSETTE])])],
    }
    kwargs.update(overrides)
    return _FakeCheckRunner(**kwargs)


class _ThreadRecordingStore:
    """Wraps a real RoomStore and remembers which thread each call ran on."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = []
        self.threads = []

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def recorded(*args, **kwargs):
            self.calls.append(name)
            self.threads.append(threading.get_ident())
            return attribute(*args, **kwargs)

        return recorded


@contextlib.contextmanager
def checking(store, runner=None, runs=None):
    """Patch the four things a check touches, and nothing else."""
    runner = a_runner() if runner is None else runner
    with (
        mock.patch("star.server.verify_token", return_value=UID),
        mock.patch("star.server._store", store),
        mock.patch("star.server._check_runner", runner),
        mock.patch.dict(server._runs, runs or {}, clear=True),
    ):
        yield runner


def post(client, scene=SCENE, run_id=ROOM):
    return client.post(
        f"/api/rooms/{run_id}/scenes", json={"scene": scene}, headers=AUTH
    )


# -- a check requires a room -------------------------------------------------


def test_a_check_against_a_room_that_does_not_exist_is_not_found():
    store, _ = a_store()

    with checking(store):
        response = post(TestClient(server.app))

    assert response.status_code == 404


def test_another_uids_room_answers_exactly_as_a_room_that_never_existed():
    """Not merely both 404. The read goes through `_store.get(uid, run_id)`,
    whose path is rooted at `users/{uid}`, so another caller's room is never
    found and refused — it is not found, which has to be the same answer down
    to the string or the refusal itself tells them the room is real."""
    store, _ = a_store()
    store.save("uid-two", ROOM, filed_room())

    with checking(store):
        client = TestClient(server.app)
        theirs = post(client)
        absent = post(client, run_id="never-existed")

    assert theirs.status_code == absent.status_code == 404
    assert theirs.json() == absent.json()


def test_a_room_still_being_built_is_refused_rather_than_checked_against_nothing():
    """It has filed nothing yet, so the check would spend up to eight live
    searches to produce a check leaning on an empty room."""
    store, _ = a_store()
    store.save(UID, ROOM, room_to_document(ROOM, None, "running", FILED))
    live = {ROOM: {"status": "running", "uid": UID}}

    with checking(store, runs=live) as runner:
        response = post(TestClient(server.app))

    assert response.status_code == 409
    assert "still being built" in response.json()["detail"]
    assert runner.messages == [], "a refused check still started the pipeline"


def test_an_interrupted_room_is_checkable_where_a_live_build_is_not():
    """Both rooms are stored as "running"; only one has a task behind it. A
    build that did not survive a restart is what get_room reports as
    interrupted, and a check against it is a supported case — refusing on the
    stored status alone would refuse it forever."""
    store, _ = a_store()
    store.save(UID, ROOM, barren_room("running"))

    with checking(store):
        response = post(TestClient(server.app))

    assert response.status_code == 200


def test_a_partial_room_with_no_findings_still_supports_a_check_on_fresh_search():
    store, _ = a_store()
    store.save(UID, ROOM, barren_room("partial"))

    with checking(store):
        response = post(TestClient(server.app))

    assert response.status_code == 200
    # The Impala claim cited a URL only the room could have held, and the room
    # held nothing — so it comes back unsourced and downgraded. The cassette
    # claim cited what this check's own search returned, and stands. That
    # split is the whole of "on fresh search alone".
    assert [claim["verdict"] for claim in response.json()["claims"]] == [
        "unverifiable",
        "anachronism",
    ]


def test_the_result_says_when_the_rooms_own_files_were_empty():
    """The room contributed nothing, and the check has to say so rather than
    letting a reader read an all-search result as an all-room one."""
    store, _ = a_store()
    store.save(UID, ROOM, barren_room("partial"))

    with checking(store) as runner:
        body = post(TestClient(server.app)).json()

    assert runner.session_service.seeded[0]["room_files"] == ""
    assert body["cover_note"] == (
        "This room filed no sources of its own, so the check had nothing to "
        "work from but a fresh search."
    )


def test_a_filed_room_carries_no_cover_note_because_the_claims_speak():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()

    assert body["cover_note"] == ""


# -- the two ledgers, per claim ----------------------------------------------


def test_a_scene_checked_against_a_room_cites_that_rooms_ledger():
    """The room answered, and the server knows that because the URL resolved
    against the ledger rebuilt from the room's own document — not because the
    verifier said so."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()

    impala = body["claims"][0]
    assert impala["verdict"] == "confirmed"
    assert impala["citation_sources"] == ["room"]
    assert impala["citations"][0]["url"] == IMPALA["url"]
    assert impala["citations"][0]["title"] == IMPALA["title"]
    assert impala["citations"][0]["excerpt"] == IMPALA["excerpt"]


def test_a_fresh_search_is_recorded_by_the_server_and_marked_as_a_search():
    """The run ledger is fed from `event.get_function_responses()`, the same
    server-side path a build uses, so a title or an excerpt here exists only
    because the tool returned it."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()

    cassette = body["claims"][1]
    assert cassette["verdict"] == "anachronism"
    assert cassette["citation_sources"] == ["search"]
    assert cassette["citations"][0]["title"] == CASSETTE["title"]
    assert cassette["citations"][0]["excerpt"] == CASSETTE["excerpts"][0]


def test_a_cited_url_in_neither_ledger_leaves_the_claim_on_screen_unsourced():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    nowhere = "https://nowhere.example/x"
    runner = a_runner(
        produces={
            "claims": {"claims": [{"text": "a '61 Impala", "claim_type": "object"}]},
            "verdicts": f"- confirmed | a '61 Impala | {nowhere} | Sold new.",
            "search_count": 1,
        },
        events=[],
    )

    with checking(store, runner=runner):
        body = post(TestClient(server.app)).json()

    claim = body["claims"][0]
    assert claim["unsourced_urls"] == [nowhere]
    assert body["unsourced_count"] == 1
    assert claim["verdict"] == "unverifiable", "a stamp with nothing behind it"


# -- what reaches the model, and in which position ---------------------------


def test_the_scene_travels_in_session_state_and_never_as_the_user_turn():
    """A scene posted as the user turn arrives in instruction position, which
    is the one thing claim_extractor's <scene> markers exist to prevent."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store) as runner:
        post(TestClient(server.app))

    turn = "".join(part.text or "" for part in runner.messages[0].parts)
    assert SCENE not in turn
    assert "Impala" not in turn
    assert runner.session_service.seeded[0]["scene"] == SCENE.strip()


def test_the_rooms_files_are_in_front_of_the_verifier_before_it_can_search():
    """"The room is consulted before a search is spent" is a property of the
    prompt, and this is the assembly that makes it one."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store) as runner:
        post(TestClient(server.app))

    room_files = runner.session_service.seeded[0]["room_files"]
    assert "SETTING" in room_files
    assert "Impalas of that generation ran 1961 to 1964" in room_files
    assert IMPALA["url"] in room_files
    assert IMPALA["excerpt"] in room_files


def test_a_finding_with_no_citation_is_left_out_of_the_rooms_files():
    """The verifier may name only URLs it saw, so an uncited fact gives it
    nothing it is allowed to cite — and leaving it out keeps "the room's files
    were empty" one fact rather than two that can disagree with each other."""
    store, _ = a_store()
    document = filed_room()
    document["categories"]["setting"]["findings"].append(
        {"fact": "Something nobody could source", "citations": [], "unverified_urls": []}
    )
    store.save(UID, ROOM, document)

    with checking(store) as runner:
        post(TestClient(server.app))

    assert "Something nobody could source" not in (
        runner.session_service.seeded[0]["room_files"]
    )


def test_the_check_seeds_its_own_search_budget_and_not_the_builds():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store) as runner:
        post(TestClient(server.app))

    seeded = runner.session_service.seeded[0]["search_budget"]
    assert seeded == config.max_searches_per_check()
    assert seeded != config.max_searches_per_build()


# -- the facts the server computes for itself --------------------------------


def test_the_budget_is_spent_only_when_the_servers_own_count_says_so():
    """parallel_search holds the ceiling and counts every allowed spend into
    session state. The verifier's `budget:` prefix is a claim about the same
    thing, and it is not the authority on it."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store, runner=a_runner(produces=_produces(1))):
        under = post(TestClient(server.app)).json()
    with checking(
        store, runner=a_runner(produces=_produces(config.max_searches_per_check()))
    ):
        spent = post(TestClient(server.app)).json()

    assert under["budget_exhausted"] is False
    assert under["search_count"] == 1
    assert spent["budget_exhausted"] is True
    assert spent["search_count"] == config.max_searches_per_check()


def test_a_scene_with_no_checkable_claims_comes_back_as_a_result_not_an_empty_state():
    """Pure interior dialogue asserts nothing about the world. An empty claim
    set plus one plain line is the answer; a blank panel reads as a failure."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    runner = a_runner(
        produces={"claims": {"claims": []}, "verdicts": "", "search_count": 0}, events=[]
    )

    with checking(store, runner=runner):
        response = post(TestClient(server.app), scene="She is afraid. She says nothing.")

    assert response.status_code == 200
    body = response.json()
    assert body["claims"] == []
    assert body["cover_note"] == (
        "Nothing in this scene made a claim about the world, so there was "
        "nothing for the department to check."
    )
    assert "\n" not in body["cover_note"], "one plain line, not a paragraph"


def test_an_empty_room_and_an_empty_claim_set_gets_the_line_about_the_scene():
    """Both notes are true and only one is useful: a check with nothing to
    check did not lean on a search either."""
    store, _ = a_store()
    store.save(UID, ROOM, barren_room("partial"))
    runner = a_runner(
        produces={"claims": {"claims": []}, "verdicts": "", "search_count": 0}, events=[]
    )

    with checking(store, runner=runner):
        body = post(TestClient(server.app), scene="She is afraid.").json()

    assert "nothing for the department to check" in body["cover_note"]
    assert "fresh search" not in body["cover_note"]


# -- the caps, and what they refuse before spending --------------------------


def test_an_oversized_scene_is_capped_with_the_number_in_the_message():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store) as runner:
        response = post(TestClient(server.app), scene="x" * (config.max_scene_chars() + 1))

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert str(config.max_scene_chars()) in detail
    assert "capped at" in detail
    assert runner.messages == [], "an oversized scene reached the model anyway"


def test_a_scene_exactly_at_the_cap_is_still_checked():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        response = post(TestClient(server.app), scene="x" * config.max_scene_chars())

    assert response.status_code == 200


def test_an_empty_scene_is_refused_rather_than_checked_as_a_scene_of_nothing():
    """claim_extractor's `{scene}` has no `?`, so a scene the server never
    seeded raises — but an empty string seeds fine, renders an empty block,
    and comes back with zero claims, which reads as "nothing in this scene
    made a claim about the world"."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store) as runner:
        response = post(TestClient(server.app), scene="   \n  ")

    assert response.status_code == 400
    assert runner.messages == []


# -- the ceiling a check is admitted under -----------------------------------
#
# Until item 10 there was none. `_ip_limiter` and `_daily_cap` both count
# ROOMS, so neither one ever saw a scene, and a check spends up to
# config.max_searches_per_check() live searches. Anonymous accounts are free
# and zero-click, so the shape was: mint an account, build one room, then check
# unlimited scenes against it forever.
#
# The ceiling lives inside `_run_check`, which is what makes it both doors'
# ceiling rather than this endpoint's — the MCP `check_scene` tool reaches the
# same function object, and tests/test_mcp_protocol.py asserts that identity
# directly.


def test_a_check_is_admitted_under_a_ceiling_rather_than_on_the_token_alone():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    ceiling = config.max_rooms_per_ip_per_hour()

    with checking(store):
        client = TestClient(server.app)
        allowed = [post(client) for _ in range(ceiling)]
        refused = post(client)

    assert [response.status_code for response in allowed] == [200] * ceiling
    assert refused.status_code == 429
    detail = refused.json()["detail"]
    assert str(ceiling) in detail
    assert "hour" in detail
    assert "not limited" in detail


def test_a_check_the_ceiling_refuses_never_reaches_the_pipeline():
    """The point of a ceiling on this endpoint is the searches behind it. A
    refusal that still ran the pipeline would cost exactly what it exists to
    stop."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with mock.patch.object(
        server, "_uid_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)
    ), checking(store) as runner:
        client = TestClient(server.app)
        post(client)
        refused = post(client)

    assert refused.status_code == 429
    assert len(runner.messages) == 1, "a refused check still started the pipeline"


def test_a_room_that_does_not_exist_does_not_cost_a_check_slot():
    """The limiter records on the allow path — it is a spend, not a peek, the
    same property Finding 3 turned on. Charging an hour's check budget for a
    404 would ration the wrong thing: what is being rationed is searches, and
    a room that is not there never reaches one."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with mock.patch.object(
        server, "_uid_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)
    ), checking(store):
        client = TestClient(server.app)
        for _ in range(5):
            assert post(client, run_id="never-existed").status_code == 404
        assert post(client).status_code == 200


def test_a_room_still_being_built_does_not_cost_a_check_slot():
    store, _ = a_store()
    store.save(UID, ROOM, room_to_document(ROOM, None, "running", FILED))
    live = {ROOM: {"status": "running", "uid": UID}}

    with mock.patch.object(
        server, "_uid_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)
    ), checking(store, runs=live):
        client = TestClient(server.app)
        assert post(client).status_code == 409

    store.save(UID, ROOM, filed_room())
    with mock.patch.object(
        server, "_uid_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)
    ), checking(store):
        assert post(TestClient(server.app)).status_code == 200


def test_one_accounts_checks_do_not_throttle_another():
    """Keyed on the account, not the address, for the reason the agent door
    is: a desktop agent behind CGNAT shares one address with strangers."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save(OTHER_UID, ROOM, filed_room())

    with mock.patch.object(
        server, "_uid_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)
    ), checking(store):
        client = TestClient(server.app)
        assert post(client).status_code == 200
        assert post(client).status_code == 429
        with mock.patch("star.server.verify_token", return_value=OTHER_UID):
            assert post(client).status_code == 200


def test_a_writers_builds_and_their_checks_hold_separate_windows():
    """One limiter, two key spaces. Five builds an hour must not cost a writer
    their checks, and five checks must not cost them a build."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with mock.patch.object(
        server, "_uid_limiter", server.RateLimiter(max_per_window=1, window_seconds=3600)
    ), checking(store):
        # The build window for this account, spent.
        assert server._uid_gate(UID) is None
        assert server._uid_gate(UID) is not None
        assert post(TestClient(server.app)).status_code == 200


# -- Decision 5: a check is one request ---------------------------------------


def test_a_check_leaves_no_run_registry_entry_and_hands_back_no_stream_key():
    """The run registry, the capability key, and the resume cursor exist
    because a build runs 146s to 420s+. A check is one request and imports
    none of it."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()
        assert server._runs == {}

    serialized = json.dumps(body)
    assert "stream_key" not in serialized
    assert "run_id" not in serialized


def test_the_check_runner_holds_pipeline_b_and_not_pipeline_a():
    """Wiring the build pipeline into the check runner would still answer,
    slowly, expensively, and with the wrong agents."""
    assert server._check_runner.agent is check_scene
    assert server._check_runner is not server._runner


# -- failure, bounded and quiet ----------------------------------------------


def test_a_check_that_overruns_its_ceiling_fails_naming_the_cap():
    """There is nothing partial worth salvaging from a scene check, so the
    ceiling turns into a refusal that names itself rather than a half answer."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with (
        checking(store, runner=a_runner(hangs=True)),
        mock.patch("star.server.config.check_timeout_seconds", return_value=1),
    ):
        response = post(TestClient(server.app))

    assert response.status_code == 504
    assert "1-second limit" in response.json()["detail"]


def test_a_check_that_blows_up_says_nothing_about_our_internals(caplog):
    """The reader gets plain language; the detail goes to the log, because
    losing it there would be as bad as leaking it to a stranger."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    boom = RuntimeError("psycopg2.OperationalError: password authentication failed")

    with (
        checking(store, runner=a_runner(raises=boom)),
        caplog.at_level(logging.ERROR, logger="star.server"),
    ):
        response = post(TestClient(server.app))

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "psycopg2" not in detail
    assert "password" not in detail
    assert "RuntimeError" not in detail
    assert "unexpected problem" in detail

    logged = "\n".join(record.getMessage() for record in caplog.records) + caplog.text
    assert "psycopg2" in logged


def test_a_claim_set_that_does_not_validate_fails_visibly(caplog):
    """ADK leaves the extractor's output in state as a plain dict. Papering
    over a malformed one with an empty list would reach the reader as "nothing
    in this scene made a claim about the world" — a silent lie shaped like a
    result."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    runner = a_runner(produces={"claims": {"claims": "not a list"}}, events=[])

    with (
        checking(store, runner=runner),
        caplog.at_level(logging.ERROR, logger="star.server"),
    ):
        response = post(TestClient(server.app))

    assert response.status_code == 502


def test_the_session_a_check_ran_on_is_dropped_whether_it_succeeded_or_not():
    """It holds the scene verbatim, and the scene is the paste this surface
    promises can be deleted. Nothing bounds how many checks run in a day
    either, so a session service that only grows is a leak with no ceiling."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store) as good:
        post(TestClient(server.app))
    with checking(store, runner=a_runner(raises=RuntimeError("boom"))) as bad:
        post(TestClient(server.app))

    assert good.session_service.deleted == ["check-0"]
    assert good.session_service.sessions == {}
    assert bad.session_service.deleted == ["check-0"]


# -- persistence -------------------------------------------------------------


def test_a_check_files_at_the_path_the_spec_names():
    store, client = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()

    assert f"users/{UID}/rooms/{ROOM}/scenes/{body['scene_id']}" in client.data


def test_a_filed_check_keeps_the_scene_and_everything_the_schema_names():
    store, client = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()

    document = client.data[f"users/{UID}/rooms/{ROOM}/scenes/{body['scene_id']}"]
    assert document["scene"] == SCENE.strip()
    assert set(document) == {
        "scene_id",
        "created_at",
        "scene",
        "claims",
        "parse_rate",
        "unsourced_count",
        "field_notes",
        "search_count",
        "budget_exhausted",
        "cover_note",
        "scope_note",
    }


def test_filing_a_check_does_not_disturb_the_room_it_was_checked_against():
    """The scenes are a subcollection, not a field: a room read stays the size
    of a room, and a late `_persist` cannot overwrite a filed check."""
    store, client = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        post(TestClient(server.app))

    assert client.data[f"users/{UID}/rooms/{ROOM}"] == filed_room()


def test_a_filed_check_reads_back_as_it_returned_plus_the_scene_it_checked():
    """Replayable without re-running. The one field the read adds is the
    scene, because the caller that ran the check already had it and a reader
    coming back tomorrow does not — and the claims are exact substrings of it
    rather than offsets into it, so without the text they are quotations with
    nowhere to sit."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        client = TestClient(server.app)
        filed = post(client).json()
        read = client.get(
            f"/api/rooms/{ROOM}/scenes/{filed['scene_id']}", headers=AUTH
        ).json()

    assert read == {**filed, "scene": SCENE.strip()}


def test_the_list_of_filed_checks_does_not_carry_the_scenes():
    """A room with twenty filed checks would otherwise send twenty scenes
    across the wire to draw a list."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        client = TestClient(server.app)
        filed = post(client).json()
        listed = client.get(f"/api/rooms/{ROOM}/scenes", headers=AUTH).json()

    assert [scene["scene_id"] for scene in listed["scenes"]] == [filed["scene_id"]]
    assert listed["scenes"][0]["claim_count"] == 2
    assert "scene" not in listed["scenes"][0]
    assert "claims" not in listed["scenes"][0]


def test_listing_an_unknown_room_and_another_uids_room_answer_identically():
    """Both are empty rather than 404: the path is rooted at `users/{uid}`, so
    there is nothing to find either way and no read that could tell them
    apart."""
    store, _ = a_store()
    store.save("uid-two", ROOM, filed_room())
    store.save_scene("uid-two", ROOM, "s1", {"scene_id": "s1", "scene": "theirs"})

    with checking(store):
        client = TestClient(server.app)
        theirs = client.get(f"/api/rooms/{ROOM}/scenes", headers=AUTH)
        absent = client.get("/api/rooms/never-existed/scenes", headers=AUTH)

    assert theirs.json() == absent.json() == {"scenes": []}


def test_reading_another_uids_filed_check_is_not_found():
    store, _ = a_store()
    store.save("uid-two", ROOM, filed_room())
    store.save_scene("uid-two", ROOM, "s1", {"scene_id": "s1", "scene": "theirs"})

    with checking(store):
        response = TestClient(server.app).get(
            f"/api/rooms/{ROOM}/scenes/s1", headers=AUTH
        )

    assert response.status_code == 404


# -- delete, and the scene text that goes with it ----------------------------


def every_stored_string(value):
    """Every string anywhere in the fake store, at any depth.

    Searching the store rather than a `json.dumps` of it, because dumping
    escapes the newlines a scene is full of and the substring would miss what
    is plainly still there.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from every_stored_string(item)
    elif isinstance(value, list):
        for item in value:
            yield from every_stored_string(item)


def test_deleting_a_filed_check_takes_the_stored_scene_text_with_it():
    """The whole promise above the paste box. Not that the id stops listing —
    that the pages stop being kept, anywhere."""
    store, client = a_store()
    store.save(UID, ROOM, filed_room())

    def scene_is_stored():
        return any(SCENE.strip() in text for text in every_stored_string(client.data))

    with checking(store):
        http = TestClient(server.app)
        filed = post(http).json()
        path = f"users/{UID}/rooms/{ROOM}/scenes/{filed['scene_id']}"
        assert scene_is_stored()

        deleted = http.delete(
            f"/api/rooms/{ROOM}/scenes/{filed['scene_id']}", headers=AUTH
        )
        read_back = http.get(
            f"/api/rooms/{ROOM}/scenes/{filed['scene_id']}", headers=AUTH
        )

    assert deleted.status_code == 204
    assert path not in client.data
    assert not scene_is_stored()
    assert read_back.status_code == 404


def test_deleting_a_check_that_was_never_filed_is_not_found():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        response = TestClient(server.app).delete(
            f"/api/rooms/{ROOM}/scenes/never-filed", headers=AUTH
        )

    assert response.status_code == 404


def test_another_uids_filed_check_survives_a_delete_aimed_at_it():
    store, client = a_store()
    store.save("uid-two", ROOM, filed_room())
    store.save_scene("uid-two", ROOM, "s1", {"scene_id": "s1", "scene": "their pages"})

    with checking(store):
        response = TestClient(server.app).delete(
            f"/api/rooms/{ROOM}/scenes/s1", headers=AUTH
        )

    assert response.status_code == 404
    assert client.data[f"users/uid-two/rooms/{ROOM}/scenes/s1"]["scene"] == "their pages"


# -- the loop the whole instance shares --------------------------------------


@pytest.mark.asyncio
async def test_every_firestore_call_a_check_makes_happens_off_the_event_loop():
    """The Firestore client is blocking and this loop is shared with every
    open SSE stream on the instance. A synchronous read here stalls all of
    them, and a check makes two calls, one of them behind a model."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    recorder = _ThreadRecordingStore(store)

    loop_thread = threading.get_ident()
    with (
        mock.patch("star.server._store", recorder),
        mock.patch("star.server._check_runner", a_runner()),
        mock.patch.dict(server._runs, {}, clear=True),
    ):
        await server._run_check(UID, ROOM, SCENE.strip())

    assert recorder.calls == ["get", "save_scene"]
    assert loop_thread not in recorder.threads


# -- copy ---------------------------------------------------------------------


def test_no_part_of_a_check_says_the_bare_word_verified():
    """The rule that binds every other surface, and the MCP door has no
    renderer between this payload and its reader."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        body = post(TestClient(server.app)).json()

    assert "verified" not in json.dumps(body).lower()


# -- the stored shapes, pure --------------------------------------------------

RESULT = {
    "scene_id": "abc123",
    "created_at": FILED,
    "claims": [{"text": "a '61 Impala", "claim_type": "object", "verdict": "confirmed"}],
    "parse_rate": 1.0,
    "unsourced_count": 0,
    "field_notes": "",
    "search_count": 3,
    "budget_exhausted": False,
    "cover_note": "",
    "scope_note": "",
}


def test_scene_to_document_takes_its_identity_off_the_result_not_a_second_clock():
    """A second `now()` in the write path is how a stamped date drifts away
    from the answer it belongs to — the failure `_persist` documents for a
    room, avoided here by never minting either field."""
    document = scene_to_document(RESULT, "INT. GARAGE - NIGHT")

    assert document["scene_id"] == "abc123"
    assert document["created_at"] == FILED
    assert document["scene"] == "INT. GARAGE - NIGHT"


def test_document_to_scene_round_trips_the_payload_the_check_returned():
    document = scene_to_document(RESULT, "INT. GARAGE - NIGHT")

    assert document_to_scene(document) == {**RESULT, "scene": "INT. GARAGE - NIGHT"}


def test_scene_summary_counts_the_claims_it_refuses_to_carry():
    summary = scene_summary(scene_to_document(RESULT, "INT. GARAGE - NIGHT"))

    assert summary == {
        "scene_id": "abc123",
        "created_at": FILED,
        "claim_count": 1,
        "search_count": 3,
        "unsourced_count": 0,
        "budget_exhausted": False,
    }


def test_list_scenes_returns_the_newest_filed_check_first():
    store, _ = a_store()
    for scene_id, created_at in (("old", "2026-08-01T00:00:00Z"), ("new", "2026-08-09T00:00:00Z")):
        result = {**RESULT, "scene_id": scene_id, "created_at": created_at}
        store.save_scene(UID, ROOM, scene_id, scene_to_document(result, "INT. GARAGE"))

    listed = store.list_scenes(UID, ROOM)

    assert [scene["scene_id"] for scene in listed] == ["new", "old"]


def test_a_rooms_filed_checks_do_not_show_up_in_the_rail():
    """`list_rooms` streams one collection, and a subcollection is not part of
    it. If it were, every filed check would arrive as a room with no title."""
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())
    store.save_scene(UID, ROOM, "s1", scene_to_document(RESULT, "INT. GARAGE"))

    assert [room["run_id"] for room in store.list_rooms(UID)] == [ROOM]


# -- deleting a room ---------------------------------------------------------
#
# The opposite call from a scene, and the endpoint says why: a scene is the
# writer's script pages and goes for good the moment they say so, while a room
# is research that cost money and minutes, where losing it is the expensive
# mistake rather than keeping it. Both leave the reader's sight at once.


def test_deleting_a_room_hides_it_but_keeps_it_for_the_window():
    store, client = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        http = TestClient(server.app)
        gone = http.delete(f"/api/rooms/{ROOM}", headers=AUTH)
        listed = http.get("/api/rooms", headers=AUTH).json()
        read_back = http.get(f"/api/rooms/{ROOM}", headers=AUTH)

    assert gone.status_code == 200
    body = gone.json()
    assert body["retention_days"] == config.room_retention_days(), (
        "a delete that will not say when it becomes permanent is asking the "
        "reader to trust a number nobody stated"
    )
    assert listed["rooms"] == [], "out of the rail immediately"

    # Still readable, and readable AS deleted.
    assert read_back.status_code == 200, "404 would make restore impossible"
    assert read_back.json()["status"] == "deleted"
    assert read_back.json()["deleted_at"] == body["deleted_at"]
    assert client.data[f"users/{UID}/rooms/{ROOM}"]["deleted_at"], "kept, not destroyed"


def test_a_deleted_room_can_be_restored_and_comes_back_to_the_rail():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        http = TestClient(server.app)
        http.delete(f"/api/rooms/{ROOM}", headers=AUTH)
        restored = http.post(f"/api/rooms/{ROOM}/restore", headers=AUTH)
        listed = http.get("/api/rooms", headers=AUTH).json()

    assert restored.status_code == 200
    assert [r["run_id"] for r in listed["rooms"]] == [ROOM]


def test_restoring_a_room_that_was_never_deleted_is_not_found():
    store, _ = a_store()
    store.save(UID, ROOM, filed_room())

    with checking(store):
        response = TestClient(server.app).post(f"/api/rooms/{ROOM}/restore", headers=AUTH)

    assert response.status_code == 404


def test_deleting_a_room_that_is_not_there_is_not_found():
    store, _ = a_store()

    with checking(store):
        response = TestClient(server.app).delete("/api/rooms/never-existed", headers=AUTH)

    assert response.status_code == 404


def test_another_uids_room_survives_a_delete_aimed_at_it():
    store, client = a_store()
    store.save("uid-two", ROOM, filed_room())

    with checking(store):
        response = TestClient(server.app).delete(f"/api/rooms/{ROOM}", headers=AUTH)

    assert response.status_code == 404
    assert not client.data[f"users/uid-two/rooms/{ROOM}"].get("deleted_at"), (
        "ownership is by path construction: users/{uid}/rooms never resolves "
        "across accounts, so this is refused by the shape of the read"
    )
