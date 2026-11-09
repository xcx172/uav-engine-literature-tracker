from __future__ import annotations

from src import store


def record(work_id: str, *, date: str | None = "2026-10-01", abstract: str | None = "a", doi: str | None = None):
    return {
        "work_id": work_id,
        "doi": doi,
        "doi_norm": doi,
        "title": f"Title {work_id}",
        "abstract": abstract,
        "publication_date": date,
        "date_unknown": 1 if date is None else 0,
        "landing_url": None,
        "doi_url": None,
        "openalex_url": f"https://openalex.org/{work_id}",
        "query_tags": ["direct"],
    }


def test_init_creates_four_tables(tmp_path):
    conn = store.init_db(tmp_path / "db.sqlite3")
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"paper", "run", "run_hit", "meta"} <= names


def test_select_queue_skips_special_records(tmp_path):
    conn = store.init_db(tmp_path / "db.sqlite3")
    store.upsert_paper(conn, record("W1"), category="direct", reason="seed", extraction_status="pending", run_id="r")
    store.upsert_paper(
        conn, record("W2", abstract=None), category="unclassified", reason="missing", extraction_status="missing_abstract", run_id="r"
    )
    store.upsert_paper(
        conn, record("W3", date=None), category="unclassified", reason="unknown", extraction_status="pending", run_id="r"
    )

    queue = store.select_queue(conn, "2025-11-08", "2026-11-07", "extract-v1", 20)
    assert [row["work_id"] for row in queue] == ["W1"]


def test_run_hit_round_trip(tmp_path):
    conn = store.init_db(tmp_path / "db.sqlite3")
    store.upsert_paper(conn, record("W1"), category="direct", reason="seed", extraction_status="pending", run_id="r1")
    store.save_run(
        conn,
        {
            "run_id": "r1",
            "started_at": "2026-11-07T10:00:00+00:00",
            "finished_at": "2026-11-07T10:00:01+00:00",
            "days": 365,
            "window_start": "2025-11-08",
            "window_end": "2026-11-07",
            "status": "ok",
        },
    )
    store.save_run_hits(conn, "r1", [("W1", "direct", True)])

    hits = store.papers_for_run(conn, "r1")
    assert len(hits) == 1
    assert hits[0]["run_category"] == "direct"
    assert store.latest_run(conn)["run_id"] == "r1"


def test_current_and_history_are_separated(tmp_path):
    conn = store.init_db(tmp_path / "db.sqlite3")
    store.upsert_paper(conn, record("W1"), category="direct", reason="seed", extraction_status="pending", run_id="r1")
    store.upsert_paper(conn, record("W2"), category="direct", reason="seed", extraction_status="pending", run_id="r2")
    for run_id, started in (("r1", "2026-11-07T10:00:00+00:00"), ("r2", "2026-11-07T11:00:00+00:00")):
        store.save_run(
            conn,
            {
                "run_id": run_id,
                "started_at": started,
                "finished_at": started,
                "days": 365,
                "window_start": "2025-11-08",
                "window_end": "2026-11-07",
                "status": "ok",
            },
        )
    store.save_run_hits(conn, "r1", [("W1", "direct", True)])
    store.save_run_hits(conn, "r2", [("W2", "direct", False)])

    latest, current, history = store.current_and_history(conn)
    assert latest["run_id"] == "r2"
    assert [row["work_id"] for row in current] == ["W2"]
    assert [row["work_id"] for row in history] == ["W1"]
