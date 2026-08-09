from star.guards import DailyCap, RateLimiter

HOUR = 3600.0


def test_rate_limiter_allows_up_to_the_limit():
    limiter = RateLimiter(max_per_window=3, window_seconds=HOUR)
    assert [limiter.check("1.2.3.4", now=0.0) for _ in range(3)] == [True, True, True]


def test_rate_limiter_refuses_past_the_limit():
    limiter = RateLimiter(max_per_window=2, window_seconds=HOUR)
    limiter.check("1.2.3.4", now=0.0)
    limiter.check("1.2.3.4", now=1.0)

    assert limiter.check("1.2.3.4", now=2.0) is False


def test_rate_limiter_keys_are_independent():
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    assert limiter.check("1.2.3.4", now=0.0) is True
    assert limiter.check("5.6.7.8", now=0.0) is True
    assert limiter.check("1.2.3.4", now=0.0) is False


def test_rate_limiter_forgets_calls_older_than_the_window():
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    limiter.check("1.2.3.4", now=0.0)

    assert limiter.check("1.2.3.4", now=HOUR + 1) is True


def test_rate_limiter_does_not_grow_without_bound():
    """An attacker rotating IPs must not be able to exhaust memory."""
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    for i in range(5000):
        limiter.check(f"10.0.{i // 256}.{i % 256}", now=0.0)

    # Everything is stale an hour later; one call should collect the garbage.
    limiter.check("1.2.3.4", now=HOUR * 2)

    assert len(limiter) <= 2, f"stale keys were never evicted: {len(limiter)}"


def test_daily_cap_allows_up_to_the_limit():
    cap = DailyCap(max_per_day=2)
    assert cap.check(now=0.0) is True
    assert cap.check(now=1.0) is True


def test_daily_cap_refuses_past_the_limit():
    cap = DailyCap(max_per_day=1)
    cap.check(now=0.0)

    assert cap.check(now=1.0) is False


def test_daily_cap_resets_on_a_new_day():
    cap = DailyCap(max_per_day=1)
    cap.check(now=0.0)

    assert cap.check(now=86400.0 + 1) is True


def test_daily_cap_reports_its_current_count():
    cap = DailyCap(max_per_day=10)
    cap.check(now=0.0)
    cap.check(now=1.0)

    assert cap.count_for(now=2.0) == 2
    assert cap.count_for(now=86400.0 + 1) == 0


# --- Finding 3b: reordering the daily cap behind the per-IP check (see
# test_server.py) means a caller rotating its key passes the IP check every
# time and is refused only by the daily cap — so _hits grows once per call
# instead of being bounded by the ~100 daily slots that used to cap it as a
# side effect. RateLimiter needs its own bound. ---


def test_rate_limiter_refuses_a_brand_new_key_once_the_key_bound_is_reached():
    """A limiter that cannot afford to track another caller must refuse that
    caller rather than grow past its bound — the O(n) stale-key sweep in
    check() runs on every call, on a single-threaded loop shared with every
    open SSE stream."""
    limiter = RateLimiter(max_per_window=5, window_seconds=HOUR, max_keys=2)
    assert limiter.check("1.1.1.1", now=0.0) is True
    assert limiter.check("2.2.2.2", now=0.0) is True

    assert limiter.check("3.3.3.3", now=0.0) is False
    assert len(limiter) == 2


def test_rate_limiter_still_checks_an_existing_key_once_the_bound_is_hit():
    """The bound must gate new keys only — a caller already being tracked
    keeps getting real rate-limit decisions, not a blanket refusal."""
    limiter = RateLimiter(max_per_window=2, window_seconds=HOUR, max_keys=2)
    limiter.check("1.1.1.1", now=0.0)
    limiter.check("2.2.2.2", now=0.0)

    assert limiter.check("1.1.1.1", now=1.0) is True
    assert limiter.check("1.1.1.1", now=2.0) is False


def test_rate_limiter_key_bound_defaults_to_a_generous_value():
    """Default must not bite ordinary traffic — a few thousand distinct
    callers a day is a generous demo allowance, not a tuning knob anyone
    should have to touch."""
    limiter = RateLimiter(max_per_window=1, window_seconds=HOUR)
    assert limiter.check("1.1.1.1", now=0.0) is True
    assert len(limiter) == 1
