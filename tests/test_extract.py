from __future__ import annotations

import pytest

from src.errors import ErrorType, TrackerError
from src.extract import extract_fields, locate_evidence, validate_extraction
from tests.helpers import FakeResponse, FakeSession, deepseek_json, synthetic_payload

ABSTRACT = "We use a PI controller. The implementation code is publicly available."


def test_valid_payload_returns_original_evidence(settings):
    payload = synthetic_payload(
        code_open="Yes",
        code_evidence="the implementation code is publicly available",
    )
    session = FakeSession([deepseek_json(payload)])
    extracted = extract_fields(session, settings, "Title", ABSTRACT)
    assert extracted.code_open == "Yes"
    assert extracted.code_evidence == "The implementation code is publicly available."


def test_request_uses_non_thinking_and_json_mode(settings):
    session = FakeSession([deepseek_json(synthetic_payload())])
    extract_fields(session, settings, "Title", ABSTRACT)
    body = session.calls[0]["json"]
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "deepseek-flash"


def test_schema_failure_uses_three_attempts(settings):
    bad = synthetic_payload(code_open="Yes", code_evidence="not present in abstract")
    session = FakeSession([deepseek_json(bad), deepseek_json(bad), deepseek_json(bad)])
    with pytest.raises(TrackerError) as excinfo:
        extract_fields(session, settings, "Title", ABSTRACT)
    assert excinfo.value.kind is ErrorType.SCHEMA_INVALID
    assert len(session.calls) == 3


def test_quota_error_stops_immediately(settings):
    session = FakeSession([FakeResponse(402, {"error": "balance"})])
    with pytest.raises(TrackerError) as excinfo:
        extract_fields(session, settings, "Title", ABSTRACT)
    assert excinfo.value.kind is ErrorType.QUOTA_EXHAUSTED
    assert len(session.calls) == 1


def test_validation_rejects_empty_evidence():
    with pytest.raises(TrackerError):
        validate_extraction(
            synthetic_payload(code_open="Yes", code_evidence="   "),
            ABSTRACT,
        )


def test_locate_is_case_insensitive():
    assert locate_evidence(ABSTRACT, "THE IMPLEMENTATION CODE IS PUBLICLY AVAILABLE") == (
        "The implementation code is publicly available."
    )
