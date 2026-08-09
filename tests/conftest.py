"""Test-wide setup.

`star.server` calls `config.validate_env()` at import time, so dummy keys must
exist before any test imports it. These are never used to make a request.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-real")
os.environ.setdefault("PARALLEL_API_KEY", "test-key-not-real")
