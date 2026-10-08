"""Prometheus metrics and OpenTelemetry spans for use cases (SPEC §9).

Exposed at /metrics with django-prometheus' HTTP and DB metrics. Under gunicorn,
PROMETHEUS_MULTIPROC_DIR aggregates all workers (see gunicorn.conf.py).
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import trace
from prometheus_client import Counter, Histogram

# Latency buckets bracket the SLOs (p95 < 300 ms, p99 < 800 ms booking; 150 ms availability).
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.8, 1.0, 2.0, 5.0)

BOOKING_REQUESTS = Counter("booking_requests", "Booking attempts by outcome.", ["outcome"])
BOOKING_DURATION = Histogram(
    "booking_duration_seconds", "Booking use-case latency.", buckets=_BUCKETS
)
BOOKING_CONFLICTS = Counter(
    "booking_conflicts", "Exclusion-constraint conflicts (a concurrent booking won the race)."
)
BOOKING_RETRIES = Counter("booking_retries", "Booking retries after a conflict.")
USE_CASE_REQUESTS = Counter(
    "use_case_requests", "Use-case invocations by outcome.", ["use_case", "outcome"]
)
USE_CASE_DURATION = Histogram(
    "use_case_duration_seconds", "Use-case latency.", ["use_case"], buckets=_BUCKETS
)
AVAILABILITY_CACHE_REQUESTS = Counter(
    "availability_cache_requests", "Availability cache lookups.", ["result"]
)

tracer = trace.get_tracer("scheduling")


class PrometheusTelemetry:
    """Implements the application's UseCaseTelemetry and BookingObserver ports."""

    @contextmanager
    def span(self, use_case: str, attributes: Mapping[str, object]) -> Iterator[None]:
        span_attributes = {k: v for k, v in attributes.items() if isinstance(v, str | int)}
        with tracer.start_as_current_span(f"use_case.{use_case}", attributes=span_attributes):
            yield

    def record(self, use_case: str, outcome: str, duration_seconds: float) -> None:
        trace.get_current_span().set_attribute("outcome", outcome)
        USE_CASE_REQUESTS.labels(use_case=use_case, outcome=outcome).inc()
        USE_CASE_DURATION.labels(use_case=use_case).observe(duration_seconds)
        if use_case == "book_appointment":
            BOOKING_REQUESTS.labels(outcome=outcome).inc()
            BOOKING_DURATION.observe(duration_seconds)

    def booking_conflict(self) -> None:
        BOOKING_CONFLICTS.inc()

    def booking_retry(self, attempt: int) -> None:
        BOOKING_RETRIES.inc()
