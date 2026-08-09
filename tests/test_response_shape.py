"""Pins the ADK function-response envelope observed on 2026-08-09, ADK 2.6.2.

Recorded by scripts/inspect_response_shape.py against the live API. If an ADK
upgrade changes the wrapping, this fails loudly rather than silently emptying
every ledger and dropping every citation.
"""

from star.ledger import SourceLedger, unwrap_results

# The exact envelope printed by the inspection script for its first function
# response (name="parallel_search"): python type dict, top-level keys
# ["result"], unwrapped count 9. Trimmed to one source here; title, url, and
# the excerpt text below are copied verbatim from that live run.
OBSERVED = {
    "result": [
        {
            "title": "Sun Studio, Memphis",
            "url": "https://www.gpsmycity.com/attractions/sun-studio-23386.html",
            "excerpts": [
                (
                    "# Sun Studio, Memphis (must see)\n"
                    "Sun Studio is one of Memphis’s essential music landmarks, "
                    "known worldwide as the “Birthplace of Rock ’n’ "
                    "Roll.” It stands on Union Avenue in the historic core of "
                    "Memphis, housed in a modest brick structure that began in "
                    "1950 as the Memphis Recording Service.\nFounded by producer "
                    "Sam Phillips in the same building as the Sun Records label, "
                    "the studio occupied a former auto repair shop."
                )
            ],
        }
    ]
}


def test_the_observed_adk_envelope_unwraps():
    results = unwrap_results(OBSERVED)
    assert len(results) == 1
    assert results[0]["url"] == "https://www.gpsmycity.com/attractions/sun-studio-23386.html"


def test_the_observed_envelope_records_into_the_ledger():
    ledger = SourceLedger()
    assert ledger.record("Setting researcher", OBSERVED) == 1
    assert ledger.has("https://www.gpsmycity.com/attractions/sun-studio-23386.html")
