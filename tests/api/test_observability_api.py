import json
import logging

import pytest

from contexts.scheduling.infrastructure.telemetry.logging import JsonFormatterFactory
from tests.api.conftest import booking, post_booking

pytestmark = pytest.mark.usefixtures("seeded")


def metric_value(text: str, name: str, labels: str = "") -> float:
    prefix = f"{name}{{{labels}}}" if labels else name
    for line in text.splitlines():
        if line.startswith(prefix + " "):
            return float(line.split()[-1])
    return 0.0


def test_metrics_endpoint_exposes_booking_and_http_metrics(api):
    before = api.get("/metrics").content.decode()
    post_booking(api, booking())
    post_booking(api, booking(customer=2))  # 422 vehicle_not_owned

    text = api.get("/metrics").content.decode()

    for outcome, delta in (("success", 1), ("vehicle_not_owned", 1)):
        label = f'outcome="{outcome}"'
        assert (
            metric_value(text, "booking_requests_total", label)
            == metric_value(before, "booking_requests_total", label) + delta
        )
    assert "booking_duration_seconds_bucket" in text
    assert "booking_conflicts_total" in text
    assert "booking_retries_total" in text
    assert "use_case_requests_total" in text
    assert "django_http_requests_total_by_view_transport_method_total" in text
    assert "django_db_execute_total" in text


def test_availability_cache_hits_and_misses_are_counted(api):
    params = {"dealership_id": 2, "service_type_id": 2, "date": "2026-11-02"}
    before = api.get("/metrics").content.decode()

    api.get("/api/v1/availability/", params)
    api.get("/api/v1/availability/", params)

    text = api.get("/metrics").content.decode()
    for result in ("hit", "miss"):
        label = f'result="{result}"'
        assert (
            metric_value(text, "availability_cache_requests_total", label)
            == metric_value(before, "availability_cache_requests_total", label) + 1
        )


def test_logs_are_json_with_correlation_id(api, caplog):
    formatter = JsonFormatterFactory()
    with caplog.at_level(logging.INFO):
        api.post(
            "/api/v1/appointments/",
            booking(),
            format="json",
            headers={"Idempotency-Key": "log-test", "X-Correlation-ID": "corr-42"},
        )

    [record] = [r for r in caplog.records if r.getMessage() == "use_case.completed"]
    line = json.loads(formatter.format(record))
    assert line["event"] == "use_case.completed"
    assert line["correlation_id"] == "corr-42"
    assert line["use_case"] == "book_appointment"
    assert line["outcome"] == "success"
    assert line["dealership_id"] == 1
    assert line["level"] == "info"
    assert "timestamp" in line


def test_use_case_spans_are_created(api):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    from contexts.scheduling.infrastructure.telemetry import metrics

    original = metrics.tracer
    metrics.tracer = tracer
    try:
        post_booking(api, booking())
    finally:
        metrics.tracer = original
        trace.get_tracer_provider()

    names = [span.name for span in exporter.get_finished_spans()]
    assert "use_case.book_appointment" in names
    span = next(s for s in exporter.get_finished_spans() if s.name == "use_case.book_appointment")
    assert span.attributes is not None
    assert span.attributes["dealership_id"] == 1
    assert span.attributes["outcome"] == "success"
