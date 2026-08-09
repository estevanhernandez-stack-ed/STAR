"""Wires web/auth.js's concurrency-guard test into pytest.

web/auth.js is a browser ES module (imports an absolute "/config.js" path,
relies on `fetch` and `localStorage` globals) — pytest can't import it
directly. tests/js/test_auth_concurrency.mjs does the real work: it patches
the one browser-root import line, stubs the globals with node:assert
checks, and proves the getIdToken() concurrency guard with a deterministic,
gate-controlled fetch stub rather than a timing-dependent one. This wrapper
just shells out to Node so `pytest` stays the single entry point, and skips
cleanly on a machine without Node instead of failing the whole suite.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_NODE = shutil.which("node")
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = Path(__file__).resolve().parent / "js" / "test_auth_concurrency.mjs"


@pytest.mark.skipif(_NODE is None, reason="node is not on PATH")
def test_auth_concurrency_guard():
    result = subprocess.run(
        [_NODE, str(_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{_SCRIPT} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
