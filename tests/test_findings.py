from star.findings import parse_finding_line, parse_findings
from star.ledger import SourceLedger
from star.models import Category

STAX = {
    "title": "Stax Museum — History",
    "url": "https://staxmuseum.example/history",
    "excerpts": ["The old Capitol Theatre floor still raked downward."],
}
ROLLING = {
    "title": "The Sound of Soulsville",
    "url": "https://rollingstone.example/soulsville",
    "excerpts": ["They never leveled the floor."],
}


def make_ledger():
    ledger = SourceLedger()
    ledger.record("Setting researcher", [STAX, ROLLING])
    return ledger


def test_parse_line_pulls_fact_and_single_url():
    fact, urls = parse_finding_line("- Stax used a converted theater :: https://a.example/x")
    assert fact == "Stax used a converted theater"
    assert urls == ["https://a.example/x"]


def test_parse_line_pulls_multiple_urls():
    fact, urls = parse_finding_line(
        "- The floor was never leveled :: https://a.example/x, https://b.example/y"
    )
    assert fact == "The floor was never leveled"
    assert urls == ["https://a.example/x", "https://b.example/y"]


def test_parse_line_accepts_asterisk_bullets():
    assert parse_finding_line("* A fact :: https://a.example/x") is not None


def test_parse_line_strips_a_trailing_period_from_the_url():
    _, urls = parse_finding_line("- A fact :: https://a.example/x.")
    assert urls == ["https://a.example/x"]


def test_parse_line_rejects_a_line_with_no_separator():
    assert parse_finding_line("- Just a sentence with no sources") is None


def test_parse_line_rejects_a_line_with_no_urls():
    assert parse_finding_line("- A fact :: see the museum website") is None


def test_parse_line_rejects_a_non_bullet():
    assert parse_finding_line("A fact :: https://a.example/x") is None


def test_parse_line_rejects_an_empty_fact():
    assert parse_finding_line("-  :: https://a.example/x") is None


def test_findings_hydrate_title_and_excerpt_from_the_ledger():
    prose = f"- Stax used the old Capitol Theatre :: {STAX['url']}"
    doc = parse_findings(prose, Category.SETTING, make_ledger())

    assert len(doc.findings) == 1
    citation = doc.findings[0].citations[0]
    assert citation.title == "Stax Museum — History"
    assert citation.excerpt == "The old Capitol Theatre floor still raked downward."
    assert doc.category == Category.SETTING


def test_findings_flag_a_url_absent_from_the_ledger():
    prose = "- An invented fact :: https://nowhere.example/invented"
    doc = parse_findings(prose, Category.SETTING, make_ledger())

    assert doc.findings[0].citations == []
    assert doc.findings[0].unverified_urls == ["https://nowhere.example/invented"]
    assert doc.unverified_count == 1


def test_findings_keep_verified_citations_alongside_an_unverified_one():
    prose = f"- Mixed sourcing :: {STAX['url']}, https://nowhere.example/invented"
    doc = parse_findings(prose, Category.SETTING, make_ledger())

    assert len(doc.findings[0].citations) == 1
    assert doc.findings[0].unverified_urls == ["https://nowhere.example/invented"]
    assert doc.unverified_count == 1


def test_unparsed_bullets_become_field_notes_and_lower_the_parse_rate():
    prose = (
        f"- A good finding :: {STAX['url']}\n"
        "- A bullet with no sources at all\n"
    )
    doc = parse_findings(prose, Category.SETTING, make_ledger())

    assert len(doc.findings) == 1
    assert "A bullet with no sources at all" in doc.field_notes
    assert doc.parse_rate == 0.5


def test_prose_paragraphs_do_not_count_against_the_parse_rate():
    prose = (
        "## Setting findings\n"
        "\n"
        f"- A good finding :: {STAX['url']}\n"
        "\n"
        "I could not establish the exact opening date; sources conflict.\n"
    )
    doc = parse_findings(prose, Category.SETTING, make_ledger())

    assert doc.parse_rate == 1.0
    assert "sources conflict" in doc.field_notes


def test_raw_prose_is_preserved_verbatim():
    prose = f"## Header\n- A good finding :: {STAX['url']}\ntrailing note"
    doc = parse_findings(prose, Category.SETTING, make_ledger())

    assert doc.markdown == prose


def test_empty_prose_yields_an_empty_doc_with_zero_parse_rate():
    doc = parse_findings("", Category.LOGISTICS, make_ledger())

    assert doc.findings == []
    assert doc.parse_rate == 0.0
    assert doc.unverified_count == 0
    assert doc.category == Category.LOGISTICS


def test_none_prose_is_treated_as_empty():
    doc = parse_findings(None, Category.FORCES_CONFLICTS, make_ledger())
    assert doc.findings == []
