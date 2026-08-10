from star.ledger import SourceLedger, ledger_from_room, unwrap_results

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


# -- rebuilding a ledger from a filed room, for Pipeline B -------------------
#
# The document shape is the one star/store.py writes: `categories` is a dict
# keyed by category value, each holding a jsonable_encoded ResearchDoc.


def room_document(categories):
    return {
        "run_id": "r1",
        "status": "complete",
        "title": "Soulsville",
        "categories": categories,
    }


def citation(source, excerpt=None):
    return {
        "url": source["url"],
        "title": source["title"],
        "excerpt": source["excerpts"][0] if excerpt is None else excerpt,
    }


def test_ledger_from_room_walks_categories_findings_citations():
    document = room_document(
        {
            "setting": {
                "findings": [
                    {"fact": "The floor sloped", "citations": [citation(SOURCE_A)]},
                    {"fact": "A second fact", "citations": [citation(SOURCE_B)]},
                ]
            }
        }
    )

    ledger = ledger_from_room(document)

    assert len(ledger) == 2
    assert ledger.get(SOURCE_A["url"]).title == "Stax Museum — History"
    assert ledger.get(SOURCE_A["url"]).excerpts == SOURCE_A["excerpts"]


def test_ledger_from_room_labels_each_source_with_the_drawer_it_came_from():
    """`found_by` is what tells a reader the room answered, and which drawer
    of it did."""
    document = room_document(
        {
            "setting": {"findings": [{"citations": [citation(SOURCE_A)]}]},
            "objects_props": {"findings": [{"citations": [citation(SOURCE_B)]}]},
        }
    )

    ledger = ledger_from_room(document)

    assert ledger.get(SOURCE_A["url"]).found_by == {"room:setting"}
    assert ledger.get(SOURCE_B["url"]).found_by == {"room:objects_props"}


def test_ledger_from_room_merges_a_url_two_drawers_both_cited():
    """No new accumulation logic: `record()` already merges by URL and dedupes
    excerpts, and routing the room back through it is what keeps one set of
    rules for what counts as a source."""
    document = room_document(
        {
            "setting": {"findings": [{"citations": [citation(SOURCE_A)]}]},
            "logistics": {
                "findings": [{"citations": [citation(SOURCE_A, "A second excerpt.")]}]
            },
        }
    )

    ledger = ledger_from_room(document)

    assert len(ledger) == 1
    entry = ledger.get(SOURCE_A["url"])
    assert entry.found_by == {"room:setting", "room:logistics"}
    assert entry.excerpts == [SOURCE_A["excerpts"][0], "A second excerpt."]


def test_ledger_from_room_does_not_repeat_an_excerpt_two_drawers_share():
    document = room_document(
        {
            "setting": {"findings": [{"citations": [citation(SOURCE_A)]}]},
            "logistics": {"findings": [{"citations": [citation(SOURCE_A)]}]},
        }
    )

    assert ledger_from_room(document).get(SOURCE_A["url"]).excerpts == (
        SOURCE_A["excerpts"]
    )


def test_ledger_from_room_keeps_a_citation_whose_excerpt_is_empty():
    """A citation with no excerpt is still a source the room holds. It just
    hydrates a check's citation with an empty excerpt rather than none."""
    document = room_document(
        {"setting": {"findings": [{"citations": [citation(SOURCE_A, "")]}]}}
    )

    entry = ledger_from_room(document).get(SOURCE_A["url"])

    assert entry.title == "Stax Museum — History"
    assert entry.excerpts == []


def test_ledger_from_room_skips_a_citation_with_no_url():
    document = room_document(
        {"setting": {"findings": [{"citations": [{"title": "T", "excerpt": "E"}]}]}}
    )

    assert len(ledger_from_room(document)) == 0


def test_a_room_that_filed_nothing_makes_an_empty_ledger_rather_than_an_error():
    """A partial or interrupted build files no findings, and a check against
    it still runs on fresh search alone."""
    assert len(ledger_from_room(room_document({}))) == 0
    assert len(ledger_from_room({"categories": {"setting": {}}})) == 0
    assert len(ledger_from_room({"categories": {"setting": {"findings": []}}})) == 0
    assert len(ledger_from_room({})) == 0
    assert len(ledger_from_room(None)) == 0


def test_a_categories_block_of_the_wrong_shape_degrades_instead_of_raising():
    """Taking a whole check down over the shape of a room is a worse answer
    than running the check without the room's files."""
    assert len(ledger_from_room({"categories": "unexpected"})) == 0
    assert len(ledger_from_room({"categories": None})) == 0
