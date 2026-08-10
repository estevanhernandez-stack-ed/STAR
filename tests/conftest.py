"""Test-wide setup.

`star.server` calls `config.validate_env()` at import time, so dummy keys must
exist before any test imports it. These are never used to make a request.
"""

import os
from unittest import mock

import pytest

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-real")
os.environ.setdefault("PARALLEL_API_KEY", "test-key-not-real")


@pytest.fixture(autouse=True)
def fresh_uid_limiter():
    """Give every test its own per-account limiter.

    `star.server._uid_limiter` is module state constructed once at import, and
    it now sits on the path of every scene check as well as every MCP build.
    Without this, the sixth check anywhere in a whole test session is refused
    by the fifth test's traffic, and the failure surfaces as a bug in whichever
    test happened to run sixth. Production wants exactly that shared object —
    that is the point of it — but a test file does not, and the alternative
    (every scene test remembering to patch it) is the kind of thing one new
    test forgets.

    Constructed with the same arguments star/server.py uses, so a test that
    means to exercise the ceiling still exercises the real one.
    """
    from star import config, server
    from star.guards import RateLimiter

    with mock.patch.object(
        server,
        "_uid_limiter",
        RateLimiter(
            max_per_window=config.max_rooms_per_ip_per_hour(),
            window_seconds=3600,
            max_keys=config.max_rate_limiter_keys(),
        ),
    ):
        yield
