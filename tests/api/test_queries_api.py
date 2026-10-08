"""GET /appointments/{id}/ and GET /availability/ (SPEC §6, §7 rule 13, A14)."""

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from tests.api.conftest import booking, post_booking
from tests.api.test_book_appointment_api import assert_problem

pytestmark = pytest.mark.usefixtures("seeded")


def availability(api, dealership: int = 2, service_type: int = 2, day: str = "2026-11-02"):
    return api.get(
        "/api/v1/availability/",
        {"dealership_id": dealership, "service_type_id": service_type, "date": day},
    )


def starts(response) -> list[str]:
    return [slot["start_time"] for slot in response.json()["slots"]]


class TestGetAppointment:
    def test_returns_the_booking_body(self, api):
        created = post_booking(api, booking())

        response = api.get(created["Location"])

        assert response.status_code == 200
        assert response.json() == created.json()

    def test_shows_cancelled_status(self, api):
        created = post_booking(api, booking()).json()
        api.delete(f"/api/v1/appointments/{created['id']}/")

        assert api.get(f"/api/v1/appointments/{created['id']}/").json()["status"] == "CANCELLED"

    def test_unknown_returns_404(self, api):
        assert_problem(api.get(f"/api/v1/appointments/{uuid.uuid4()}/"), 404, "not_found")


class TestAvailability:
    def test_spec_response_shape(self, api):
        response = availability(api)

        assert response.status_code == 200
        body = response.json()
        assert (body["dealership_id"], body["service_type_id"], body["date"]) == (
            2,
            2,
            "2026-11-02",
        )
        assert body["slots"][0] == {
            "start_time": "2026-11-02T14:00:00Z",
            "end_time": "2026-11-02T15:30:00Z",
        }

    def test_rule_13_offers_exactly_the_starts_a_booking_would_accept(self, api):
        post_booking(api, booking(dealership=2, start="2026-11-02T16:00:00Z"))
        offered = set(starts(availability(api)))

        # Brute force every grid start of the local day (09:00-18:00 EST = 14:00Z-23:00Z).
        accepted = set()
        for minutes in range(0, 9 * 60, 15):
            hour, minute = divmod(14 * 60 + minutes, 60)
            start = f"2026-11-02T{hour:02d}:{minute:02d}:00Z"
            response = post_booking(api, booking(dealership=2, customer=2, vehicle=3, start=start))
            if response.status_code == 201:
                accepted.add(start)
                AppointmentRecord.objects.filter(pk=response.json()["id"]).delete()

        assert offered == accepted
        assert "2026-11-02T16:00:00Z" not in offered
        assert "2026-11-02T14:30:00Z" in offered  # ends 16:00, back-to-back

    @pytest.mark.django_db(transaction=True)  # real commits, so on_commit dispatch runs
    def test_booking_and_cancel_invalidate_the_cached_listing(self, api):
        before = starts(availability(api))
        created = post_booking(api, booking(dealership=2, start="2026-11-02T14:00:00Z")).json()
        after_booking = starts(availability(api))
        api.delete(f"/api/v1/appointments/{created['id']}/")
        after_cancel = starts(availability(api))

        assert "2026-11-02T14:00:00Z" in before
        assert "2026-11-02T14:00:00Z" not in after_booking
        assert "2026-11-02T14:00:00Z" in after_cancel

    def test_cache_hit_runs_no_queries(self, api):
        availability(api)

        with CaptureQueriesContext(connection) as queries:
            response = availability(api)

        assert response.status_code == 200
        assert len(queries) == 0

    def test_cache_may_be_stale_but_booking_revalidates(self, api, container):
        # A14: the listing may lag (e.g. a write by another process); booking never does.
        availability(api)
        AppointmentRecord.objects.create(  # bypasses the app, so no invalidation event
            id=uuid.uuid4(),
            customer_id=1,
            vehicle_id=1,
            dealership_id=2,
            service_type_id=2,
            service_bay_id=4,
            technician_id=4,
            status="CONFIRMED",
            time_range=("2026-11-02T14:00:00Z", "2026-11-02T15:30:00Z"),
            created_at="2026-11-01T12:00:00Z",
        )

        assert "2026-11-02T14:00:00Z" in starts(availability(api))  # stale, within TTL
        response = post_booking(
            api, booking(dealership=2, customer=2, vehicle=3, start="2026-11-02T14:00:00Z")
        )
        assert_problem(response, 409, "no_capacity")

    @pytest.mark.parametrize(
        "params",
        [
            {"service_type_id": 2, "date": "2026-11-02"},
            {"dealership_id": "x", "service_type_id": 2, "date": "2026-11-02"},
            {"dealership_id": 2, "service_type_id": 2, "date": "02/11/2026"},
        ],
    )
    def test_invalid_query_returns_400(self, api, params):
        assert_problem(api.get("/api/v1/availability/", params), 400, "validation_error")

    @pytest.mark.parametrize(("dealership", "service_type"), [(99, 2), (2, 99)])
    def test_unknown_ids_return_404(self, api, dealership, service_type):
        assert_problem(availability(api, dealership, service_type), 404, "not_found")

    def test_past_day_has_no_slots(self, api):
        assert availability(api, day="2026-10-01").json()["slots"] == []
