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

import time


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
    """A global kill switch measured in whole UTC days."""

    def __init__(self, max_per_day: int) -> None:
        self._max = max_per_day
        self._day: int | None = None
        self._count = 0

    def _roll(self, now: float) -> None:
        day = int(now // 86400)
        if day != self._day:
            self._day, self._count = day, 0

    def check(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self._roll(now)
        if self._count >= self._max:
            return False
        self._count += 1
        return True

    def count_for(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        self._roll(now)
        return self._count
