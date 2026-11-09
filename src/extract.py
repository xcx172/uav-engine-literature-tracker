"""DeepSeek extraction with explicit non-thinking mode and strict validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .config import Settings
from .errors import ErrorType, TrackerError
from .http import request_json
from .prompts import EXTRACT_SYSTEM, PROMPT_VERSION

API_URL = "https://api.deepseek.com/chat/completions"
MAX_ATTEMPTS = 3
ALLOWED_KEYS = {"contribution_zh", "methods", "datasets", "code_open", "code_evidence"}


@dataclass(frozen=True)
class Extracted:
    contribution_zh: str | None
    methods: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    code_open: str | None = None
    code_evidence: str | None = None
    prompt_version: str = PROMPT_VERSION


def input_hash(title: str, abstract: str | None) -> str:
    payload = f"{title}\n{abstract or ''}\n{PROMPT_VERSION}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_messages(title: str, abstract: str) -> list[dict[str, str]]:
    user_data = json.dumps({"title": title, "abstract": abstract}, ensure_ascii=False)
    return [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": user_data},
    ]


def _location_pattern(evidence: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in evidence.split()]
    return re.compile(r"\s+".join(parts), re.IGNORECASE)


def locate_evidence(abstract: str, evidence: str) -> str | None:
    match = _location_pattern(evidence).search(abstract)
    if not match:
        return None
    end = match.end()
    if end < len(abstract) and abstract[end] in ".!?":
        end += 1
    return abstract[match.start():end]


def _schema_error(detail: str = "") -> TrackerError:
    return TrackerError(ErrorType.SCHEMA_INVALID, service="deepseek", detail=detail)


def validate_extraction(obj: Any, abstract: str) -> Extracted:
    if not isinstance(obj, dict) or set(obj) != ALLOWED_KEYS:
        raise _schema_error("keys")

    contribution = obj.get("contribution_zh")
    if contribution is not None and not isinstance(contribution, str):
        raise _schema_error("contribution_zh")
    if isinstance(contribution, str):
        contribution = contribution.strip() or None

    def string_list(name: str) -> list[str]:
        value = obj.get(name)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise _schema_error(name)
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise _schema_error(name)
        return cleaned

    methods = string_list("methods")
    datasets = string_list("datasets")

    code_open = obj.get("code_open")
    if code_open not in ("Yes", "No", None):
        raise _schema_error("code_open")

    evidence = obj.get("code_evidence")
    if evidence is not None and not isinstance(evidence, str):
        raise _schema_error("code_evidence")
    if isinstance(evidence, str):
        evidence = evidence.strip() or None

    if code_open is None:
        if evidence is not None:
            raise _schema_error("evidence_without_status")
        return Extracted(contribution, methods, datasets, None, None)

    if not evidence:
        raise _schema_error("missing_evidence")
    original = locate_evidence(abstract, evidence)
    if original is None:
        raise _schema_error("evidence_not_in_abstract")
    return Extracted(contribution, methods, datasets, code_open, original)


def _parse_payload(payload: dict[str, Any], abstract: str) -> Extracted:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TrackerError(ErrorType.EMPTY_OUTPUT, service="deepseek", attempt=0)
    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise TrackerError(ErrorType.EMPTY_OUTPUT, service="deepseek", attempt=0)
    if choice.get("finish_reason") == "length":
        raise TrackerError(ErrorType.TRUNCATED, service="deepseek", attempt=0)
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        raise TrackerError(ErrorType.JSON_INVALID, service="deepseek", attempt=0) from None
    return validate_extraction(parsed, abstract)


def extract_fields(session: Any, settings: Settings, title: str, abstract: str) -> Extracted:
    """One extraction = HTTP request + JSON validation, sharing 3 attempts."""
    body = {
        "model": settings.model,
        "thinking": {"type": "disabled"},
        "messages": build_messages(title, abstract),
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 900,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_key or ''}",
        "Content-Type": "application/json",
    }

    last: TrackerError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            payload = request_json(
                session,
                "POST",
                API_URL,
                service="deepseek",
                headers=headers,
                json_body=body,
                timeout=settings.timeout,
                attempts=1,
            )
            extracted = _parse_payload(payload, abstract)
            return extracted
        except TrackerError as exc:
            exc.attempt = attempt
            last = exc
            if exc.stop_service or exc.kind in {ErrorType.CONFIG_MISSING, ErrorType.PARAM_INVALID}:
                raise
            if attempt >= MAX_ATTEMPTS:
                raise
    raise last if last is not None else TrackerError(ErrorType.SCHEMA_INVALID, service="deepseek")
