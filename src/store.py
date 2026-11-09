"""SQLite persistence: papers, runs, per-run hits, metadata."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper (
    work_id            TEXT PRIMARY KEY,
    doi                TEXT,
    doi_norm           TEXT UNIQUE,
    title              TEXT NOT NULL,
    abstract           TEXT,
    abstract_hash      TEXT,
    publication_date   TEXT,
    date_unknown       INTEGER NOT NULL DEFAULT 0,
    landing_url        TEXT,
    doi_url            TEXT,
    openalex_url       TEXT,
    query_tags         TEXT NOT NULL DEFAULT '[]',
    category           TEXT NOT NULL DEFAULT 'unclassified' CHECK (category IN
                         ('direct','near_aircraft','near_two_stroke','excluded','unclassified')),
    category_reason    TEXT,
    extraction_status  TEXT NOT NULL DEFAULT 'pending' CHECK (extraction_status IN
                         ('pending','ok','missing_abstract','deferred','failed')),
    contribution_zh    TEXT,
    methods_json       TEXT NOT NULL DEFAULT '[]',
    datasets_json      TEXT NOT NULL DEFAULT '[]',
    code_open          TEXT CHECK (code_open IN ('Yes','No') OR code_open IS NULL),
    code_evidence      TEXT,
    prompt_version     TEXT,
    input_hash         TEXT,
    rule_version       TEXT NOT NULL DEFAULT 'rule-v1',
    first_seen_at      TEXT NOT NULL,
    last_seen_at       TEXT NOT NULL,
    last_run_id        TEXT
);

CREATE TABLE IF NOT EXISTS run (
    run_id                 TEXT PRIMARY KEY,
    started_at             TEXT NOT NULL,
    finished_at            TEXT,
    days                   INTEGER NOT NULL,
    window_start           TEXT NOT NULL,
    window_end             TEXT NOT NULL,
    status                 TEXT NOT NULL CHECK (status IN ('ok','partial','failed')),
    queries_ok             INTEGER NOT NULL DEFAULT 0,
    queries_total          INTEGER NOT NULL DEFAULT 3,
    hit_count              INTEGER NOT NULL DEFAULT 0,
    queue_count            INTEGER NOT NULL DEFAULT 0,
    direct_count           INTEGER NOT NULL DEFAULT 0,
    near_aircraft_count    INTEGER NOT NULL DEFAULT 0,
    near_two_stroke_count  INTEGER NOT NULL DEFAULT 0,
    excluded_count         INTEGER NOT NULL DEFAULT 0,
    missing_abstract_count INTEGER NOT NULL DEFAULT 0,
    date_unknown_count     INTEGER NOT NULL DEFAULT 0,
    extracted_count        INTEGER NOT NULL DEFAULT 0,
    failed_count           INTEGER NOT NULL DEFAULT 0,
    deferred_count         INTEGER NOT NULL DEFAULT 0,
    merged_count           INTEGER NOT NULL DEFAULT 0,
    error_summary          TEXT
);

CREATE TABLE IF NOT EXISTS run_hit (
    run_id     TEXT NOT NULL,
    work_id    TEXT NOT NULL,
    category   TEXT NOT NULL,
    is_new     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, work_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
    conn.commit()
    return conn


def _row_by_work(conn: sqlite3.Connection, work_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM paper WHERE work_id=?", (work_id,)).fetchone()


def _row_by_doi(conn: sqlite3.Connection, doi_norm: str | None) -> sqlite3.Row | None:
    if not doi_norm:
        return None
    return conn.execute("SELECT * FROM paper WHERE doi_norm=?", (doi_norm,)).fetchone()


def _parse_tags(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _merge_rows(conn: sqlite3.Connection, primary: sqlite3.Row, secondary: sqlite3.Row) -> str:
    """Merge ``secondary`` into ``primary`` in the current transaction."""
    tags = sorted({*_parse_tags(primary["query_tags"]), *_parse_tags(secondary["query_tags"])})
    abstract = primary["abstract"] or secondary["abstract"]
    fields = {
        "doi": primary["doi"] or secondary["doi"],
        "doi_norm": primary["doi_norm"] or secondary["doi_norm"],
        "abstract": abstract,
        "abstract_hash": primary["abstract_hash"] or secondary["abstract_hash"],
        "publication_date": primary["publication_date"] or secondary["publication_date"],
        "date_unknown": 0 if (primary["publication_date"] or secondary["publication_date"]) else 1,
        "landing_url": primary["landing_url"] or secondary["landing_url"],
        "doi_url": primary["doi_url"] or secondary["doi_url"],
        "openalex_url": primary["openalex_url"] or secondary["openalex_url"],
        "query_tags": json.dumps(tags, ensure_ascii=False),
        "first_seen_at": min(primary["first_seen_at"], secondary["first_seen_at"]),
        "last_seen_at": max(primary["last_seen_at"], secondary["last_seen_at"]),
    }
    if primary["extraction_status"] != "ok" and secondary["extraction_status"] == "ok":
        for key in (
            "category", "category_reason", "extraction_status", "contribution_zh",
            "methods_json", "datasets_json", "code_open", "code_evidence",
            "prompt_version", "input_hash",
        ):
            fields[key] = secondary[key]
    assignments = ", ".join(f"{key}=?" for key in fields)
    conn.execute("DELETE FROM paper WHERE work_id=?", (secondary["work_id"],))
    conn.execute(
        f"UPDATE paper SET {assignments} WHERE work_id=?",
        (*fields.values(), primary["work_id"]),
    )
    return primary["work_id"]


def _order_for_merge(left: sqlite3.Row, right: sqlite3.Row) -> tuple[sqlite3.Row, sqlite3.Row]:
    left_key = (left["first_seen_at"], left["work_id"])
    right_key = (right["first_seen_at"], right["work_id"])
    return (left, right) if left_key <= right_key else (right, left)


def upsert_paper(
    conn: sqlite3.Connection,
    record: dict[str, Any],
    *,
    category: str,
    reason: str,
    extraction_status: str,
    run_id: str,
) -> tuple[str, int, bool]:
    """Insert/update one paper. Returns (work_id, merged_count, is_new)."""
    now = utcnow()
    work_id = record["work_id"]
    by_work = _row_by_work(conn, work_id)
    by_doi = _row_by_doi(conn, record.get("doi_norm"))

    merged = 0
    target: sqlite3.Row | None
    with conn:
        if by_work and by_doi and by_work["work_id"] != by_doi["work_id"]:
            primary, secondary = _order_for_merge(by_work, by_doi)
            target_id = _merge_rows(conn, primary, secondary)
            merged = 1
            target = _row_by_work(conn, target_id)
        elif by_work:
            target = by_work
        elif by_doi:
            target = by_doi
        else:
            target = None

        if target is None:
            conn.execute(
                """
                INSERT INTO paper (
                    work_id, doi, doi_norm, title, abstract, abstract_hash,
                    publication_date, date_unknown, landing_url, doi_url, openalex_url,
                    query_tags, category, category_reason, extraction_status,
                    rule_version, first_seen_at, last_seen_at, last_run_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    work_id, record.get("doi"), record.get("doi_norm"), record["title"],
                    record.get("abstract"), _abstract_hash(record.get("abstract")),
                    record.get("publication_date"), int(record.get("date_unknown", 0)),
                    record.get("landing_url"), record.get("doi_url"), record.get("openalex_url"),
                    json.dumps(record.get("query_tags", []), ensure_ascii=False),
                    category, reason, extraction_status, "rule-v1", now, now, run_id,
                ),
            )
            return work_id, merged, True

        existing = target
        tags = sorted({*_parse_tags(existing["query_tags"]), *record.get("query_tags", [])})
        abstract = record.get("abstract")
        abstract_changed = abstract is not None and abstract != existing["abstract"]
        fields: dict[str, Any] = {
            "title": record["title"],
            "query_tags": json.dumps(tags, ensure_ascii=False),
            "category": category,
            "category_reason": reason,
            "last_seen_at": now,
            "last_run_id": run_id,
        }
        if record.get("doi"):
            fields["doi"] = record["doi"]
        if record.get("doi_norm"):
            fields["doi_norm"] = record["doi_norm"]
        if abstract is not None:
            fields["abstract"] = abstract
            fields["abstract_hash"] = _abstract_hash(abstract)
        if record.get("publication_date"):
            fields["publication_date"] = record["publication_date"]
            fields["date_unknown"] = 0
        for key in ("landing_url", "doi_url", "openalex_url"):
            if record.get(key):
                fields[key] = record[key]
        if abstract_changed and existing["extraction_status"] == "ok":
            fields["extraction_status"] = "pending"
            fields["input_hash"] = None
        elif existing["extraction_status"] in ("missing_abstract", "pending") and extraction_status:
            fields["extraction_status"] = extraction_status

        assignments = ", ".join(f"{key}=?" for key in fields)
        conn.execute(
            f"UPDATE paper SET {assignments} WHERE work_id=?",
            (*fields.values(), existing["work_id"]),
        )
        return existing["work_id"], merged, False


def _abstract_hash(abstract: str | None) -> str | None:
    if not abstract:
        return None
    import hashlib

    return hashlib.sha256(abstract.encode("utf-8")).hexdigest()


def select_queue(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    prompt_version: str,
    limit: int = 20,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM paper
        WHERE date_unknown=0
          AND publication_date IS NOT NULL
          AND publication_date BETWEEN ? AND ?
          AND category IN ('direct','near_aircraft','near_two_stroke')
          AND abstract IS NOT NULL AND abstract <> ''
          AND (
                extraction_status IN ('pending','deferred','failed')
                OR (extraction_status='ok' AND (prompt_version IS NULL OR prompt_version<>?))
              )
        ORDER BY publication_date DESC, work_id ASC
        LIMIT ?
        """,
        (start, end, prompt_version, limit),
    ).fetchall()


def count_queue(conn: sqlite3.Connection, start: str, end: str, prompt_version: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM paper
        WHERE date_unknown=0
          AND publication_date IS NOT NULL
          AND publication_date BETWEEN ? AND ?
          AND category IN ('direct','near_aircraft','near_two_stroke')
          AND abstract IS NOT NULL AND abstract <> ''
          AND (
                extraction_status IN ('pending','deferred','failed')
                OR (extraction_status='ok' AND (prompt_version IS NULL OR prompt_version<>?))
              )
        """,
        (start, end, prompt_version),
    ).fetchone()
    return int(row["n"]) if row else 0


def save_extraction(conn: sqlite3.Connection, work_id: str, extracted: Any, digest: str) -> None:
    with conn:
        conn.execute(
            """
            UPDATE paper SET
                extraction_status='ok',
                contribution_zh=?,
                methods_json=?,
                datasets_json=?,
                code_open=?,
                code_evidence=?,
                prompt_version=?,
                input_hash=?
            WHERE work_id=?
            """,
            (
                extracted.contribution_zh,
                json.dumps(extracted.methods, ensure_ascii=False),
                json.dumps(extracted.datasets, ensure_ascii=False),
                extracted.code_open,
                extracted.code_evidence,
                extracted.prompt_version,
                digest,
                work_id,
            ),
        )


def mark_status(conn: sqlite3.Connection, work_id: str, status: str) -> None:
    with conn:
        conn.execute("UPDATE paper SET extraction_status=? WHERE work_id=?", (status, work_id))


def save_run(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    with conn:
        conn.execute(f"INSERT INTO run ({columns}) VALUES ({placeholders})", tuple(row.values()))


def save_run_hits(conn: sqlite3.Connection, run_id: str, hits: Iterable[tuple[str, str, bool]]) -> None:
    rows = [(run_id, work_id, category, 1 if is_new else 0) for work_id, category, is_new in hits]
    if not rows:
        return
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO run_hit(run_id, work_id, category, is_new) VALUES (?,?,?,?)",
            rows,
        )


def latest_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM run ORDER BY started_at DESC LIMIT 1").fetchone()


def papers_for_run(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT p.*, h.category AS run_category, h.is_new
        FROM run_hit h JOIN paper p ON p.work_id = h.work_id
        WHERE h.run_id=?
        ORDER BY p.publication_date DESC, p.work_id ASC
        """,
        (run_id,),
    ).fetchall()


def current_and_history(
    conn: sqlite3.Connection,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row], list[sqlite3.Row]]:
    """Return (latest run, current hits, older cached papers)."""
    latest = latest_run(conn)
    if latest is None:
        return None, [], []
    current = papers_for_run(conn, latest["run_id"])
    history = conn.execute(
        """
        SELECT p.* FROM paper p
        JOIN run_hit h ON h.work_id = p.work_id
        WHERE h.run_id <> ?
          AND p.work_id NOT IN (SELECT work_id FROM run_hit WHERE run_id=?)
        GROUP BY p.work_id
        ORDER BY p.publication_date DESC, p.work_id ASC
        """,
        (latest["run_id"], latest["run_id"]),
    ).fetchall()
    return latest, current, history


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, value))


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None
