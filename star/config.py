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
    """Fail fast on missing keys (review fix M5) instead of mid-pipeline."""
    missing = []
    if not os.environ.get("PARALLEL_API_KEY"):
        missing.append("PARALLEL_API_KEY")
    using_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in ("TRUE", "1")
    if not using_vertex and not os.environ.get("GOOGLE_API_KEY"):
        missing.append("GOOGLE_API_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
