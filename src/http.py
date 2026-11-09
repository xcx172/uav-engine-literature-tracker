"""HTTP JSON helper with bounded, sanitized retries."""

from __future__ import annotations

import time
from typing import Any, Callable

from .errors import ErrorType, TrackerError, classify_status


def _retry_after(response: Any, fallback: float) -> float:
    raw = getattr(response, "headers", {}) or {}
    try:
        value = raw.get("Retry-After")
        return max(0.0, float(value)) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def request_json(
    session: Any,
    method: str,
    url: str,
    *,
    service: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Perform a request and return parsed JSON.

    Raises :class:`TrackerError` with a fixed, sanitized message.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last: TrackerError | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 - normalized below
            name = type(exc).__name__.lower()
            kind = ErrorType.TIMEOUT if "timeout" in name else ErrorType.NETWORK
            last = TrackerError(kind, service=service, attempt=attempt)
            if attempt < attempts:
                sleep(min(2.0, float(attempt)))
                continue
            raise last from None

        status = int(getattr(response, "status_code", 0))
        if status == 200:
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                last = TrackerError(ErrorType.JSON_INVALID, service=service, status=status, attempt=attempt)
                if attempt < attempts:
                    sleep(0.5)
                    continue
                raise last from None
            if not isinstance(payload, dict):
                last = TrackerError(ErrorType.JSON_INVALID, service=service, status=status, attempt=attempt)
                if attempt < attempts:
                    sleep(0.5)
                    continue
                raise last from None
            return payload

        error = classify_status(service, status, attempt)
        if error.stop_service or not error.retryable:
            raise error

        last = error
        if attempt < attempts:
            sleep(_retry_after(response, 2.0) if error.kind is ErrorType.RATE_LIMITED else min(2.0, float(attempt)))
            continue
        raise last

    raise last if last is not None else TrackerError(ErrorType.NETWORK, service=service)
