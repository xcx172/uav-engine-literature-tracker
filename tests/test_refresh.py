from __future__ import annotations

from datetime import date

from src import store
from src.config import Settings
from src.refresh import run_refresh
from tests.helpers import FakeResponse, FakeSession, deepseek_json, openalex_page, raw_work, synthetic_payload

TODAY = date(2026, 11, 7)
EMPTY = openalex_page([])


def seed(settings: Settings, work_id: str, publication_date: str = "2026-10-01") -> None:
    conn = store.init_db(settings.db_path)
    record = {
        "work_id": work_id,
        "doi": None,
        "doi_norm": None,
        "title": f"Two-stroke engine speed regulation {work_id}",
        "abstract": "A two-stroke engine speed regulation method is proposed.",
        "publication_date": publication_date,
        "date_unknown": 0,
        "landing_url": None,
        "doi_url": None,
        "openalex_url": f"https://openalex.org/{work_id}",
        "query_tags": ["direct"],
    }
    store.upsert_paper(
        conn, record, category="direct", reason="seed", extraction_status="pending", run_id="seed"
    )


def test_ok_run_hits_and_extracts(settings):
    record = raw_work(
        "W1",
        "Aircraft two-stroke piston engine speed regulation",
        "An aircraft two-stroke piston engine speed regulation method is proposed.",
    )
    session = FakeSession(
        [openalex_page([record]), EMPTY, EMPTY, deepseek_json(synthetic_payload())]
    )
    result = run_refresh(settings, days=365, today=TODAY, session=session)

    assert result.status == "ok"
    assert result.hit_count == 1
    assert result.direct_count == 1
    assert result.extracted_count == 1
    assert result.queue_count == 1


def test_partial_when_one_query_fails(settings):
    record = raw_work(
        "W1",
        "Aircraft two-stroke piston engine speed regulation",
        "An aircraft two-stroke piston engine speed regulation method is proposed.",
    )
    session = FakeSession(
        [openalex_page([record]), FakeResponse(400, {}), EMPTY, deepseek_json(synthetic_payload())]
    )
    result = run_refresh(settings, days=365, today=TODAY, session=session)

    assert result.status == "partial"
    assert result.queries_ok == 2
    assert result.hit_count == 1


def test_zero_hits_is_success(settings):
    result = run_refresh(
        settings, days=365, today=TODAY, session=FakeSession([EMPTY, EMPTY, EMPTY])
    )
    assert result.status == "ok"
    assert result.hit_count == 0


def test_auth_error_stops_later_extractions(settings):
    seed(settings, "W-new", "2026-10-02")
    seed(settings, "W-old", "2026-10-01")
    session = FakeSession([EMPTY, EMPTY, EMPTY, FakeResponse(401, {})])
    result = run_refresh(settings, days=365, today=TODAY, session=session)

    assert result.failed_count == 1
    assert result.status == "partial"
    assert len(session.calls) == 4  # three queries + one DeepSeek attempt


def test_25_pending_extracts_20_and_defers_5(settings):
    for index in range(25):
        seed(settings, f"W{index:02d}")
    session = FakeSession([EMPTY, EMPTY, EMPTY] + [deepseek_json(synthetic_payload()) for _ in range(20)])
    result = run_refresh(settings, days=365, max_summaries=20, today=TODAY, session=session)

    assert result.queue_count == 20
    assert result.extracted_count == 20
    assert result.deferred_count == 5


def test_next_run_resumes_deferred_from_database(settings):
    seed(settings, "W-new", "2026-10-02")
    seed(settings, "W-old", "2026-10-01")

    first = run_refresh(
        settings,
        days=365,
        max_summaries=1,
        today=TODAY,
        session=FakeSession([EMPTY, EMPTY, EMPTY, deepseek_json(synthetic_payload())]),
    )
    assert first.extracted_count == 1

    second = run_refresh(
        settings,
        days=365,
        max_summaries=1,
        today=TODAY,
        session=FakeSession([EMPTY, EMPTY, EMPTY, deepseek_json(synthetic_payload())]),
    )
    assert second.hit_count == 0
    assert second.extracted_count == 1


def test_missing_keys_fail_before_any_request(tmp_path):
    settings = Settings(
        openalex_key=None,
        deepseek_key=None,
        model="deepseek-flash",
        db_path=tmp_path / "db.sqlite3",
    )
    session = FakeSession([])
    result = run_refresh(settings, days=365, today=TODAY, session=session)

    assert result.status == "failed"
    assert set(result.missing) == {"OPENALEX_API_KEY", "DEEPSEEK_API_KEY"}
    assert session.calls == []
