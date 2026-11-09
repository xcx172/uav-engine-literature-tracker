from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_env_example_contains_only_placeholders():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert lines == [
        "OPENALEX_API_KEY=your_openalex_key_here",
        "DEEPSEEK_API_KEY=your_deepseek_key_here",
        "DEEPSEEK_MODEL=deepseek-flash",
    ]
    assert "sk-" not in text


def test_gitignore_covers_secrets_and_caches():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", ".venv/", "__pycache__/", "*.sqlite", ".pytest_cache/"):
        assert pattern in text


def test_demo_data_covers_required_cases():
    records = json.loads((ROOT / "data" / "demo_papers.json").read_text(encoding="utf-8"))
    assert len(records) >= 6
    categories = {record["category"] for record in records}
    assert {"direct", "near_aircraft", "near_two_stroke"} <= categories
    assert {record.get("code_open") for record in records} >= {"Yes", "No", None}
    assert all(record.get("synthetic") is True for record in records)
