"""Refresh orchestration and CLI.

``run_refresh`` is the single entry point used by the page and the command
line. It never touches the network during tests: callers inject a session.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from .classify import classify_record
from .config import Settings
from .errors import ErrorType, TrackerError
from .extract import extract_fields, input_hash
from .openalex import normalize_work, search_works
from .prompts import PROMPT_VERSION, SEARCH_QUERIES
from . import store

MAX_SUMMARIES = 20
MAX_DAYS = 3650


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass
class RunResult:
    run_id: str
    status: str
    window: Window
    queries_ok: int = 0
    hit_count: int = 0
    queue_count: int = 0
    direct_count: int = 0
    near_aircraft_count: int = 0
    near_two_stroke_count: int = 0
    excluded_count: int = 0
    missing_abstract_count: int = 0
    date_unknown_count: int = 0
    extracted_count: int = 0
    failed_count: int = 0
    deferred_count: int = 0
    merged_count: int = 0
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def compute_window(days: int, today: date | None = None) -> Window:
    if not isinstance(days, int) or isinstance(days, bool):
        raise ValueError("days must be an integer")
    if not 1 <= days <= MAX_DAYS:
        raise ValueError("days must be between 1 and 3650")
    end = today or date.today()
    return Window(end - timedelta(days=days - 1), end)


def _new_run_id() -> str:
    return uuid.uuid4().hex


def run_refresh(
    settings: Settings,
    *,
    days: int = 365,
    max_summaries: int = MAX_SUMMARIES,
    mode: str = "online",
    session: Any | None = None,
    today: date | None = None,
    db_path: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> RunResult:
    if not isinstance(max_summaries, int) or isinstance(max_summaries, bool):
        raise ValueError("max_summaries must be an integer")
    if not 1 <= max_summaries <= MAX_SUMMARIES:
        raise ValueError("max_summaries must be between 1 and 20")

    window = compute_window(days, today)
    run_id = _new_run_id()

    missing = settings.validate(mode == "online")
    if missing:
        return RunResult(
            run_id=run_id,
            status="failed",
            window=window,
            missing=missing,
            errors=[f"CONFIG_MISSING service=config missing={'+'.join(missing)}"],
        )

    if session is None:
        import requests

        session = requests.Session()

    conn = store.init_db(db_path or settings.db_path)
    started = store.utcnow()

    def notify(message: str) -> None:
        if progress_cb is not None:
            progress_cb(message)

    hits: dict[str, tuple[str, bool]] = {}
    errors: list[str] = []
    queries_ok = 0
    merged_total = 0

    for name, query in SEARCH_QUERIES.items():
        notify(f"query {name}")
        try:
            raw_records = search_works(settings, query, window.start, window.end, session)
        except TrackerError as exc:
            errors.append(str(exc))
            continue
        queries_ok += 1
        for raw in raw_records:
            record = normalize_work(raw, name)
            if record is None:
                continue
            paper_date = record["publication_date"]
            if paper_date is None:
                category, reason, status = "unclassified", "date_unknown", "pending"
            else:
                parsed = date.fromisoformat(paper_date)
                if parsed < window.start or parsed > window.end:
                    continue
                if record["abstract"]:
                    result = classify_record(record["title"], record["abstract"])
                    category, reason = result.category, result.reason
                    status = "pending"
                else:
                    category, reason, status = "unclassified", "missing_abstract", "missing_abstract"
            target_id, merged, is_new = store.upsert_paper(
                conn,
                record,
                category=category,
                reason=reason,
                extraction_status=status,
                run_id=run_id,
            )
            merged_total += merged
            hits[target_id] = (category, is_new)

    queue = store.select_queue(conn, window.start_iso, window.end_iso, PROMPT_VERSION, max_summaries)
    queue_total = store.count_queue(conn, window.start_iso, window.end_iso, PROMPT_VERSION)

    extracted_count = 0
    failed_count = 0
    stop_deepseek = False
    for row in queue:
        notify(f"extract {row['work_id']}")
        if stop_deepseek:
            break
        try:
            digest = input_hash(row["title"], row["abstract"])
            if row["extraction_status"] == "ok" and row["input_hash"] == digest and row["prompt_version"] == PROMPT_VERSION:
                continue
            extracted = extract_fields(session, settings, row["title"], row["abstract"])
            store.save_extraction(conn, row["work_id"], extracted, digest)
            extracted_count += 1
        except TrackerError as exc:
            failed_count += 1
            errors.append(str(exc))
            store.mark_status(conn, row["work_id"], "failed")
            if exc.stop_service:
                stop_deepseek = True

    counts = {"direct": 0, "near_aircraft": 0, "near_two_stroke": 0, "excluded": 0}
    missing_abstract = 0
    date_unknown = 0
    for category, _ in hits.values():
        counts[category] = counts.get(category, 0) + 1
    for work_id, (category, _) in hits.items():
        row = conn.execute(
            "SELECT abstract, date_unknown FROM paper WHERE work_id=?", (work_id,)
        ).fetchone()
        if row is None:
            continue
        if row["date_unknown"]:
            date_unknown += 1
        elif row["abstract"] is None:
            missing_abstract += 1

    if queries_ok == 0:
        status = "failed"
    elif queries_ok < len(SEARCH_QUERIES) or failed_count > 0:
        status = "partial"
    else:
        status = "ok"

    deferred = max(0, queue_total - len(queue))
    run_row = {
        "run_id": run_id,
        "started_at": started,
        "finished_at": store.utcnow(),
        "days": window.days,
        "window_start": window.start_iso,
        "window_end": window.end_iso,
        "status": status,
        "queries_ok": queries_ok,
        "queries_total": len(SEARCH_QUERIES),
        "hit_count": len(hits),
        "queue_count": len(queue),
        "direct_count": counts.get("direct", 0),
        "near_aircraft_count": counts.get("near_aircraft", 0),
        "near_two_stroke_count": counts.get("near_two_stroke", 0),
        "excluded_count": counts.get("excluded", 0),
        "missing_abstract_count": missing_abstract,
        "date_unknown_count": date_unknown,
        "extracted_count": extracted_count,
        "failed_count": failed_count,
        "deferred_count": deferred,
        "merged_count": merged_total,
        "error_summary": "; ".join(errors)[:1000] or None,
    }
    store.save_run(conn, run_row)
    store.save_run_hits(conn, run_id, [(work_id, category, is_new) for work_id, (category, is_new) in hits.items()])
    if status in ("ok", "partial"):
        store.set_meta(conn, "last_success_at", run_row["finished_at"])

    return RunResult(
        run_id=run_id,
        status=status,
        window=window,
        queries_ok=queries_ok,
        hit_count=len(hits),
        queue_count=len(queue),
        direct_count=counts.get("direct", 0),
        near_aircraft_count=counts.get("near_aircraft", 0),
        near_two_stroke_count=counts.get("near_two_stroke", 0),
        excluded_count=counts.get("excluded", 0),
        missing_abstract_count=missing_abstract,
        date_unknown_count=date_unknown,
        extracted_count=extracted_count,
        failed_count=failed_count,
        deferred_count=deferred,
        merged_count=merged_total,
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the aviation engine literature tracker.")
    parser.add_argument("--days", type=int, default=365, help="publication window in days (1-3650)")
    parser.add_argument("--max-summaries", type=int, default=MAX_SUMMARIES, help="max extractions per run (1-20)")
    args = parser.parse_args(argv)

    settings = Settings.load()
    try:
        result = run_refresh(settings, days=args.days, max_summaries=args.max_summaries)
    except ValueError as exc:
        print(f"CONFIG_INVALID detail={exc}", file=sys.stderr)
        return 2

    print(
        f"status={result.status} window={result.window.start_iso}..{result.window.end_iso} "
        f"hits={result.hit_count} direct={result.direct_count} "
        f"near_aircraft={result.near_aircraft_count} near_two_stroke={result.near_two_stroke_count} "
        f"queue={result.queue_count} extracted={result.extracted_count} failed={result.failed_count}"
    )
    for message in result.errors[:5]:
        print(message, file=sys.stderr)
    return 0 if result.status in ("ok", "partial") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
