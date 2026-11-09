from __future__ import annotations

from datetime import date

import pytest

from src.refresh import compute_window, run_refresh
from tests.helpers import FakeSession, openalex_page, raw_work


def test_default_window_is_inclusive():
    window = compute_window(365, date(2026, 11, 7))
    assert window.start == date(2025, 11, 8)
    assert window.end == date(2026, 11, 7)
    assert window.days == 365


def test_single_day_window():
    window = compute_window(1, date(2026, 11, 7))
    assert window.start == window.end == date(2026, 11, 7)


@pytest.mark.parametrize("days", [0, -1, 3651, 3.5, True])
def test_invalid_days(days):
    with pytest.raises(ValueError):
        compute_window(days, date(2026, 11, 7))


def test_date_unknown_is_saved_but_not_queued(settings):
    record = raw_work(
        "W1",
        "Two-stroke engine speed regulation",
        "A two-stroke engine speed regulation method is proposed.",
        publication_date=None,
    )
    session = FakeSession([openalex_page([record]), openalex_page([]), openalex_page([])])
    result = run_refresh(settings, days=365, today=date(2026, 11, 7), session=session)

    assert result.status == "ok"
    assert result.hit_count == 1
    assert result.date_unknown_count == 1
    assert result.queue_count == 0
    assert len(session.calls) == 3  # no DeepSeek call


def test_future_date_is_skipped(settings):
    record = raw_work(
        "W1",
        "Aircraft two-stroke piston engine speed regulation",
        "An aircraft two-stroke piston engine speed regulation is studied.",
        publication_date="2026-11-08",
    )
    session = FakeSession([openalex_page([record]), openalex_page([]), openalex_page([])])
    result = run_refresh(settings, days=365, today=date(2026, 11, 7), session=session)

    assert result.hit_count == 0
    assert result.status == "ok"
