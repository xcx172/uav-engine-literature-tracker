"""OpenAlex Works search, normalization and abstract reconstruction."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .config import Settings
from .http import request_json

API_URL = "https://api.openalex.org/works"
MAX_PER_QUERY = 20


def build_params(query: str, start: date, end: date, api_key: str, limit: int = MAX_PER_QUERY) -> dict[str, Any]:
    """Wire parameters agreed for round 3.

    The request sends ``search.title_and_abstract`` and ``per_page`` exactly as
    approved; dates stay in ``filter`` and results are newest first.
    """
    return {
        "search.title_and_abstract": query,
        "filter": (
            f"from_publication_date:{start.isoformat()},"
            f"to_publication_date:{end.isoformat()}"
        ),
        "per_page": limit,
        "sort": "publication_date:desc",
        "api_key": api_key,
    }


def search_works(
    settings: Settings,
    query: str,
    start: date,
    end: date,
    session: Any,
    *,
    limit: int = MAX_PER_QUERY,
) -> list[dict[str, Any]]:
    payload = request_json(
        session,
        "GET",
        API_URL,
        service="openalex",
        params=build_params(query, start, end, settings.openalex_key or "", limit),
        timeout=settings.timeout,
        attempts=3,
    )
    results = payload.get("results") or []
    if not isinstance(results, list):
        return []
    return results[:limit]


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    text = text.strip().strip(".,;")
    return text or None


def work_id_from(raw: dict[str, Any]) -> str | None:
    raw_id = str(raw.get("id") or "").rstrip("/")
    if not raw_id:
        return None
    candidate = raw_id.rsplit("/", 1)[-1]
    return candidate or None


def rebuild_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in index.items():
        for position in idxs or []:
            positions[int(position)] = word
    if not positions:
        return None
    size = max(positions)
    text = " ".join(positions.get(i, "") for i in range(size + 1)).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def _parse_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def normalize_work(raw: dict[str, Any], query_tag: str) -> dict[str, Any] | None:
    work_id = work_id_from(raw)
    if not work_id:
        return None
    title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip()
    if not title:
        return None
    doi = (str(raw.get("doi")).strip() if raw.get("doi") else None)
    doi_norm = normalize_doi(doi)
    abstract = rebuild_abstract(raw.get("abstract_inverted_index"))
    publication_date = _parse_date(raw.get("publication_date"))
    location = raw.get("primary_location") or {}
    landing_url = location.get("landing_page_url") if isinstance(location, dict) else None
    openalex_url = f"https://openalex.org/{work_id}"
    doi_url = f"https://doi.org/{doi_norm}" if doi_norm else None
    query_tags = [query_tag]
    incoming_tags = raw.get("_query_tags")
    if isinstance(incoming_tags, list):
        query_tags = sorted({*query_tags, *[str(t) for t in incoming_tags]})
    return {
        "work_id": work_id,
        "doi": doi,
        "doi_norm": doi_norm,
        "title": title,
        "abstract": abstract,
        "publication_date": publication_date,
        "date_unknown": 1 if publication_date is None else 0,
        "landing_url": landing_url,
        "doi_url": doi_url,
        "openalex_url": openalex_url,
        "query_tags": query_tags,
    }
