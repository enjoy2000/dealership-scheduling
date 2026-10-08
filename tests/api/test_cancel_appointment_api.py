"""SPEC §7 rules 7 and 12 (with RESTful 204 semantics, DECISIONS I18)."""

import uuid

import pytest

from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from tests.api.conftest import booking, post_booking
from tests.api.test_book_appointment_api import assert_problem
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")


def book_uptown(api, customer: int = 1, vehicle: int = 1) -> str:
    response = post_booking(
        api, booking(dealership=2, customer=customer, vehicle=vehicle, start="2026-11-02T14:00:00Z")
    )
    assert response.status_code == 201, response.content
    return str(response.json()["id"])


def test_cancel_returns_204_with_empty_body(api):
    appointment_id = book_uptown(api)

    response = api.delete(f"/api/v1/appointments/{appointment_id}/")

    assert response.status_code == 204
    assert response.content == b""
    record = AppointmentRecord.objects.get(pk=appointment_id)
    assert record.status == "CANCELLED"
    assert record.cancelled_at is not None


def test_rule_12_repeat_cancel_is_idempotent(api):
    appointment_id = book_uptown(api)
    api.delete(f"/api/v1/appointments/{appointment_id}/")
    cancelled_at = AppointmentRecord.objects.get(pk=appointment_id).cancelled_at

    response = api.delete(f"/api/v1/appointments/{appointment_id}/")

    assert response.status_code == 204
    assert AppointmentRecord.objects.get(pk=appointment_id).cancelled_at == cancelled_at


def test_rule_7_cancelling_frees_bay_and_technician(api):
    appointment_id = book_uptown(api)
    api.delete(f"/api/v1/appointments/{appointment_id}/")

    book_uptown(api, customer=2, vehicle=3)


def test_cancel_unknown_appointment_returns_404(api):
    assert_problem(api.delete(f"/api/v1/appointments/{uuid.uuid4()}/"), 404, "not_found")


def test_malformed_appointment_id_returns_404(api):
    assert api.delete("/api/v1/appointments/not-a-uuid/").status_code == 404


@pytest.mark.parametrize("now", [utc(2026, 11, 2, 14), utc(2026, 11, 2, 15)])
def test_rule_12_cancel_at_or_after_start_returns_422(api, clock, now):
    appointment_id = book_uptown(api)
    clock.current = now

    response = api.delete(f"/api/v1/appointments/{appointment_id}/")

    assert_problem(response, 422, "cancellation_not_allowed")
    assert AppointmentRecord.objects.get(pk=appointment_id).status == "CONFIRMED"
