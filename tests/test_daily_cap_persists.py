"""The daily cap survives a deploy.

THE DEFECT, written down on 2026-08-16 while producing an operations runbook
and true since the day the cap shipped. `DailyCap` kept its count in process
memory, and `star/guards.py`'s module docstring already said what that meant —
"the counters also reset on every redeploy and every instance recycle,
min-instances or not." It was recorded as a property of the design rather than
as the hole it is.

So **every deploy handed the world a fresh hundred rooms.** A hundred rooms is
up to three thousand live searches, and a push twenty minutes before a public
demo was the moment the service was least protected.

The hazard was in the docstring the whole time. Nobody read it as a to-do
because it was filed under an explanation of why in-memory was correct.
"""

import logging

from star.guards import DailyCap


class Store:
    """The store seam, in memory. Records calls so a test can count them."""

    def __init__(self, saved: dict | None = None) -> None:
        self.saved = saved
        self.reads = 0
        self.writes: list[tuple[int, int]] = []

    def read(self) -> dict | None:
        self.reads += 1
        return self.saved

    def write(self, day: int, count: int) -> None:
        self.writes.append((day, count))
        self.saved = {"day": day, "count": count}


class Broken(Store):
    def read(self):
        raise RuntimeError("Firestore is having a day")

    def write(self, day, count):
        raise RuntimeError("Firestore is having a day")


DAY = 20_680  # a whole UTC day number
NOW = DAY * 86400 + 3600


def test_a_restart_does_not_hand_back_the_whole_day():
    """THE POINT. Two caps over one store is what a redeploy looks like: the
    process is replaced and a brand-new object reads what the old one left."""
    store = Store()
    before = DailyCap(max_per_day=3, store=store)
    assert before.check(NOW) and before.check(NOW) and before.check(NOW)
    assert before.check(NOW) is False, "the third exhausts it"

    after = DailyCap(max_per_day=3, store=store)

    assert after.check(NOW) is False, "a restart does not reset the cap"
    assert after.count_for(NOW) == 3


def test_without_a_store_it_behaves_exactly_as_it_used_to():
    """Every existing caller and test constructs it with one argument."""
    cap = DailyCap(max_per_day=2)

    assert cap.check(NOW) and cap.check(NOW)
    assert cap.check(NOW) is False
    assert DailyCap(max_per_day=2).check(NOW) is True, "and a fresh one is fresh"


def test_a_new_day_still_rolls_and_the_roll_is_written():
    store = Store({"day": DAY, "count": 100})
    cap = DailyCap(max_per_day=3, store=store)

    tomorrow = (DAY + 1) * 86400 + 60
    assert cap.check(tomorrow) is True
    assert store.saved == {"day": DAY + 1, "count": 1}


def test_yesterdays_count_does_not_refuse_today():
    """The stored day is read back, so the roll has to happen after the load
    rather than before it — the ordering is the whole fix."""
    store = Store({"day": DAY - 1, "count": 100})
    cap = DailyCap(max_per_day=3, store=store)

    assert cap.count_for(NOW) == 0


def test_a_refusal_is_still_written_so_the_next_process_sees_it():
    """A cap that only persisted on success would forget it was exhausted the
    moment a deploy landed between the hundredth build and the hundred-and-
    first — which is exactly the window this exists for."""
    store = Store()
    cap = DailyCap(max_per_day=1, store=store)
    cap.check(NOW)
    store.writes.clear()

    assert cap.check(NOW) is False
    assert store.writes == [(DAY, 1)], "the refusal wrote the count too"


def test_it_reads_before_every_decision_rather_than_once():
    """Memory is usually right on a single instance. The one moment it is
    stale is the first call after a restart, which is precisely the moment the
    cap used to read zero."""
    store = Store()
    cap = DailyCap(max_per_day=5, store=store)
    cap.check(NOW)
    cap.check(NOW)

    assert store.reads >= 2


def test_a_broken_store_fails_open_rather_than_closing_the_service(caplog):
    """DELIBERATE, and the opposite of the sweep-origin guard's fail-closed.

    This cap is a cost guard, not a security boundary. Refusing every build in
    the building because Firestore blinked turns a spend control into an
    outage, and an outage is the worse failure for a service whose whole job is
    to be demonstrated. What must not happen is silence.
    """
    cap = DailyCap(max_per_day=2, store=Broken())

    with caplog.at_level(logging.ERROR):
        assert cap.check(NOW) is True
        assert cap.check(NOW) is True
        assert cap.check(NOW) is False, "and the in-memory count still bounds it"

    assert caplog.records, "a store failure is logged, never swallowed"


def test_a_junk_document_is_ignored_rather_than_trusted():
    """Firestore holds whatever was last written, including by a hand-edit or
    an older shape. A day that is not an integer is not a day."""
    for junk in ({"day": "today", "count": 99}, {"count": 99}, {}, None):
        cap = DailyCap(max_per_day=2, store=Store(junk))
        assert cap.check(NOW) is True, junk


def test_the_stored_count_bounds_a_process_that_never_built_anything():
    """A fresh process reading a full day refuses immediately, having admitted
    nothing itself. That is the redeploy case stated the other way round."""
    cap = DailyCap(max_per_day=100, store=Store({"day": DAY, "count": 100}))

    assert cap.check(NOW) is False
    assert cap.count_for(NOW) == 100
