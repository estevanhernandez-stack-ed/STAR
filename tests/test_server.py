from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from star import server
from star.ledger import SourceLedger
from star.models import Category

STAX = {
    "title": "Stax Museum — History",
    "url": "https://staxmuseum.example/history",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}


def test_category_map_covers_every_researcher_author():
    for category in Category:
        assert server._CATEGORY_BY_AUTHOR[f"researcher_{category.value}"] == category


def test_category_map_returns_none_for_non_researchers():
    assert server._CATEGORY_BY_AUTHOR.get("synthesis") is None


def test_build_categories_parses_every_category_from_state():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX])
    state = {"findings_setting": f"- Stax used a converted theater :: {STAX['url']}"}

    categories = server._build_categories(state, ledger)

    assert set(categories) == {c.value for c in Category}
    assert len(categories["setting"].findings) == 1
    assert categories["setting"].findings[0].citations[0].title == "Stax Museum — History"
    assert categories["setting"].parse_rate == 1.0
    assert categories["logistics"].findings == []


def test_categories_serialize_to_the_api_shape():
    """The seam the endpoint test cannot reach: real ResearchDoc -> JSON."""
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX])
    state = {"findings_setting": f"- Stax used a converted theater :: {STAX['url']}"}

    payload = jsonable_encoder(server._build_categories(state, ledger))

    setting = payload["setting"]
    assert setting["category"] == "setting"
    assert setting["parse_rate"] == 1.0
    assert setting["unverified_count"] == 0
    assert setting["findings"][0]["fact"] == "Stax used a converted theater"
    assert setting["findings"][0]["citations"][0]["title"] == "Stax Museum — History"
    assert setting["findings"][0]["citations"][0]["excerpt"]
    assert setting["findings"][0]["unverified_urls"] == []
    assert payload["logistics"]["findings"] == []


def test_room_endpoint_exposes_categories():
    client = TestClient(server.app)
    server._runs["testrun"] = {
        "events": [],
        "status": "complete",
        "search_count": 3,
        "ledger": SourceLedger(),
        "result": {
            "story_profile": {"title": "1962 Memphis"},
            "research_plan": None,
            "research_bible": "# Bible",
            "search_count": 3,
            "categories": {
                "setting": {
                    "category": "setting",
                    "markdown": "raw",
                    "findings": [],
                    "field_notes": "",
                    "parse_rate": 0.0,
                    "unverified_count": 0,
                }
            },
        },
    }

    response = client.get("/api/rooms/testrun")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert "categories" in body["result"]
    assert body["result"]["categories"]["setting"]["parse_rate"] == 0.0

    del server._runs["testrun"]


def test_unknown_room_still_404s():
    client = TestClient(server.app)
    assert client.get("/api/rooms/does-not-exist").status_code == 404


# -- Finding 6: a fifth ADK envelope must fail loud, not silently -----------


def test_maybe_warn_empty_ledger_pushes_a_warning_when_searches_ran_dry():
    """Simulates a hypothetical fifth envelope shape unwrap_results can't
    recognize: searches happened but nothing landed in the ledger."""
    run = {"events": [], "search_count": 3, "ledger": SourceLedger()}

    server._maybe_warn_empty_ledger(run)

    assert len(run["events"]) == 1
    assert run["events"][0]["type"] == "warning"


def test_maybe_warn_empty_ledger_stays_quiet_when_the_ledger_has_sources():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX])
    run = {"events": [], "search_count": 3, "ledger": ledger}

    server._maybe_warn_empty_ledger(run)

    assert run["events"] == []


def test_maybe_warn_empty_ledger_stays_quiet_when_no_searches_ran():
    run = {"events": [], "search_count": 0, "ledger": SourceLedger()}

    server._maybe_warn_empty_ledger(run)

    assert run["events"] == []
