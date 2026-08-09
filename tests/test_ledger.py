from star.ledger import SourceLedger, unwrap_results

SOURCE_A = {
    "title": "Stax Museum — History",
    "url": "https://staxmuseum.example/history",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}
SOURCE_B = {
    "title": "Fender Jazzmaster",
    "url": "https://fender.example/jazzmaster",
    "excerpts": ["Introduced in 1958."],
}


def test_unwrap_accepts_a_bare_list():
    assert unwrap_results([SOURCE_A]) == [SOURCE_A]


def test_unwrap_accepts_the_result_key():
    assert unwrap_results({"result": [SOURCE_A]}) == [SOURCE_A]


def test_unwrap_accepts_the_results_key():
    assert unwrap_results({"results": [SOURCE_A]}) == [SOURCE_A]


def test_unwrap_accepts_a_nested_wrapping():
    assert unwrap_results({"response": {"result": [SOURCE_A]}}) == [SOURCE_A]


def test_unwrap_accepts_a_single_bare_source():
    assert unwrap_results(SOURCE_A) == [SOURCE_A]


def test_unwrap_returns_empty_for_junk():
    assert unwrap_results(None) == []
    assert unwrap_results("nonsense") == []
    assert unwrap_results({"unexpected": 1}) == []


def test_record_stores_title_and_excerpts():
    ledger = SourceLedger()
    added = ledger.record("Setting researcher", {"result": [SOURCE_A]})

    assert added == 1
    entry = ledger.get("https://staxmuseum.example/history")
    assert entry.title == "Stax Museum — History"
    assert entry.excerpts == ["The old Capitol Theatre floor still raked downward."]
    assert entry.found_by == {"Setting researcher"}


def test_record_merges_the_same_url_across_agents():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [SOURCE_A])
    ledger.record("Props researcher", [SOURCE_A])

    assert len(ledger) == 1
    assert ledger.get(SOURCE_A["url"]).found_by == {
        "Setting researcher",
        "Props researcher",
    }


def test_record_accumulates_new_excerpts_without_duplicating():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [SOURCE_A])
    ledger.record(
        "Props researcher",
        [{**SOURCE_A, "excerpts": ["The old Capitol Theatre floor still raked downward.", "A second excerpt."]}],
    )

    assert ledger.get(SOURCE_A["url"]).excerpts == [
        "The old Capitol Theatre floor still raked downward.",
        "A second excerpt.",
    ]


def test_record_skips_the_budget_error_dict():
    ledger = SourceLedger()
    added = ledger.record("Setting researcher", [{"error": "Search budget exhausted"}])

    assert added == 0
    assert len(ledger) == 0


def test_has_and_urls():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [SOURCE_A, SOURCE_B])

    assert ledger.has(SOURCE_A["url"]) is True
    assert ledger.has("https://nowhere.example/invented") is False
    assert sorted(ledger.urls) == sorted([SOURCE_A["url"], SOURCE_B["url"]])
