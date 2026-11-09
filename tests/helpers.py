"""Shared offline helpers: fake HTTP session and synthetic records."""

from __future__ import annotations

import json

from src.config import Settings


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Returns queued responses and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("FakeSession ran out of responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def openalex_page(records):
    return FakeResponse(200, {"results": records})


def deepseek_json(payload: dict, finish_reason: str = "stop"):
    return FakeResponse(
        200,
        {
            "choices": [
                {
                    "message": {"content": json.dumps(payload, ensure_ascii=False)},
                    "finish_reason": finish_reason,
                }
            ]
        },
    )


def synthetic_payload(**overrides):
    payload = {
        "contribution_zh": "提出一种转速调节方法。",
        "methods": ["PI controller"],
        "datasets": [],
        "code_open": None,
        "code_evidence": None,
    }
    payload.update(overrides)
    return payload


def raw_work(
    work_id: str,
    title: str,
    abstract: str | None,
    publication_date: str | None = "2026-10-01",
    doi: str | None = None,
    landing: str | None = None,
):
    index = None
    if abstract:
        index = {}
        for position, word in enumerate(abstract.split()):
            index.setdefault(word, []).append(position)
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "title": title,
        "abstract_inverted_index": index,
        "publication_date": publication_date,
        "primary_location": {"landing_page_url": landing},
    }


def make_settings(tmp_path) -> Settings:
    return Settings(
        openalex_key="test-openalex-key",
        deepseek_key="test-deepseek-key",
        model="deepseek-flash",
        db_path=tmp_path / "tracker.sqlite3",
        timeout=5.0,
    )
