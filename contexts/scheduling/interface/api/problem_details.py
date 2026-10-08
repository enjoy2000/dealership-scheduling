"""Maps application/domain errors to RFC 7807 `application/problem+json` (SPEC §14.2)."""

import logging
from dataclasses import dataclass
from typing import Any

from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response

from contexts.scheduling.application.errors import IdempotencyConflictError, NotFoundError
from contexts.scheduling.domain import errors as domain

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


@dataclass(frozen=True)
class Problem:
    status: int
    code: str
    title: str


_DOMAIN_PROBLEMS: dict[type[Exception], Problem] = {
    NotFoundError: Problem(404, "not_found", "Not found"),
    domain.NoCapacityAvailable: Problem(409, "no_capacity", "No capacity"),
    domain.VehicleAlreadyBooked: Problem(409, "vehicle_already_booked", "Vehicle already booked"),
    domain.ResourceConflict: Problem(409, "no_capacity", "No capacity"),
    domain.AppointmentAlreadyCancelled: Problem(
        409, "appointment_already_cancelled", "Appointment already cancelled"
    ),
    IdempotencyConflictError: Problem(409, "idempotency_conflict", "Idempotency conflict"),
    domain.InvalidSlot: Problem(422, "invalid_slot", "Invalid slot"),
    domain.OutsideOpeningHours: Problem(422, "outside_opening_hours", "Outside opening hours"),
    domain.VehicleNotOwnedByCustomer: Problem(422, "vehicle_not_owned", "Vehicle not owned"),
    domain.CancellationNotAllowed: Problem(
        422, "cancellation_not_allowed", "Cancellation not allowed"
    ),
}


def problem_response(
    request: Request | None,
    problem: Problem,
    detail: str,
    headers: dict[str, str] | None = None,
    **extensions: Any,
) -> Response:
    correlation_id = getattr(getattr(request, "_request", request), "correlation_id", None)
    body = {
        "type": "about:blank",
        "title": problem.title,
        "status": problem.status,
        "detail": detail,
        "code": problem.code,
        "correlation_id": correlation_id,
        **extensions,
    }
    return Response(body, status=problem.status, headers=headers, content_type=PROBLEM_JSON)


def _drf_problem(exc: exceptions.APIException) -> tuple[Problem, str, dict[str, Any]]:
    if isinstance(exc, exceptions.ValidationError):
        errors = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        return (
            Problem(400, "validation_error", "Validation error"),
            f"Invalid or missing: {', '.join(errors)}.",
            {"errors": errors},
        )
    if isinstance(exc, exceptions.ParseError):
        return Problem(400, "validation_error", "Validation error"), str(exc.detail), {}
    if isinstance(exc, exceptions.Throttled):
        return Problem(429, "throttled", "Too many requests"), str(exc.detail), {}
    if isinstance(exc, exceptions.NotFound):
        return Problem(404, "not_found", "Not found"), str(exc.detail), {}
    if isinstance(exc, exceptions.MethodNotAllowed):
        return Problem(405, "method_not_allowed", "Method not allowed"), str(exc.detail), {}
    code = exc.default_code if isinstance(exc.default_code, str) else "error"
    return Problem(exc.status_code, code, code.replace("_", " ").capitalize()), str(exc.detail), {}


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """DRF `EXCEPTION_HANDLER`: every error leaves the API as problem+json."""
    request: Request | None = context.get("request")
    for error_type, problem in _DOMAIN_PROBLEMS.items():
        if isinstance(exc, error_type):
            return problem_response(request, problem, str(exc))
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    if isinstance(exc, exceptions.APIException):
        problem, detail, extensions = _drf_problem(exc)
        headers = {}
        wait = getattr(exc, "wait", None)
        if isinstance(exc, exceptions.Throttled) and wait is not None:
            headers["Retry-After"] = str(int(wait) + 1)
        return problem_response(request, problem, detail, headers, **extensions)

    logger.exception("unhandled error", exc_info=exc)
    return problem_response(
        request,
        Problem(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Internal error"),
        "An unexpected error occurred. Quote the correlation id when reporting it.",
    )
