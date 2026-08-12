"""A build that fails still charges, so it has to say what it charged.

THE BUG, in three places at once. `_daily_cap.check()` increments on the ALLOW
path, and the live searches a run makes are spent the moment they are made.
Neither is refunded when the build then dies. But:

  1. `_persist` handed `room_to_document` `run.get("result")`, which is `None`
     for a failed run, so the stored document recorded `search_count: 0` for a
     room that really spent a dozen searches and a day's build. The department
     charged and then filed a document saying it had done nothing.
  2. `_read_room`'s live branch answered `result: null` for a terminal run with
     no result, so the one window where a caller is most likely to ask what
     happened — seconds after the failure, while the run is still in memory —
     was the window where nothing could tell them.
  3. `_room_report` described the failure and stopped, so an agent reading it
     learned that the build failed and not that retrying costs the same again.

The three are one defect: the app was charging silently. These tests hold each
half of it. The copy assertions are deliberately about the FACTS in the
sentence (a count, "not refunded", "daily") and not its wording, so a rewrite
in the department's voice is free and a rewrite that drops the fact is not.
"""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from star import server, store
from star.ledger import SourceLedger
from star.mcp import tools

AUTH = {"Authorization": "Bearer t"}


def test_document_records_spend_when_the_run_has_no_result():
    """The stored document carries what the RUN cost, not what a result says."""
    doc = store.room_to_document(
        "run-1",
        None,
        "error",
        "2026-08-11T00:00:00Z",
        spent={"search_count": 12, "source_count": 40},
    )

    assert doc["search_count"] == 12
    assert doc["source_count"] == 40


def test_a_result_that_carries_its_own_counts_still_wins_when_nothing_is_spent():
    """`spent` is additive, not a replacement: complete rooms keep working."""
    doc = store.room_to_document(
        "run-2",
        {"search_count": 7, "source_count": 3},
        "complete",
        "2026-08-11T00:00:00Z",
    )

    assert doc["search_count"] == 7
    assert doc["source_count"] == 3


@pytest.mark.parametrize("status", ["error", "interrupted"])
def test_a_failed_room_says_what_it_spent(status):
    report = tools._room_report(status, {"search_count": 12, "source_count": 40})

    assert "12" in report
    assert "40" in report
    assert "not refunded" in report
    assert "daily" in report


def test_a_failed_room_that_spent_nothing_says_nothing_about_spending():
    """No zero-count sentence. `It spent 0 live searches` is noise, and the
    room it describes did not cost anything to have failed."""
    report = tools._room_report("error", {"search_count": 0, "source_count": 0})

    assert "not refunded" not in report
    assert "0 live" not in report


def test_the_spend_line_survives_a_room_with_no_payload_at_all():
    """`result` is `None` on the paths this defect lives on. Reporting must not
    raise there, because the alternative to a spend sentence is a 500."""
    assert tools._spend_line(None) == ""
    assert "failed" in tools._room_report("error", None)


def test_no_sources_no_source_clause():
    """A build that failed before anything came back should not claim sources."""
    line = tools._spend_line({"search_count": 3, "source_count": 0})

    assert "3 live searches" in line
    assert "source" not in line


def test_one_search_is_not_pluralised():
    line = tools._spend_line({"search_count": 1, "source_count": 1})

    assert "1 live search " in line
    assert "1 source " in line


def _live_run(status: str, searches: int) -> dict:
    """A run in memory that died before it built a result. This is the exact
    shape `_run_pipeline` leaves behind on the failure path: counts on the run,
    nothing under `result`."""
    return {
        "events": [],
        "status": status,
        "search_count": searches,
        "ledger": SourceLedger(),
        "result": None,
        "uid": "uid-one",
        "created_at": "2026-08-11T00:00:00Z",
    }


def test_a_live_run_that_failed_reports_its_spend_before_it_is_evicted():
    """The window that mattered most and reported least: the run is still in
    memory, the caller has just been told the build failed, and it asks why."""
    client = TestClient(server.app)
    server._runs["hot"] = _live_run("error", 12)
    try:
        with mock.patch("star.server.verify_token", return_value="uid-one"):
            body = client.get("/api/rooms/hot", headers=AUTH).json()
    finally:
        del server._runs["hot"]

    assert body["status"] == "error"
    assert body["result"]["search_count"] == 12


def test_a_run_still_going_answers_null_the_way_both_doors_expect():
    """`result: null` while running is a contract, not an oversight — the web
    app's room view branches on it. The spend answer must not reach into it."""
    client = TestClient(server.app)
    server._runs["warm"] = _live_run("running", 4)
    try:
        with mock.patch("star.server.verify_token", return_value="uid-one"):
            body = client.get("/api/rooms/warm", headers=AUTH).json()
    finally:
        del server._runs["warm"]

    assert body["status"] == "running"
    assert body["result"] is None
