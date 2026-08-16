"""Abuse guards for a publicly reachable endpoint.

One room build spends real money — a dozen or more live web searches plus
several Gemini calls. Without a ceiling, a public URL is an open invitation
to spend someone else's budget, and the first sign would be the bill.

Both guards are in-memory, and that is correct rather than a compromise —
but only under BOTH halves of the scaling config, not one: the service
deploys with `--max-instances=1` (because `_runs` is per-process and live
runs already require instance affinity) AND `--min-instances=1`. The second
flag is just as load-bearing as the first. These counters are constructed
once at import time, as module-level objects in star/server.py; scaling to
zero when idle destroys the process, and the next request cold-starts a
fresh one with both counters back at zero. With `--max-instances=1` alone,
the "100 builds/day" cap is actually "100 builds per instance lifetime," and
instance lifetime has no lower bound — an attacker sends 100 builds, waits
out the idle window, and repeats; the counters also reset on every redeploy
and every instance recycle, min-instances or not. Only with min-instances=1
AND max-instances=1 together does one process live long enough that an
in-memory counter IS the global counter.

If anyone later raises the instance count, these silently become per-instance:
the per-IP limit multiplies by the instance count and the daily cap stops
being daily-global. Moving to a shared store is the fix, and it has to happen
in the same change as the scale-up, not after.
"""

import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window limiter keyed by caller.

    `max_keys` bounds the number of distinct callers tracked at once,
    independent of the stale-key sweep below. That sweep is O(n) in the
    number of tracked keys and runs on every `check()` call, on a
    single-threaded event loop shared with every other request and every
    open SSE stream on the instance — so the number of tracked keys is a
    cost every caller pays, not just the one adding a new key.

    Before Finding 3's reordering (see star/server.py's create_room), the
    daily cap was checked before the per-IP limiter, which meant a caller
    the IP limiter would go on to refuse had already been turned away by the
    daily cap before ever reaching this dict — so `_hits` stayed bounded at
    roughly the daily cap's size (~100 keys) as an accident of ordering, not
    by design. With the per-IP check running first, a caller rotating its
    key (see star/server.py's `_caller_key` docstring on why neither the
    X-Forwarded-For key nor the uid is a strong identity) passes the IP
    check every time and is refused only by the daily cap — so without a
    bound of its own, `_hits` would grow by one key per request instead of
    being incidentally capped. A limiter that cannot afford to keep tracking
    new callers should refuse the next one rather than grow past what it can
    afford; that is what `max_keys` enforces.
    """

    def __init__(
        self, max_per_window: int, window_seconds: float, max_keys: int = 5000
    ) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, now: float | None = None) -> bool:
        """Record a call and return whether it is allowed."""
        now = time.time() if now is None else now
        cutoff = now - self._window

        # Evict every stale key, not just this one. Otherwise an attacker
        # rotating source addresses grows this dict without bound, which is
        # its own denial of service.
        for existing in list(self._hits):
            fresh = [t for t in self._hits[existing] if t > cutoff]
            if fresh:
                self._hits[existing] = fresh
            else:
                del self._hits[existing]

        if key not in self._hits and len(self._hits) >= self._max_keys:
            # A caller this limiter has no memory of, arriving when the
            # limiter is already at capacity, is refused outright — growing
            # the dict to accommodate it would let an identity-rotating
            # attacker force this exact sweep to cost more on every future
            # call, for everyone, including legitimate callers already
            # being tracked (see the class docstring).
            return False

        hits = self._hits.setdefault(key, [])
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True

    def __len__(self) -> int:
        return len(self._hits)


class DailyCap:
    """A global kill switch measured in whole UTC days, and it now survives.

    THE DEFECT THIS CLOSES, written down while producing an operations runbook
    on 2026-08-16 and true since the day the cap shipped: this counter lived in
    process memory, so **every deploy handed the world a fresh hundred rooms.**
    So did every instance recycle. The module docstring above already said so —
    "the counters also reset on every redeploy and every instance recycle,
    min-instances or not" — and it was recorded as a property of the design
    rather than as the hole it is.

    A hundred rooms is up to three thousand live searches. A push twenty
    minutes before a public demo is the moment this service is least protected,
    which is the opposite of what anybody wants from a deploy.

    So the count is persisted. `store` is any object with `read()` returning
    `{"day": int, "count": int}` or None, and `write(day, count)`. Injected
    rather than imported so this class stays unit-testable without Firestore,
    which is the same reason `RoomStore` takes a client.

    IT FAILS OPEN, DELIBERATELY, AND LOUDLY. If the store raises, the in-memory
    count is used and the failure is logged. This cap is a cost guard, not a
    security boundary — refusing every build in the building because Firestore
    blinked would turn a spend control into an outage, and an outage is the
    worse failure for a service whose whole job is to be demonstrated. The log
    line is what makes that a decision rather than a silence.

    STILL NOT ATOMIC, and that is still fine for exactly one reason: the
    service runs on a single instance with a single-threaded event loop, so
    there is no second writer to race. If `--max-instances` ever rises above
    one, this read-then-write needs a transaction in the same change — the same
    sentence the module docstring already makes about every other counter here.
    """

    def __init__(self, max_per_day: int, store: object | None = None) -> None:
        self._max = max_per_day
        self._day: int | None = None
        self._count = 0
        self._store = store

    def _load(self) -> None:
        """Pull the stored day and count into memory. Best effort."""
        if self._store is None:
            return
        try:
            saved = self._store.read()
        except Exception:
            logger.exception("Daily cap could not be read; using the in-memory count")
            return
        if not saved:
            return
        day = saved.get("day")
        if isinstance(day, int):
            self._day = day
            self._count = int(saved.get("count") or 0)

    def _save(self) -> None:
        if self._store is None or self._day is None:
            return
        try:
            self._store.write(self._day, self._count)
        except Exception:
            logger.exception("Daily cap could not be written; the count may reset")

    def _roll(self, now: float) -> None:
        day = int(now // 86400)
        if day != self._day:
            self._day, self._count = day, 0

    def check(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        # Read first, every time. A single instance means memory is usually
        # right, but "usually" is what this class was wrong about before: the
        # one moment it is stale is the first call after a restart, which is
        # precisely the moment the cap used to be zero.
        self._load()
        self._roll(now)
        if self._count >= self._max:
            self._save()
            return False
        self._count += 1
        self._save()
        return True

    def count_for(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        self._load()
        self._roll(now)
        return self._count
