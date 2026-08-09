"""Abuse guards for a publicly reachable endpoint.

One room build spends real money — a dozen or more live web searches plus
several Gemini calls. Without a ceiling, a public URL is an open invitation
to spend someone else's budget, and the first sign would be the bill.

Both guards are in-memory, and that is correct rather than a compromise: the
service deploys with `--max-instances=1` because `_runs` is per-process and
live runs already require instance affinity. With one instance an in-memory
counter IS the global counter.

If anyone later raises the instance count, these silently become per-instance:
the per-IP limit multiplies by the instance count and the daily cap stops
being daily-global. Moving to a shared store is the fix, and it has to happen
in the same change as the scale-up, not after.
"""

import time


class RateLimiter:
    """Sliding-window limiter keyed by caller."""

    def __init__(self, max_per_window: int, window_seconds: float) -> None:
        self._max = max_per_window
        self._window = window_seconds
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
