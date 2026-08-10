"""Wires the web/auth.js Node tests into pytest.

web/auth.js is a browser ES module (imports an absolute "/config.js" path,
relies on `fetch` and `localStorage` globals) — pytest can't import it
directly. The scripts under tests/js/ do the real work: they patch the one
browser-root import line, stub the globals with node:assert checks, and prove
behaviour with deterministic, gate-controlled fetch stubs rather than
timing-dependent ones. This wrapper just shells out to Node so `pytest` stays
the single entry point, and skips cleanly on a machine without Node instead of
failing the whole suite.

Parametrized over every tests/js/test_*.mjs rather than naming one, so a new
scenario file is picked up by adding it. Files not matching that glob
(_auth_module.mjs, the shared loader) are helpers, not tests.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_NODE = shutil.which("node")
_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS_DIR = Path(__file__).resolve().parent / "js"
_SCRIPTS = sorted(_JS_DIR.glob("test_*.mjs"))


def test_the_js_suite_is_not_silently_empty():
    """A glob that matches nothing would make every test below vanish quietly.

    This is the one assertion that cannot live in the parametrized test: a
    parametrize over an empty list collects zero cases and reports success.
    """
    assert _SCRIPTS, f"no tests/js/test_*.mjs found under {_JS_DIR}"


@pytest.mark.skipif(_NODE is None, reason="node is not on PATH")
@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.stem)
def test_js_module_behaviour(script: Path):
    result = subprocess.run(
        [_NODE, str(script)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{script} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
