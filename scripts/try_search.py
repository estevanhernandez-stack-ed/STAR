"""Smoke test for the Parallel Search integration.

Usage:  python scripts/try_search.py
Costs one Search API call. Confirms your PARALLEL_API_KEY works and shows
the response shape the researcher agents consume.
"""

from dotenv import load_dotenv

load_dotenv()

from star.tools.parallel_search import parallel_search  # noqa: E402


def main() -> None:
    results = parallel_search(
        objective=(
            "Establish what a working nurse at a large US city hospital in 1998 "
            "would carry during a shift, with era-specific specifics."
        ),
        search_queries=[
            "1990s hospital nurse equipment carried on shift",
            "nursing in the 1990s pager technology hospital",
        ],
    )
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r.get('title')}\n    {r.get('url')}")
        for ex in r.get("excerpts", [])[:2]:
            print(f"    - {ex[:180]}")
    print(f"\n{len(results)} sources returned. Integration OK.")


if __name__ == "__main__":
    main()
