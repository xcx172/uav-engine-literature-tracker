from __future__ import annotations

import pytest

from src.errors import ErrorType, TrackerError
from src.http import request_json
from tests.helpers import FakeResponse, FakeSession


class TimeoutLike(Exception):
    pass


def test_429_is_retried_then_succeeds():
    session = FakeSession(
        [FakeResponse(429, {}, {"Retry-After": "0"}), FakeResponse(200, {"ok": True})]
    )
    payload = request_json(
        session, "GET", "https://example.invalid", service="openalex", sleep=lambda _: None
    )
    assert payload == {"ok": True}
    assert len(session.calls) == 2


def test_401_stops_immediately():
    session = FakeSession([FakeResponse(401, {})])
    with pytest.raises(TrackerError) as excinfo:
        request_json(session, "GET", "https://example.invalid", service="openalex")
    assert excinfo.value.kind is ErrorType.AUTH_FAILED
    assert len(session.calls) == 1


def test_500_exhausts_three_attempts():
    session = FakeSession([FakeResponse(500, {}) for _ in range(3)])
    with pytest.raises(TrackerError) as excinfo:
        request_json(session, "GET", "https://example.invalid", service="openalex", sleep=lambda _: None)
    assert excinfo.value.kind is ErrorType.SERVER_ERROR
    assert len(session.calls) == 3


def test_timeout_is_retried():
    session = FakeSession([TimeoutLike("slow"), TimeoutLike("slow"), TimeoutLike("slow")])
    with pytest.raises(TrackerError) as excinfo:
        request_json(session, "GET", "https://example.invalid", service="openalex", sleep=lambda _: None)
    assert excinfo.value.kind is ErrorType.TIMEOUT
    assert len(session.calls) == 3


def test_400_is_permanent():
    session = FakeSession([FakeResponse(400, {})])
    with pytest.raises(TrackerError) as excinfo:
        request_json(session, "GET", "https://example.invalid", service="openalex")
    assert excinfo.value.kind is ErrorType.PARAM_INVALID
    assert len(session.calls) == 1
