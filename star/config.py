"""Central configuration (review fix M3).

One place for model choices and limits. For demo week, pin explicit
versioned model IDs via env vars — `-latest` is a floating alias and can
change behavior under a rehearsed demo.
"""

import os

# Pinned, not floating. `gemini-flash-latest` is an alias that resolved to
# gemini-3.6-flash on 2026-08-09 — the model both verified room builds ran on.
# Leaving the alias in place means Google can move the model out from under a
# rehearsed demo. Revisit after the 2026-09-07 deadline.
_PINNED_FLASH = "gemini-3.6-flash"


def fast_model() -> str:
    """Extraction/verification steps."""
    return os.environ.get("STAR_FAST_MODEL", _PINNED_FLASH)


def smart_model() -> str:
    """Planning and synthesis steps."""
    return os.environ.get("STAR_SMART_MODEL", _PINNED_FLASH)


def max_searches_per_build() -> int:
    return int(os.environ.get("STAR_MAX_SEARCHES_PER_BUILD", "30"))


def max_treatment_chars() -> int:
    return int(os.environ.get("STAR_MAX_TREATMENT_CHARS", "8000"))


def max_rooms_per_ip_per_hour() -> int:
    """Per-caller ceiling on a public endpoint that spends money to answer."""
    return int(os.environ.get("STAR_MAX_ROOMS_PER_IP_PER_HOUR", "5"))


def max_rooms_per_day() -> int:
    """Global kill switch. One build is roughly 15 searches; 100 builds a day
    is a generous demo allowance and a cheap disaster ceiling."""
    return int(os.environ.get("STAR_MAX_ROOMS_PER_DAY", "100"))


def max_rate_limiter_keys() -> int:
    """Bound on distinct callers `_ip_limiter` tracks at once (Finding 3b).

    Reordering the daily cap behind the per-IP check (Finding 3) removed an
    accidental bound: the daily cap used to turn away identity-rotating
    callers before they ever reached the per-IP limiter's dict, capping it
    near the daily cap's own size. With the per-IP check running first, that
    accident is gone, so RateLimiter needs an explicit bound of its own. A
    few thousand distinct callers a day is generous for a hackathon demo and
    still cheap for the O(n) stale-key sweep in RateLimiter.check() to walk
    on every request, on a single-threaded loop shared with every open SSE
    stream.
    """
    return int(os.environ.get("STAR_MAX_RATE_LIMITER_KEYS", "5000"))


def max_synthesis_output_tokens() -> int:
    """Hard ceiling on the bible, because generation runs away without one.

    Measured 2026-08-09: gemini-3.6-flash generates at roughly 115 tokens/sec
    and permits 65,536 output tokens, so an unbounded synthesis call can spend
    9.5 minutes before it stops on its own. One did. Good bibles have run
    11,000-17,000 characters, comfortably under 6,000 tokens; 16,000 leaves
    generous headroom while capping the worst case near two minutes.
    """
    return int(os.environ.get("STAR_MAX_SYNTHESIS_TOKENS", "16000"))


def max_sources_per_category() -> int:
    """Cap the source list handed to synthesis.

    Deliberately generous. This started at 25 on the theory that a long source
    list was inflating synthesis output, but measurement did not support it:
    bibles came in at 6.2k, 16.5k, and 16.5k characters across runs whose
    caps differed, and the spread within a single cap was as wide as the
    spread between caps. Run-to-run variance swamps this knob.

    The real runaway guard is max_synthesis_output_tokens, which bounds the
    output directly rather than guessing at an input that correlates with it.
    This cap stays only to keep a pathological source list from bloating the
    prompt, and 60 is well above what any observed run produced per category.
    """
    return int(os.environ.get("STAR_MAX_SOURCES_PER_CATEGORY", "60"))


def max_runs_in_memory() -> int:
    """Cap on live entries in `star.server._runs`.

    Each entry holds a `SourceLedger` carrying every excerpt from up to
    `max_searches_per_build()` searches, plus a task reference — nothing
    ever shrinks it on its own. Persistence (star/store.py) is what makes
    eviction safe: a run dropped from memory once it reaches a terminal
    status is still readable back from Firestore via get_room's fallback.
    """
    return int(os.environ.get("STAR_MAX_RUNS_IN_MEMORY", "20"))


def run_timeout_seconds() -> int:
    """Wall-clock ceiling on one room build.

    Independent of any model-level cap: a hung network call, a retry storm, or
    a future agent with its own limits should still surface as a visible error
    rather than a UI that spins forever and a container that never frees the
    connection.

    Raised from 420 to 600 after a legitimate, non-pathological run tripped the
    420s ceiling. Observed durations for one fixed treatment ranged from 146s
    to over 420s, so a ceiling that normal runs hit is a ceiling that turns
    slowness into failure. This is a backstop, not a performance budget: the
    pipeline's duration variance is a separate problem and a real demo risk.
    """
    return int(os.environ.get("STAR_RUN_TIMEOUT_SECONDS", "600"))


def validate_env() -> None:
    """Fail fast on missing keys (review fix M5) instead of mid-pipeline.

    Phase 2 made three more variables load-bearing, and all three fail
    *closed but silently* when absent: `star/auth.py` and `star/store.py`
    read the project id, and `/config.js` serves the API key to the browser.
    With no project id, `firebase_admin` raises inside `_verify`,
    `verify_token` swallows it, and every `/api/` call just 401s — a missing
    env var and a network blip look identical to the user. Checking here
    makes that class of misconfiguration loud at boot instead.
    """
    missing = []
    if not os.environ.get("PARALLEL_API_KEY"):
        missing.append("PARALLEL_API_KEY")
    using_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in ("TRUE", "1")
    if not using_vertex and not os.environ.get("GOOGLE_API_KEY"):
        missing.append("GOOGLE_API_KEY")
    # Either satisfies star/auth.py's _get_app and star/store.py's client
    # property, which both accept the same fallback — see those modules.
    if not (os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")):
        missing.append("FIREBASE_PROJECT_ID (or GOOGLE_CLOUD_PROJECT)")
    if not os.environ.get("FIREBASE_API_KEY"):
        missing.append("FIREBASE_API_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
