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
