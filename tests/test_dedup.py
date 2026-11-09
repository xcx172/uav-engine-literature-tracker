from __future__ import annotations

from src import store
from src.openalex import normalize_doi


def make_record(work_id: str, doi: str | None = None, title: str = "Title") -> dict:
    return {
        "work_id": work_id,
        "doi": doi,
        "doi_norm": normalize_doi(doi),
        "title": title,
        "abstract": "A two-stroke engine speed regulation.",
        "publication_date": "2026-10-01",
        "date_unknown": 0,
        "landing_url": None,
        "doi_url": None,
        "openalex_url": f"https://openalex.org/{work_id}",
        "query_tags": ["direct"],
    }


def test_doi_normalization():
    assert normalize_doi("https://doi.org/10.1000/ABC.") == "10.1000/abc"
    assert normalize_doi("doi: 10.1000/xyz") == "10.1000/xyz"
    assert normalize_doi(None) is None


def test_same_work_is_idempotent(tmp_path):
    conn = store.init_db(tmp_path / "db.sqlite3")
    first = store.upsert_paper(
        conn, make_record("W1"), category="direct", reason="step4", extraction_status="pending", run_id="r1"
    )
    second = store.upsert_paper(
        conn, make_record("W1"), category="direct", reason="step4", extraction_status="pending", run_id="r2"
    )
    assert first[2] is True
    assert second[2] is False
    assert conn.execute("SELECT COUNT(*) AS n FROM paper").fetchone()["n"] == 1


def test_doi_late_merge_keeps_earlier_record(tmp_path):
    conn = store.init_db(tmp_path / "db.sqlite3")
    store.upsert_paper(conn, make_record("W1"), category="direct", reason="step4", extraction_status="pending", run_id="r1")
    store.upsert_paper(conn, make_record("W2", "10.1/x"), category="direct", reason="step4", extraction_status="pending", run_id="r1")

    kept, merged, is_new = store.upsert_paper(
        conn, make_record("W1", "10.1/x"), category="direct", reason="step4", extraction_status="pending", run_id="r2"
    )

    assert merged == 1
    assert is_new is False
    rows = conn.execute("SELECT work_id, doi_norm FROM paper").fetchall()
    assert len(rows) == 1
    assert rows[0]["work_id"] == "W1"
    assert rows[0]["doi_norm"] == "10.1/x"


def test_failed_merge_rolls_back(tmp_path):
    import sqlite3

    import pytest

    conn = store.init_db(tmp_path / "db.sqlite3")
    store.upsert_paper(conn, make_record("W1"), category="direct", reason="step4", extraction_status="pending", run_id="r1")
    store.upsert_paper(conn, make_record("W2", "10.1/x"), category="direct", reason="step4", extraction_status="pending", run_id="r1")

    broken = make_record("W1", "10.1/x")
    broken["title"] = None
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_paper(conn, broken, category="direct", reason="step4", extraction_status="pending", run_id="r2")

    assert conn.execute("SELECT COUNT(*) AS n FROM paper").fetchone()["n"] == 2
