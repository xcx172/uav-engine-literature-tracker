from __future__ import annotations

from datetime import date

import pytest

from src.errors import ErrorType, TrackerError
from src.openalex import build_params, rebuild_abstract, search_works
from tests.helpers import FakeResponse, FakeSession, openalex_page


def test_build_params_sends_agreed_wire_names():
    params = build_params("two-stroke AND governor", date(2025, 11, 8), date(2026, 11, 7), "k")
    assert params["search.title_and_abstract"] == "two-stroke AND governor"
    assert params["filter"] == (
        "from_publication_date:2025-11-08,to_publication_date:2026-11-07"
    )
    assert params["per_page"] == 20
    assert params["sort"] == "publication_date:desc"


def test_rebuild_abstract_orders_words():
    assert rebuild_abstract({"b": [1], "a": [0]}) == "a b"
    assert rebuild_abstract({"a": []}) is None
    assert rebuild_abstract(None) is None


def test_http_400_is_group_error_without_retry(settings):
    session = FakeSession([FakeResponse(400, {"error": "bad"})])
    with pytest.raises(TrackerError) as excinfo:
        search_works(settings, "q", date(2025, 11, 8), date(2026, 11, 7), session)
    assert excinfo.value.kind is ErrorType.PARAM_INVALID
    assert len(session.calls) == 1


def test_results_are_truncated_to_20(settings):
    records = [
        {"id": f"https://openalex.org/W{i}", "title": "t", "abstract_inverted_index": {"a": [0]}}
        for i in range(25)
    ]
    session = FakeSession([openalex_page(records)])
    result = search_works(settings, "q", date(2025, 11, 8), date(2026, 11, 7), session)
    assert len(result) == 20


def test_search_sends_approved_params(settings):
    session = FakeSession([openalex_page([])])
    search_works(settings, "governor query", date(2025, 11, 8), date(2026, 11, 7), session)
    params = session.calls[0]["params"]
    assert params["search.title_and_abstract"] == "governor query"
    assert params["per_page"] == 20
    assert params["filter"].startswith("from_publication_date:")
    assert params["sort"] == "publication_date:desc"
