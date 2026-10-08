"""Correlation id per request: taken from `X-Correlation-ID` (or `X-Request-ID`) when
supplied, otherwise generated; exposed on the request, the response and in logs."""

import re
import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

HEADER = "X-Correlation-ID"
_SAFE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


class CorrelationIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        supplied = request.headers.get(HEADER) or request.headers.get("X-Request-ID") or ""
        correlation_id = supplied if _SAFE.match(supplied) else uuid.uuid4().hex
        request.correlation_id = correlation_id  # type: ignore[attr-defined]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        response = self.get_response(request)
        response[HEADER] = correlation_id
        return response
