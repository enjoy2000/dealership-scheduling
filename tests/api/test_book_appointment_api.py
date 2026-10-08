"""SPEC §7 acceptance criteria for booking, through the HTTP API."""

from typing import Any, cast

import pytest

from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from tests.api.conftest import booking, post_booking

pytestmark = pytest.mark.usefixtures("seeded")

PROBLEM = "application/problem+json"


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.content
    assert response["Content-Type"] == PROBLEM
    body = cast(dict[str, Any], response.json())
    assert body["status"] == status
    assert body["code"] == code
    assert body["title"]
    assert body["detail"]
    assert body["type"]
    assert body["correlation_id"] == response["X-Correlation-ID"]
    return body


class TestSuccess:
    def test_201_with_the_spec_body_and_location(self, api):
        response = post_booking(api, booking())

        assert response.status_code == 201
        body = response.json()
        assert body == {
            "id": body["id"],
            "status": "CONFIRMED",
            "start_time": "2026-11-02T09:00:00Z",
            "end_time": "2026-11-02T10:30:00Z",
            "customer": {"id": 1, "name": "Customer One"},
            "vehicle": {"id": 1, "vin": "1HGCM82633A004352"},
            "service_type": {"id": 2, "name": "Brake Service", "duration_minutes": 90},
            "dealership": {"id": 1, "name": "Downtown Motors"},
            "technician": {"id": 2, "name": "Bob"},
            "service_bay": {"id": 1, "name": "Bay 1"},
        }
        assert response["Location"] == f"http://testserver/api/v1/appointments/{body['id']}/"

    def test_rule_3_persists_appointment_linking_all_parties(self, api):
        body = post_booking(api, booking()).json()

        record = AppointmentRecord.objects.get(pk=body["id"])
        assert (record.customer_id, record.vehicle_id) == (1, 1)
        assert (record.service_bay_id, record.technician_id) == (1, 2)
        assert record.status == "CONFIRMED"

    def test_start_time_with_offset_is_normalised_to_utc(self, api):
        response = post_booking(api, booking(start="2026-11-02T04:00:00-05:00"))

        assert response.json()["start_time"] == "2026-11-02T09:00:00Z"


class TestCapacityRules:
    """Dealership 2 (Uptown Auto, New York) has one bay and one technician."""

    def test_rule_2_no_free_resource_returns_409_and_persists_nothing(self, api):
        post_booking(api, booking(dealership=2, start="2026-11-02T14:00:00Z"))

        response = post_booking(
            api, booking(dealership=2, customer=2, vehicle=3, start="2026-11-02T15:00:00Z")
        )

        assert_problem(response, 409, "no_capacity")
        assert AppointmentRecord.objects.count() == 1

    def test_rule_4_back_to_back_booking_succeeds(self, api):
        first = post_booking(api, booking(dealership=2, start="2026-11-02T14:00:00Z"))
        back_to_back = post_booking(
            api, booking(dealership=2, customer=2, vehicle=3, start="2026-11-02T15:30:00Z")
        )

        assert (first.status_code, back_to_back.status_code) == (201, 201)

    def test_rule_4_overlap_fails(self, api):
        # On the 15-minute grid the smallest API-level overlap is 15 minutes; the
        # 1-minute case is covered by the domain and database constraint tests.
        post_booking(api, booking(dealership=2, start="2026-11-02T14:00:00Z"))

        overlap = post_booking(
            api, booking(dealership=2, customer=2, vehicle=3, start="2026-11-02T15:15:00Z")
        )

        assert_problem(overlap, 409, "no_capacity")

    def test_rule_6_unqualified_technician_is_never_assigned(self, api):
        # Bob and Chen (brakes) get busy; Alice (no brakes skill) stays free.
        post_booking(api, booking())
        post_booking(api, booking(customer=2, vehicle=3))

        response = post_booking(api, booking(customer=3, vehicle=4))

        assert_problem(response, 409, "no_capacity")
        assert not AppointmentRecord.objects.filter(technician_id=1).exists()

    def test_vehicle_already_booked_returns_409(self, api):
        post_booking(api, booking(dealership=1, start="2026-11-02T15:00:00Z"))

        response = post_booking(api, booking(dealership=2, start="2026-11-02T15:30:00Z"))

        assert_problem(response, 409, "vehicle_already_booked")


class TestValidation:
    def test_rule_11_missing_idempotency_key_returns_400(self, api):
        response = api.post("/api/v1/appointments/", booking(), format="json")

        body = assert_problem(response, 400, "validation_error")
        assert "Idempotency-Key" in body["detail"]

    def test_overlong_idempotency_key_returns_400(self, api):
        response = post_booking(api, booking(), key="k" * 256)

        assert_problem(response, 400, "validation_error")

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({k: v for k, v in booking().items() if k != "vehicle_id"}, "vehicle_id"),
            (booking() | {"customer_id": "one"}, "customer_id"),
            (booking() | {"start_time": "tomorrow"}, "start_time"),
            (booking() | {"start_time": "2026-11-02T09:00:00"}, "start_time"),  # naive
        ],
    )
    def test_malformed_payload_returns_400_with_field_errors(self, api, body, field):
        response = post_booking(api, body)

        problem = assert_problem(response, 400, "validation_error")
        assert field in problem["errors"]

    @pytest.mark.parametrize(
        "override",
        [{"customer": 99}, {"vehicle": 99}, {"service_type": 99}, {"dealership": 99}],
    )
    def test_rule_9_unknown_ids_return_404(self, api, override):
        assert_problem(post_booking(api, booking(**override)), 404, "not_found")

    def test_rule_9_vehicle_of_another_customer_returns_422(self, api):
        assert_problem(post_booking(api, booking(customer=2)), 422, "vehicle_not_owned")

    def test_rule_10_past_start_returns_422(self, api):
        response = post_booking(api, booking(start="2026-11-01T11:45:00Z"))

        assert_problem(response, 422, "invalid_slot")

    def test_off_grid_start_returns_422(self, api):
        assert_problem(
            post_booking(api, booking(start="2026-11-02T09:10:00Z")), 422, "invalid_slot"
        )

    def test_rule_10_outside_opening_hours_returns_422(self, api):
        response = post_booking(api, booking(start="2026-11-02T07:30:00Z"))

        assert_problem(response, 422, "outside_opening_hours")


def test_correlation_id_from_request_is_echoed(api):
    response = api.post(
        "/api/v1/appointments/",
        booking(),
        format="json",
        headers={"X-Correlation-ID": "abc-123"},
    )

    assert response["X-Correlation-ID"] == "abc-123"
    assert response.json()["correlation_id"] == "abc-123"


def test_unexpected_error_returns_500_problem(api, container, monkeypatch):
    def explode(key, command):
        raise RuntimeError("database on fire")

    monkeypatch.setattr(container, "book_appointment", explode)
    client = api
    client.raise_request_exception = False

    response = post_booking(client, booking())

    body = assert_problem(response, 500, "internal_error")
    assert "fire" not in body["detail"]  # internals are not leaked


def test_booking_is_throttled_per_customer(api, monkeypatch):
    from contexts.scheduling.interface.api.throttles import BookingRateThrottle

    monkeypatch.setattr(BookingRateThrottle, "THROTTLE_RATES", {"booking": "2/min"})
    past = booking(start="2026-11-01T11:00:00Z")  # rejected cheaply, still counted

    first, second, third = (post_booking(api, past) for _ in range(3))

    assert (first.status_code, second.status_code) == (422, 422)
    assert_problem(third, 429, "throttled")
    assert "Retry-After" in third
    assert post_booking(api, booking(customer=2, vehicle=3)).status_code == 201
