"""Fixed error types and a sanitized exception.

Only the fields below may reach logs or pages: service name, HTTP status,
error type, attempt counter. Never include response bodies, URLs or keys.
"""

from __future__ import annotations

from enum import Enum


class ErrorType(str, Enum):
    CONFIG_MISSING = "CONFIG_MISSING"
    AUTH_FAILED = "AUTH_FAILED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    PARAM_INVALID = "PARAM_INVALID"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    NETWORK = "NETWORK"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    TRUNCATED = "TRUNCATED"
    JSON_INVALID = "JSON_INVALID"
    SCHEMA_INVALID = "SCHEMA_INVALID"


RETRYABLE = {
    ErrorType.TIMEOUT,
    ErrorType.RATE_LIMITED,
    ErrorType.SERVER_ERROR,
    ErrorType.NETWORK,
    ErrorType.EMPTY_OUTPUT,
    ErrorType.TRUNCATED,
    ErrorType.JSON_INVALID,
    ErrorType.SCHEMA_INVALID,
}

# Stop all remaining calls to the same service for this run.
STOP_SERVICE = {ErrorType.AUTH_FAILED, ErrorType.QUOTA_EXHAUSTED}

PERMANENT = {ErrorType.CONFIG_MISSING, ErrorType.PARAM_INVALID}


def classify_status(service: str, status: int, attempt: int = 0) -> "TrackerError":
    if status in (401, 403):
        kind = ErrorType.AUTH_FAILED
    elif status == 402:
        kind = ErrorType.QUOTA_EXHAUSTED
    elif status == 429:
        kind = ErrorType.RATE_LIMITED
    elif status >= 500:
        kind = ErrorType.SERVER_ERROR
    else:
        kind = ErrorType.PARAM_INVALID
    return TrackerError(kind, service=service, status=status, attempt=attempt)


class TrackerError(Exception):
    def __init__(
        self,
        kind: ErrorType,
        *,
        service: str = "unknown",
        status: int | None = None,
        attempt: int = 0,
        detail: str = "",
    ) -> None:
        self.kind = kind
        self.service = service
        self.status = status
        self.attempt = attempt
        self.detail = detail
        super().__init__(str(self))

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE

    @property
    def stop_service(self) -> bool:
        return self.kind in STOP_SERVICE

    def __str__(self) -> str:  # sanitized: no URL, body, key or traceback
        return (
            f"{self.service} {self.kind.value} status={self.status if self.status is not None else '-'}"
            f" attempt={self.attempt}"
        )
