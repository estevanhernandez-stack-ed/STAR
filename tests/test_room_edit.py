"""Naming a room, and saying which room it follows.

THE BUG. `"Untitled room"` was permanent. There was no rename path in the
store, the server or the web app, so a build whose intake could not find a
title produced a room that could never be called anything else. The judge's
round-two review filed it under *Room hygiene*: three Untitled rooms and an
errored husk, and no way to clean any of it up over either door.

And rooms had no relation to one another, so a story spanning five eras was
five strangers in a rail sorted newest-first.

The endpoint is one PATCH for both edits because they are one act — a writer
looking at a room, deciding what it is and what it belongs to. What these tests
mostly hold is the refusals: three different ways a link can be wrong, each
answered by name, because "that did not work" on a link a writer just drew is
the least useful sentence available.
"""

from __future__ import annotations

from unittest import mock

from fastapi.testclient import TestClient

from star import config, server

AUTH = {"Authorization": "Bearer t"}


def _rooms(*pairs: tuple[str, str]) -> list[dict]:
    """The rail's own shape: a run_id and what it continues from."""
    return [{"run_id": run_id, "continues": parent} for run_id, parent in pairs]


def _client(rooms: list[dict] | None = None, **store_attrs):
    fake = mock.Mock()
    fake.list_rooms.return_value = rooms if rooms is not None else _rooms(("a", ""))
    for name, value in store_attrs.items():
        getattr(fake, name).return_value = value
    return TestClient(server.app), fake


def _patch(client, fake, run_id: str, body: dict):
    with (
        mock.patch("star.server.verify_token", return_value="uid-one"),
        mock.patch("star.server._store", fake),
    ):
        return client.patch(f"/api/rooms/{run_id}", json=body, headers=AUTH)


# --- naming ------------------------------------------------------------------


def test_a_room_can_be_renamed():
    client, fake = _client(set_title="The Substitute Sync")

    response = _patch(client, fake, "a", {"title": "The Substitute Sync"})

    assert response.status_code == 200
    assert response.json()["title"] == "The Substitute Sync"
    fake.set_title.assert_called_once_with("uid-one", "a", "The Substitute Sync")


def test_the_reply_carries_the_name_the_room_now_has_not_the_one_that_was_sent():
    """An empty title restores the derived one, so the two differ. The browser
    prints what comes back; printing what it typed would leave a writer who
    cleared the field watching the rail disagree with the room."""
    client, fake = _client(set_title="1962 Memphis")

    response = _patch(client, fake, "a", {"title": ""})

    assert response.json()["title"] == "1962 Memphis"


def test_a_name_longer_than_the_cap_is_refused_with_the_cap_in_the_sentence():
    client, fake = _client()

    response = _patch(
        client, fake, "a", {"title": "x" * (config.max_room_title_chars() + 1)}
    )

    assert response.status_code == 400
    assert str(config.max_room_title_chars()) in response.json()["detail"]
    fake.set_title.assert_not_called()


def test_a_name_at_exactly_the_cap_is_allowed():
    """The boundary belongs to the writer. A cap that refuses its own stated
    number is a cap that lies about where it is."""
    client, fake = _client(set_title="x" * config.max_room_title_chars())

    response = _patch(
        client, fake, "a", {"title": "x" * config.max_room_title_chars()}
    )

    assert response.status_code == 200


def test_renaming_a_room_this_account_does_not_own_is_a_404():
    client, fake = _client(set_title=None)

    assert _patch(client, fake, "a", {"title": "Mine now"}).status_code == 404


# --- the link ----------------------------------------------------------------


def test_a_room_can_say_which_room_it_follows():
    client, fake = _client(_rooms(("first", ""), ("second", "")), set_continues=True)

    response = _patch(client, fake, "second", {"continues": "first"})

    assert response.status_code == 200
    assert response.json()["continues"] == "first"
    fake.set_continues.assert_called_once_with("uid-one", "second", "first")


def test_the_link_can_be_cleared_without_naming_a_parent():
    client, fake = _client(set_continues=True)

    response = _patch(client, fake, "a", {"continues": ""})

    assert response.status_code == 200
    fake.set_continues.assert_called_once_with("uid-one", "a", "")
    # An empty parent is not a lookup, so the room list is never consulted.
    fake.list_rooms.assert_not_called()


def test_a_room_cannot_continue_from_itself():
    client, fake = _client()

    response = _patch(client, fake, "a", {"continues": "a"})

    assert response.status_code == 400
    # The sentence only the self-check produces. Mutation testing found that
    # asserting on "itself" alone proved nothing: deleting this guard lets the
    # ring guard below catch the same case, and its message also ends "loop
    # back into itself" — which is the wrong explanation here, because that
    # room does not follow this one, it IS this one. The specific refusal is
    # the point, so the specific refusal is what gets pinned.
    assert "cannot continue from itself" in response.json()["detail"]
    fake.set_continues.assert_not_called()


def test_a_parent_filed_under_another_account_is_refused_by_name():
    client, fake = _client(_rooms(("mine", "")))

    response = _patch(client, fake, "mine", {"continues": "someone-elses"})

    assert response.status_code == 404
    assert "not filed under this account" in response.json()["detail"]
    fake.set_continues.assert_not_called()


def test_a_link_that_would_close_a_ring_is_refused_by_name():
    """b already follows a. Pointing a at b closes the ring, and the rail's
    grouping walk would never terminate."""
    client, fake = _client(_rooms(("a", ""), ("b", "a")))

    response = _patch(client, fake, "a", {"continues": "b"})

    assert response.status_code == 400
    assert "loop" in response.json()["detail"]
    fake.set_continues.assert_not_called()


def test_a_ring_further_up_the_chain_is_still_refused():
    """The walk is up the whole chain, not one hop. c follows b follows a, so
    pointing a at c closes a three-room ring."""
    client, fake = _client(_rooms(("a", ""), ("b", "a"), ("c", "b")))

    response = _patch(client, fake, "a", {"continues": "c"})

    assert response.status_code == 400
    assert "loop" in response.json()["detail"]


def test_a_long_legitimate_chain_is_allowed():
    """The guard refuses rings, not depth. Five eras of one story is five rooms
    deep and entirely correct."""
    client, fake = _client(
        _rooms(("one", ""), ("two", "one"), ("three", "two"), ("four", "three")),
        set_continues=True,
    )

    response = _patch(client, fake, "four", {"continues": "three"})

    assert response.status_code == 200


def test_a_ring_already_in_the_data_does_not_hang_the_request_that_fixes_it():
    """Written by an older build, or by two edits racing. The walk is bounded by
    what it has already seen as well as by reaching the top, so a request that
    is trying to repair a ring cannot be trapped inside it."""
    client, fake = _client(_rooms(("x", "y"), ("y", "x"), ("new", "")))

    response = _patch(client, fake, "new", {"continues": "x"})

    assert response.status_code == 200


def test_linking_a_room_this_account_does_not_own_is_a_404():
    client, fake = _client(_rooms(("first", ""), ("second", "")), set_continues=False)

    assert _patch(client, fake, "second", {"continues": "first"}).status_code == 404


# --- both, and neither -------------------------------------------------------


def test_both_edits_in_one_save():
    client, fake = _client(
        _rooms(("first", ""), ("second", "")),
        set_title="Hamburg, 1960",
        set_continues=True,
    )

    response = _patch(
        client, fake, "second", {"title": "Hamburg, 1960", "continues": "first"}
    )

    assert response.json() == {
        "run_id": "second",
        "title": "Hamburg, 1960",
        "continues": "first",
    }


def test_a_key_that_is_absent_is_left_alone():
    """`title: ""` and `continues: ""` both mean something, so absence has to
    mean something else. A model with defaults could not tell them apart, which
    is why the body is read as a plain dict."""
    client, fake = _client(set_title="Named")

    response = _patch(client, fake, "a", {"title": "Named"})

    fake.set_continues.assert_not_called()
    assert "continues" not in response.json()
