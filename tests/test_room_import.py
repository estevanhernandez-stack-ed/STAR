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
from tests.test_scenes import AUTH, UID, a_store

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


def test_a_built_room_says_nothing_about_being_imported():
    """The field is the whole signal, so a room that was researched here must
    never carry it — including one written before the field existed."""
    document = room_to_document("r1", LIVERPOOL, "complete", "2026-08-13T00:00:00Z")

    assert document["imported_at"] == ""
