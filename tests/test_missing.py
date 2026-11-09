from __future__ import annotations

from datetime import date

from src import store
from src.refresh import run_refresh
from tests.helpers import FakeSession, deepseek_json, openalex_page, raw_work, synthetic_payload

START = date(2026, 11, 7)


def test_missing_abstract_is_saved_without_extraction(settings):
    record = raw_work(
        "W1",
        "Aircraft two-stroke piston engine speed regulation",
        None,
        publication_date="2026-10-01",
        doi="10.1/missing",
    )
    session = FakeSession([openalex_page([record]), openalex_page([]), openalex_page([])])
    result = run_refresh(settings, days=365, today=START, session=session)

    assert result.missing_abstract_count == 1
    assert result.queue_count == 0
    assert len(session.calls) == 3

    conn = store.init_db(settings.db_path)
    row = conn.execute("SELECT category, extraction_status FROM paper WHERE work_id='W1'").fetchone()
    assert row["category"] == "unclassified"
    assert row["extraction_status"] == "missing_abstract"


def test_short_abstract_with_content_is_classified_and_extracted(settings):
    record = raw_work(
        "W1",
        "Two-stroke engine speed regulation",
        "A two-stroke engine speed regulation method with a PI controller.",
    )
    session = FakeSession(
        [
            openalex_page([record]),
            openalex_page([]),
            openalex_page([]),
            deepseek_json(synthetic_payload()),
        ]
    )
    result = run_refresh(settings, days=365, today=START, session=session)

    assert result.near_two_stroke_count == 1
    assert result.extracted_count == 1
    assert result.queue_count == 1
