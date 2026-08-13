"""Rooms that stack, and the reasons stacking is the safe half of Job 2b.

A story spans eras. Liverpool in 1958 and Hamburg in 1960 are two worlds and
want two rooms, each researched from its own treatment — and a check on a
Hamburg scene should still be able to use what Liverpool already found.

What is asserted here is that the chain is read, in the right order, with every
answer able to say which room held it, and that a room with no chain behaves
exactly as it did before any of this existed.
"""


import pytest
from fastapi.testclient import TestClient

from star import chain, server
from star.store import room_to_document
from tests.test_scenes import (
    AUTH,
    IMPALA,
    UID,
    a_runner,
    a_store,
    checking,
)

LIVERPOOL = "room-liverpool"
HAMBURG = "room-hamburg"


def a_room(run_id, title, era, fact, url, continues=""):
    document = room_to_document(
        run_id,
        {
            "story_profile": {"title": title, "era": era},
            "categories": {
                "setting": {
                    "findings": [
                        {
                            "fact": fact,
                            "citations": [{**IMPALA, "url": url}],
                            "unverified_urls": [],
                        }
                    ]
                }
            },
        },
        "complete",
        "2026-08-10T00:00:00+00:00",
    )
    document["continues"] = continues
    return document


def a_chain(store):
    store.save(UID, LIVERPOOL, a_room(
        LIVERPOOL, "Liverpool", "1958",
        "The Casbah opened in a cellar in West Derby in August 1959.",
        "https://casbah.example",
    ))
    store.save(UID, HAMBURG, a_room(
        HAMBURG, "Hamburg", "1960",
        "The Kaiserkeller stood at 36 Grosse Freiheit.",
        "https://kaiser.example",
        continues=LIVERPOOL,
    ))


# -- the pure walk -----------------------------------------------------------


def test_a_chain_is_walked_nearest_first():
    """The order is load-bearing. The verifier reads its files top down under a
    size ceiling, so whatever comes first survives a truncation — and the room
    a writer is working in is the one whose research must never be cut."""
    rooms = {
        "c": {"continues": "b"},
        "b": {"continues": "a"},
        "a": {"continues": ""},
    }

    assert chain.order("c", rooms) == ["c", "b", "a"]
    assert chain.order("a", rooms) == ["a"]


def test_a_chain_that_points_at_itself_does_not_hang():
    """A writer can link two rooms to each other by hand, and a check that
    never came back would be worse than one that answered thinly."""
    rooms = {"a": {"continues": "b"}, "b": {"continues": "a"}}

    assert chain.order("a", rooms) == ["a", "b"]


def test_a_chain_is_bounded_even_when_the_links_are_not():
    rooms = {str(i): {"continues": str(i + 1)} for i in range(100)}

    assert len(chain.order("0", rooms)) == chain.MAX_DEPTH


def test_a_link_to_a_room_that_is_gone_ends_the_chain():
    """The honest outcome for a room deleted out from under a link."""
    rooms = {"a": {"continues": "vanished"}}

    assert chain.order("a", rooms) == ["a"]


def test_a_room_is_named_by_its_title_and_era():
    """A chain exists precisely when two rooms share a story and differ by
    period, so "Liverpool" alone does not say which of the two answered."""
    document = a_room(LIVERPOOL, "Liverpool", "1958", "f", "u")

    assert chain.label(document) == "Liverpool (1958)"
    assert chain.label({"story_profile": {"title": "No era"}}) == "No era"
    assert chain.label({}) == "Untitled room"


# -- what a check actually sees ----------------------------------------------


def _files_seen(runner):
    return runner.session_service.seeded[0]["room_files"]


def test_a_check_on_a_chained_room_sees_the_room_it_follows():
    store, _ = a_store()
    a_chain(store)
    runner = a_runner()

    with checking(store, runner=runner):
        TestClient(server.app).post(
            f"/api/rooms/{HAMBURG}/scenes", json={"scene": "INT. CLUB"}, headers=AUTH
        )

    files = _files_seen(runner)
    assert "Kaiserkeller" in files, "its own research"
    assert "Casbah" in files, (
        "AND the room it follows — this is the whole feature. A Hamburg scene "
        "can now be answered from what Liverpool already found, with no second "
        "search spent"
    )


def test_every_room_in_a_chain_is_named_in_what_the_verifier_reads():
    """A chain that cannot say where a fact came from is a bigger room with
    worse provenance, which is a trade this project does not make."""
    store, _ = a_store()
    a_chain(store)
    runner = a_runner()

    with checking(store, runner=runner):
        TestClient(server.app).post(
            f"/api/rooms/{HAMBURG}/scenes", json={"scene": "INT. CLUB"}, headers=AUTH
        )

    files = _files_seen(runner)
    assert "FROM THE ROOM: Hamburg (1960)" in files
    assert "FROM THE ROOM: Liverpool (1958)" in files
    assert files.index("Hamburg (1960)") < files.index("Liverpool (1958)"), (
        "nearest first, so a truncation cuts the room the writer is not in"
    )


def test_an_unlinked_room_reads_exactly_as_it_did_before():
    """The property that makes stacking safe to add at all: a room with no
    chain must produce the same block it produced before any of this existed —
    no room banner, no change in what a check is answered from."""
    store, _ = a_store()
    a_chain(store)
    runner = a_runner()

    with checking(store, runner=runner):
        TestClient(server.app).post(
            f"/api/rooms/{LIVERPOOL}/scenes", json={"scene": "INT. CELLAR"}, headers=AUTH
        )

    files = _files_seen(runner)
    assert "Casbah" in files
    assert "FROM THE ROOM" not in files, "one room needs no banner saying which"
    assert "Kaiserkeller" not in files, "and a parent's child is not a parent"


def test_a_chain_never_reaches_another_accounts_room():
    """Uid-scoped by path, so a `continues` pointing at somebody else's room
    ends the walk rather than reading it."""
    store, _ = a_store()
    a_chain(store)
    # Hamburg follows a room that exists — but under a different account.
    store.save("uid-two", "room-elsewhere", a_room(
        "room-elsewhere", "Elsewhere", "1999", "A secret.", "https://secret.example"
    ))
    store.save(UID, HAMBURG, a_room(
        HAMBURG, "Hamburg", "1960", "The Kaiserkeller.", "https://kaiser.example",
        continues="room-elsewhere",
    ))
    runner = a_runner()

    with checking(store, runner=runner):
        TestClient(server.app).post(
            f"/api/rooms/{HAMBURG}/scenes", json={"scene": "INT. CLUB"}, headers=AUTH
        )

    assert "secret" not in _files_seen(runner).lower()


def test_an_answer_from_the_parent_room_is_not_downgraded():
    """THE BUG STACKING SHIPPED WITH, and the reason it was worse than useless.

    The verifier is handed every room in the chain, so it can cite a url it
    only ever saw in the room this one follows. `annotate` hydrated that url
    against the NEAR room's ledger alone — where it is not — and
    star/verdicts.py correctly downgraded the verdict to unverifiable with zero
    citations and the note "in neither the room's files nor this check's search
    results".

    So a claim the parent room COULD answer came back unanswerable, and the
    reader was told the source did not exist. Stacking made answers worse than
    not stacking, invisibly: the check reads like an honest "we could not
    settle this".

    Every test in the suite passed through this. They asserted what the
    verifier was SHOWN and never what came back hydrated.
    """
    store, _ = a_store()
    a_chain(store)
    # The verifier answers a Hamburg scene by citing LIVERPOOL's source.
    runner = a_runner(
        produces={
            "claims": {"claims": [{"text": "the Casbah", "claim_type": "geography"}]},
            "verdicts": (
                "- confirmed | the Casbah | https://casbah.example | "
                "Opened in West Derby in 1959.\n"
            ),
            "search_count": 0,
        },
        events=[],
    )

    with checking(store, runner=runner):
        body = TestClient(server.app).post(
            f"/api/rooms/{HAMBURG}/scenes",
            json={"scene": "INT. CLUB — NIGHT"},
            headers=AUTH,
        ).json()

    claim = body["claims"][0]
    assert claim["verdict"] == "confirmed", (
        "the parent room answered it, so it stands. Hydrating against the near "
        "room alone made this 'unverifiable' and told the reader the source was "
        "in neither the files nor the search"
    )
    assert [c["url"] for c in claim["citations"]] == ["https://casbah.example"], (
        "with Liverpool's source attached rather than stripped"
    )
    assert claim["citations"][0]["excerpt"], "and the page's own words with it"
    assert not claim.get("unsourced_urls"), "nothing was left dangling"


def test_a_url_in_no_room_of_the_chain_is_still_refused():
    """The other half. Widening the ledger to the chain must not turn it into a
    ledger that accepts anything — a url nobody researched is still a url the
    department will not stand behind."""
    store, _ = a_store()
    a_chain(store)
    runner = a_runner(
        produces={
            "claims": {"claims": [{"text": "a Vespa", "claim_type": "object"}]},
            "verdicts": "- confirmed | a Vespa | https://invented.example | Sure.\n",
            "search_count": 0,
        },
        events=[],
    )

    with checking(store, runner=runner):
        body = TestClient(server.app).post(
            f"/api/rooms/{HAMBURG}/scenes",
            json={"scene": "EXT. STREET"},
            headers=AUTH,
        ).json()

    claim = body["claims"][0]
    assert claim["verdict"] == "unverifiable"
    assert claim["citations"] == []
    assert "neither the room's files nor" in (claim["note"] or "")


def test_two_rooms_citing_one_page_merge_rather_than_collide():
    """A chain ledger is built through `record()`, which already decides how two
    sightings of a url merge. A second accumulator would be a second set of
    those rules."""
    from star.ledger import ledger_from_chain

    first = {
        "categories": {
            "setting": {
                "findings": [
                    {"citations": [{"url": "https://same.example", "title": "A",
                                    "excerpt": "From Liverpool."}]}
                ]
            }
        }
    }
    second = {
        "categories": {
            "setting": {
                "findings": [
                    {"citations": [{"url": "https://same.example", "title": "A",
                                    "excerpt": "From Hamburg."}]}
                ]
            }
        }
    }

    merged = ledger_from_chain([first, second])

    assert len(merged) == 1, "one page, one entry"
    entry = merged.get("https://same.example")
    assert "From Liverpool." in entry.excerpts
    assert "From Hamburg." in entry.excerpts, "both rooms' words survive"


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_a_chain_of_any_depth_is_read_in_one_pass(depth):
    store, _ = a_store()
    previous = ""
    for i in range(depth):
        run_id = f"room-{i}"
        store.save(UID, run_id, a_room(
            run_id, f"Room {i}", f"19{50 + i}", f"Fact {i}.",
            f"https://f{i}.example", continues=previous,
        ))
        previous = run_id
    runner = a_runner()

    with checking(store, runner=runner):
        TestClient(server.app).post(
            f"/api/rooms/room-{depth - 1}/scenes", json={"scene": "INT. X"}, headers=AUTH
        )

    files = _files_seen(runner)
    for i in range(depth):
        assert f"Fact {i}." in files, f"room {i} of {depth} is in the block"
