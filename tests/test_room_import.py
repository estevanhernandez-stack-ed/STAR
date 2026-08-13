"""Somebody else's research, filed into an account that never ran it.

This is the second path where text a user typed becomes part of a room's
record, and it is far wider than the first: the annotation import lets a writer
add a note to one claim, and this mints whole rooms. Anyone can type a
plausible fact and a real-looking url into a spreadsheet.

So the property under test is not "the file parses". It is that an imported
room can never pass for a researched one — it carries `imported_at`, it claims
no searches, and it brings no bible. Everything else here is about the file
surviving the round trip it was exported from.
"""

from unittest import mock

from fastapi.testclient import TestClient

from star import server
from star.exports import chain_to_csv, read_room, room_to_csv
from star.store import room_to_document
from tests.test_scenes import AUTH, UID, _FakeCheckRunner, a_store

LIVERPOOL = {
    "created_at": "2026-08-13T11:51:03Z",
    "story_profile": {"title": "Doctor Who Special: Liverpool", "era": "1958-1962"},
    "research_bible": "## Setting\n\nA cellar in West Derby.\n",
    "search_count": 41,
    "source_count": 58,
    "categories": {
        "setting": {
            "findings": [
                {
                    "fact": "Mona Best opened the Casbah on 29 August 1959.",
                    "citations": [
                        {"url": "https://casbah.example", "title": "The Casbah", "excerpt": "A cellar."},
                        {"url": "https://second.example", "title": "Also", "excerpt": "Again."},
                    ],
                }
            ]
        },
        "logistics": {
            "findings": [
                {"fact": "Night trams ran on reduced headways.", "citations": []},
            ]
        },
    },
}

HAMBURG = {
    "created_at": "2026-08-13T02:14:17Z",
    "story_profile": {"title": "Doctor Who: Liverpool and Hamburg", "era": "1958-1962"},
    "continues": "liverpool-1",
    "categories": {
        "objects_props": {
            "findings": [
                {
                    "fact": "Preludin was made by Boehringer Ingelheim.",
                    "citations": [
                        {"url": "https://phen.example", "title": "Phenmetrazine", "excerpt": "1952."}
                    ],
                }
            ]
        }
    },
}


def a_chain_file():
    return chain_to_csv([("hamburg-1", HAMBURG), ("liverpool-1", LIVERPOOL)])


# -- the reader, which is pure ------------------------------------------------


def test_a_room_survives_the_round_trip_it_was_exported_from():
    rooms, complaints = read_room(room_to_csv(LIVERPOOL, "liverpool-1"))

    assert complaints == []
    assert [key for key, _ in rooms] == ["liverpool-1"]
    result = rooms[0][1]
    assert result["story_profile"] == {
        "title": "Doctor Who Special: Liverpool",
        "era": "1958-1962",
    }
    assert sorted(result["categories"]) == ["logistics", "setting"]
    casbah = result["categories"]["setting"]["findings"][0]
    assert casbah["fact"] == "Mona Best opened the Casbah on 29 August 1959."
    assert [c["url"] for c in casbah["citations"]] == [
        "https://casbah.example",
        "https://second.example",
    ], "the two rows one finding occupied come back as one finding with two sources"
    assert casbah["citations"][0]["excerpt"] == "A cellar.", "the page's own words survive"


def test_a_finding_nobody_could_cite_survives_as_one():
    """A fact with no source is exactly the row worth keeping. Dropping it on
    the way back in would quietly improve the room."""
    rooms, _ = read_room(room_to_csv(LIVERPOOL, "liverpool-1"))
    trams = rooms[0][1]["categories"]["logistics"]["findings"][0]

    assert trams["fact"].startswith("Night trams")
    assert trams["citations"] == []


def test_nothing_the_file_says_about_its_own_research_is_believed():
    """THE PROPERTY THE FEATURE RESTS ON.

    A file can claim any number. The reader counts what actually arrived, and
    it produces no bible, no search count and no field notes at all — there is
    no shape it can return that would let a room claim work this account did
    not do.
    """
    rooms, _ = read_room(room_to_csv(LIVERPOOL, "liverpool-1"))
    result = rooms[0][1]

    assert LIVERPOOL["source_count"] == 58, "the file claims 58"
    assert result["source_count"] == 2, (
        "and two distinct urls actually arrived — counted from what is here, "
        "never carried from a column a sender can type anything into"
    )
    assert "research_bible" not in result
    assert "search_count" not in result
    assert result["categories"]["setting"]["parse_rate"] == 0.0


def test_a_chain_file_comes_back_as_several_rooms_in_file_order():
    rooms, _ = read_room(a_chain_file())

    assert [key for key, _ in rooms] == ["hamburg-1", "liverpool-1"], "nearest first"
    assert rooms[0][1]["continues"] == "liverpool-1", "by the SENDER's id, for the caller to remap"
    assert rooms[1][1]["continues"] == ""


def test_the_same_source_twice_on_one_finding_is_one_source():
    """Two rows saying it does not make it two sources, and a room whose count
    double-counts is a room overstating its research."""
    doubled = (
        "drawer,fact,source_title,source_url,source_excerpt,room,era,continues,run_id\r\n"
        "setting,A fact,T,https://a.example,One,R,1960,,r1\r\n"
        "setting,A fact,T,https://a.example,One,R,1960,,r1\r\n"
    )
    rooms, _ = read_room(doubled)

    assert len(rooms[0][1]["categories"]["setting"]["findings"][0]["citations"]) == 1
    assert rooms[0][1]["source_count"] == 1


def test_a_drawer_this_department_does_not_have_is_filed_and_named():
    """Filed under Setting rather than dropped: a fifth drawer renders nowhere,
    and losing the row would lose research the sender paid for."""
    odd = (
        "drawer,fact,source_url,room,run_id\r\n"
        "weather,It rained,https://a.example,R,r1\r\n"
        "Objects & Props,A Vespa,https://b.example,R,r1\r\n"
    )
    rooms, complaints = read_room(odd)
    categories = rooms[0][1]["categories"]

    assert categories["setting"]["findings"][0]["fact"] == "It rained"
    assert categories["objects_props"]["findings"][0]["fact"] == "A Vespa", (
        "a heading a human would write is read as the drawer it names"
    )
    assert any("weather" in c for c in complaints)
    assert not any("objects" in c.casefold() for c in complaints), "that one was understood"


def test_a_file_that_is_not_a_research_export_is_refused_with_the_reason():
    rooms, complaints = read_room("claim,verdict\nKaiserkeller,confirmed\n")
    assert rooms == []
    assert "no `fact` column" in complaints[0]
    assert "sweep export is a different file" in complaints[0], (
        "and it names the mistake somebody will actually make"
    )

    assert read_room("") == ([], ["That file has no rows under its header."])


def test_a_row_stating_nothing_is_named_rather_than_dropped():
    rooms, complaints = read_room(
        "drawer,fact,source_url,room,run_id\r\n"
        "setting,,https://a.example,R,r1\r\n"
        "setting,A fact,https://b.example,R,r1\r\n"
    )

    assert len(rooms[0][1]["categories"]["setting"]["findings"]) == 1
    assert "Row 2 states no fact" in complaints[0]


def test_a_formula_escaped_on_the_way_out_is_unescaped_on_the_way_back():
    hostile = {
        "story_profile": {"title": "X"},
        "categories": {"setting": {"findings": [{"fact": "=1+1", "citations": []}]}},
    }
    rooms, _ = read_room(room_to_csv(hostile, "r1"))

    assert rooms[0][1]["categories"]["setting"]["findings"][0]["fact"] == "=1+1"


# -- the endpoint, which mints rooms ------------------------------------------


def a_client(store):
    return mock.patch("star.server.verify_token", return_value=UID), mock.patch(
        "star.server._store", store
    )


def test_the_first_press_reports_and_writes_nothing():
    """The arming `delete_room` and the annotation import both use. This one
    mints rooms in somebody's account; they should see what they are getting."""
    store, data = a_store()
    auth, patched = a_client(store)

    with auth, patched:
        body = TestClient(server.app).post(
            "/api/rooms/import", json={"csv": a_chain_file()}, headers=AUTH
        ).json()

    assert body["filed"] is False
    assert [r["title"] for r in body["rooms"]] == [
        "Doctor Who: Liverpool and Hamburg",
        "Doctor Who Special: Liverpool",
    ]
    assert body["rooms"][0]["findings"] == 1 and body["rooms"][0]["sources"] == 1
    assert not data.data, "and nothing was written"


def test_the_second_press_files_rooms_that_say_they_were_imported():
    store, data = a_store()
    auth, patched = a_client(store)

    with auth, patched:
        body = TestClient(server.app).post(
            "/api/rooms/import",
            json={"csv": a_chain_file(), "apply": True},
            headers=AUTH,
        ).json()

    assert body["filed"] is True
    stored = [data.data[f"users/{UID}/rooms/{r['run_id']}"] for r in body["rooms"]]

    for document in stored:
        assert document["imported_at"], (
            "THE FIELD EVERYTHING ELSE READS. A room that arrived in a "
            "spreadsheet and renders like a built one is the room-sized "
            "version of what the annotation import refuses to do one claim at "
            "a time"
        )
        assert document["search_count"] == 0, "this account ran none, and claims none"
        assert document["research_bible"] == "", (
            "and brings no bible: a derived document shipped beside its source "
            "can disagree with it, and this one would be describing findings "
            "that may not have survived the file"
        )
        assert document["status"] == "complete"


def test_a_chain_arrives_linked_by_the_ids_this_account_just_minted():
    """The link in the file names the SENDER'S room, which means nothing here.
    The only account that can resolve it is one holding both rooms at once,
    which is exactly this request."""
    store, data = a_store()
    auth, patched = a_client(store)

    with auth, patched:
        body = TestClient(server.app).post(
            "/api/rooms/import",
            json={"csv": a_chain_file(), "apply": True},
            headers=AUTH,
        ).json()

    hamburg, liverpool = body["rooms"]
    stored = data.data[f"users/{UID}/rooms/{hamburg['run_id']}"]

    assert stored["continues"] == liverpool["run_id"]
    assert stored["continues"] != "liverpool-1", "not the sender's id, which is nobody's here"


def test_a_room_whose_parent_is_not_in_the_file_arrives_unlinked_and_says_so():
    store, _ = a_store()
    auth, patched = a_client(store)

    with auth, patched:
        body = TestClient(server.app).post(
            "/api/rooms/import",
            json={"csv": room_to_csv(HAMBURG, "hamburg-1"), "apply": True},
            headers=AUTH,
        ).json()

    assert body["rooms"][0]["continues"] == ""
    assert any("arrives unlinked" in c for c in body["complaints"])


def test_importing_the_same_file_twice_makes_two_rooms_and_never_merges():
    """No merge, no overwrite. A file cannot reach into a room this account
    already holds — the ids it names are the sender's, and honouring them would
    let a spreadsheet address somebody else's research."""
    store, data = a_store()
    auth, patched = a_client(store)
    payload = {"csv": room_to_csv(LIVERPOOL, "liverpool-1"), "apply": True}

    with auth, patched:
        client = TestClient(server.app)
        first = client.post("/api/rooms/import", json=payload, headers=AUTH).json()
        second = client.post("/api/rooms/import", json=payload, headers=AUTH).json()

    assert first["rooms"][0]["run_id"] != second["rooms"][0]["run_id"]
    assert len([k for k in data.data if f"users/{UID}/rooms/" in k]) == 2


def test_a_file_past_the_ceiling_is_refused_before_it_is_parsed():
    store, _ = a_store()
    auth, patched = a_client(store)

    with auth, patched, mock.patch("star.config.max_import_chars", return_value=50):
        response = TestClient(server.app).post(
            "/api/rooms/import", json={"csv": a_chain_file()}, headers=AUTH
        )

    assert response.status_code == 400
    assert "ceiling" in response.json()["detail"]


def test_more_rooms_than_one_import_files_is_refused_by_count():
    store, _ = a_store()
    auth, patched = a_client(store)

    with auth, patched, mock.patch("star.config.max_rooms_per_import", return_value=1):
        response = TestClient(server.app).post(
            "/api/rooms/import", json={"csv": a_chain_file()}, headers=AUTH
        )

    assert response.status_code == 400
    assert "2 rooms" in response.json()["detail"]


def test_an_import_needs_an_account():
    response = TestClient(server.app).post("/api/rooms/import", json={"csv": "x"})
    assert response.status_code == 401


# -- the bible, which is the half of an import that is not free ---------------


BIBLE = "## 1. Setting & Atmosphere\n\nA cellar in West Derby [1].\n"


def a_bible_runner(**kwargs):
    return _FakeCheckRunner(produces={"research_bible": BIBLE}, **kwargs)


def writing(store, runner=None):
    runner = runner or a_bible_runner()
    return runner, (
        mock.patch("star.server.verify_token", return_value=UID),
        mock.patch("star.server._store", store),
        mock.patch("star.server._bible_runner", runner),
    )


def an_imported_room():
    """A room in the shape the import files: findings, sources, no bible."""
    rooms, _ = read_room(room_to_csv(LIVERPOOL, "liverpool-1"))
    result = {**rooms[0][1], "imported_at": "2026-08-13T12:00:00Z", "search_count": 0}
    return room_to_document("r1", result, "complete", "2026-08-13T12:00:00Z")


def test_an_imported_room_can_be_given_a_bible_written_from_what_it_holds():
    store, data = a_store()
    store.save(UID, "r1", an_imported_room())
    _, patches = writing(store)

    with patches[0], patches[1], patches[2]:
        body = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH).json()

    assert body["research_bible"] == BIBLE.strip(), "trimmed, the way an empty one is detected"
    assert data.data[f"users/{UID}/rooms/r1"]["research_bible"] == BIBLE.strip(), "and filed"
    assert data.data[f"users/{UID}/rooms/r1"]["imported_at"], (
        "writing a bible does not launder the room into a researched one"
    )
    assert data.data[f"users/{UID}/rooms/r1"]["search_count"] == 0, "and spends no searches"


def test_the_editor_is_handed_the_rooms_own_findings_and_sources():
    """THE STATE SEAM. A build seeds these from researchers as they run; this
    seeds them from what was filed, which is what makes the editor runnable a
    second time over a room that never had researchers at all."""
    store, _ = a_store()
    store.save(UID, "r1", an_imported_room())
    runner, patches = writing(store)

    with patches[0], patches[1], patches[2]:
        TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    state = runner.session_service.seeded[0]
    assert "Mona Best opened the Casbah" in state["findings_setting"]
    assert "Night trams" in state["findings_logistics"]
    assert "- The Casbah :: https://casbah.example\n" in state["sources_setting"], (
        "in parallel_search's own format, because that is the format the "
        "editor's prompt was written against"
    )
    assert state["sources_logistics"] == "", "a drawer whose findings cite nothing"
    assert state["story_profile"]["title"] == "Doctor Who Special: Liverpool"
    assert runner.session_service.deleted == [runner.session_service.seeded and "check-0"], (
        "and the session is dropped either way"
    )


def test_a_room_that_already_has_a_bible_is_refused_rather_than_overwritten():
    """Rewriting is destructive on a document a build was paid for, and it is
    not what this is."""
    store, data = a_store()
    document = an_imported_room()
    document["research_bible"] = "## The one the build wrote\n"
    store.save(UID, "r1", document)
    runner, patches = writing(store)

    with patches[0], patches[1], patches[2]:
        response = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    assert response.status_code == 409
    assert "already has a bible" in response.json()["detail"]
    assert data.data[f"users/{UID}/rooms/r1"]["research_bible"] == "## The one the build wrote\n"
    assert runner.messages == [], "and the editor was never run, so nothing was spent"


def test_a_room_with_no_findings_is_refused_before_the_editor_runs():
    store, _ = a_store()
    store.save(UID, "r1", room_to_document("r1", {"categories": {}}, "complete", "2026-08-13"))
    runner, patches = writing(store)

    with patches[0], patches[1], patches[2]:
        response = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    assert response.status_code == 400
    assert "Nothing was spent" in response.json()["detail"]
    assert runner.messages == []


def test_an_editor_that_comes_back_empty_changes_nothing():
    """A bible that arrived as an empty string would replace a room's absent
    bible with an absent bible and report success."""
    store, data = a_store()
    store.save(UID, "r1", an_imported_room())
    _, patches = writing(store, _FakeCheckRunner(produces={"research_bible": "  "}))

    with patches[0], patches[1], patches[2]:
        response = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    assert response.status_code == 502
    assert data.data[f"users/{UID}/rooms/r1"]["research_bible"] == ""


def test_an_editor_that_raises_leaves_the_research_untouched():
    store, data = a_store()
    store.save(UID, "r1", an_imported_room())
    _, patches = writing(store, _FakeCheckRunner(raises=RuntimeError("gemini 503")))

    with patches[0], patches[1], patches[2]:
        response = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    assert response.status_code == 502
    assert "research in the drawers is untouched" in response.json()["detail"]
    assert data.data[f"users/{UID}/rooms/r1"]["categories"]["setting"]["findings"]


def test_another_accounts_room_cannot_be_given_a_bible():
    store, _ = a_store()
    store.save(UID, "r1", an_imported_room())
    runner = a_bible_runner()

    with mock.patch("star.server.verify_token", return_value="uid-two"), \
            mock.patch("star.server._store", store), \
            mock.patch("star.server._bible_runner", runner):
        response = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    assert response.status_code == 404
    assert runner.messages == []


def test_writing_a_bible_holds_its_own_hourly_window():
    """Its own key space. An editor pass is not a build and not a check, and
    none of the three should eat another's slots."""
    store, _ = a_store()
    store.save(UID, "r1", an_imported_room())
    runner, patches = writing(store)

    with patches[0], patches[1], patches[2], \
            mock.patch.object(server._uid_limiter, "check", return_value=False) as gate:
        response = TestClient(server.app).post("/api/rooms/r1/bible", headers=AUTH)

    assert response.status_code == 429
    assert gate.call_args[0][0] == f"bible:{UID}"
    assert runner.messages == [], "refused before the model call, not after"


def test_a_built_room_says_nothing_about_being_imported():
    """The field is the whole signal, so a room that was researched here must
    never carry it — including one written before the field existed."""
    document = room_to_document("r1", LIVERPOOL, "complete", "2026-08-13T00:00:00Z")

    assert document["imported_at"] == ""
