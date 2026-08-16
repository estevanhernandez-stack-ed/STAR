"""A build that dies mid-flight keeps what it had already researched.

THE DEFECT, scoped in `docs/scope-build-survival-2026-08-16.md`. `_persist` ran
exactly twice per build: once at creation with an empty result, once at a
terminal status. **Nothing wrote in between.** So a build interrupted at ninety
per cent — by a redeploy, which replaces the process, or by an instance recycle
— filed nothing at all. The writer opened the room, found `interrupted`, and
found it empty, having paid for it with live searches and a slot of the daily
cap.

Fixing the cap on 2026-08-16 made this sharper rather than softer. Before that,
a redeploy quietly refunded the slot by resetting the counter. Now the count
persists and the slot correctly stays spent, so an interrupted build costs
something and returned nothing.

WHAT THE SCOPE GOT WRONG, and it is worth keeping. It recommended "call
`_persist` each time a researcher files", on the assumption that `run["result"]`
fills up as the build goes. It does not — `_run_pipeline` assembles the result
exactly once, from the ADK session state, after the whole event loop has
finished. A `_persist` in the loop would have written the same empty document
four more times.

`_salvage` is what makes it work and it already existed for the timeout path:
it reads the session state, builds the categories filed so far, returns False
when there is nothing worth showing, and never raises. The fix is that call
plus a write.
"""

from star import server
from star.guards import DailyCap


class Store:
    def __init__(self, saved=None):
        self.saved = saved

    def read(self):
        return self.saved

    def write(self, day, count):
        self.saved = {"day": day, "count": count}


DAY = 20_680
NOW = DAY * 86400 + 3600


# --- the checkpoint ---------------------------------------------------------


def test_the_checkpoint_writes_through_salvage_rather_than_reinventing_it():
    """A source assertion, and the one that keeps this honest. `_salvage`
    already knows how to read a half-finished build out of the session state,
    already refuses when nothing is worth showing, and already cannot raise.
    A second implementation of that would be a second place to get it wrong."""
    import inspect

    source = inspect.getsource(server)

    assert "if category is not None and await _salvage(run, run_id):" in source
    assert 'await asyncio.to_thread(_persist, run, run_id, "running")' in source


def test_the_checkpoint_is_per_agent_and_not_per_event():
    """Four writes across a build that spends minutes and real money. Guarded
    on `category`, so the events that carry no category — the planner, the
    editor's own turns — do not each trigger a Firestore write."""
    import inspect

    body = inspect.getsource(server._run_pipeline)

    assert "category is not None" in body, "an uncategorised event writes nothing"


def test_persist_writes_the_whole_document_so_a_checkpoint_cannot_erase():
    """The risk the scope named and said to verify before building.

    `_persist` uses `.set()`, which replaces the whole document — so a
    mid-build write had to carry everything the creation write did. It does:
    every call builds the entire document from `room_to_document(...)` with the
    same arguments, and the only thing that differs is how full `run["result"]`
    happens to be. Creation passes None; a checkpoint passes a partial result.
    The document gains fields rather than losing them.
    """
    import inspect

    body = inspect.getsource(server._persist)

    assert "room_to_document(" in body
    assert body.count("_store.save") == 1, "one write, one shape"
    assert 'run.get("result")' in body, "the result is the only part that varies"


# --- the refund -------------------------------------------------------------


def test_an_interrupted_run_gets_its_slot_back():
    cap = DailyCap(max_per_day=2, store=Store())
    assert cap.check(NOW) and cap.check(NOW)
    assert cap.check(NOW) is False, "exhausted"

    cap.refund(NOW)

    assert cap.check(NOW) is True, "the destroyed build's slot is available again"


def test_the_refund_persists_so_the_next_process_sees_it():
    store = Store()
    cap = DailyCap(max_per_day=5, store=store)
    cap.check(NOW)
    cap.check(NOW)
    cap.refund(NOW)

    assert store.saved == {"day": DAY, "count": 1}
    assert DailyCap(max_per_day=5, store=store).count_for(NOW) == 1


def test_a_refund_never_goes_below_zero():
    """Nothing should be able to mint slots by refunding more than it spent."""
    cap = DailyCap(max_per_day=2, store=Store())

    cap.refund(NOW)
    cap.refund(NOW)

    assert cap.count_for(NOW) == 0
    assert cap.check(NOW) and cap.check(NOW)
    assert cap.check(NOW) is False, "the ceiling still holds"


def test_a_refund_does_not_reach_across_a_day_boundary():
    """Yesterday's slot is not today's to give back. A run interrupted at
    23:59 and first read at 00:01 must not decrement a day it never spent."""
    store = Store({"day": DAY, "count": 4})
    cap = DailyCap(max_per_day=100, store=store)

    tomorrow = (DAY + 1) * 86400 + 60
    cap.refund(tomorrow)

    assert cap.count_for(tomorrow) == 0, "today is untouched"


def test_the_refund_fires_once_per_run_at_the_one_place_a_death_is_noticed():
    """`mark_interrupted` returning True means this request flipped the
    document itself, so the refund happens once per run rather than once per
    read of an interrupted room."""
    import inspect

    source = inspect.getsource(server)
    at = source.index("_daily_cap.refund()")
    before = source[:at]

    assert before.rstrip().endswith('document["status"] = "interrupted"') or \
        "mark_interrupted" in before[-900:], "refund sits inside the flip"
    assert source.count("_daily_cap.refund()") == 1, "one refund site, not several"


def test_a_finished_run_keeps_its_slot():
    """Complete, partial and error all spent the money AND produced something
    the room can show. Only a run the department destroyed is refunded."""
    import inspect

    source = inspect.getsource(server)

    for terminal in ('"complete"', '"partial"', '"error"'):
        window = source[source.index(f"_persist(run, run_id, {terminal}") :][:400]
        assert "refund" not in window, f"{terminal} must not refund"
