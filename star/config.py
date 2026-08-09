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
