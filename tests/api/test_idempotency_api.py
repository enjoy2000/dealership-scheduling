"""SPEC §7 rule 8 and §14.5."""

import pytest

from contexts.scheduling.infrastructure.persistence.models import (
    AppointmentRecord,
    IdempotencyRecord,
)
from tests.api.conftest import booking, post_booking
from tests.api.test_book_appointment_api import assert_problem

pytestmark = pytest.mark.usefixtures("seeded")


def test_rule_8_same_key_and_payload_replays_the_original_response(api):
    first = post_booking(api, booking(), key="retry-me")

    second = post_booking(api, booking(), key="retry-me")

    assert second.status_code == 201
    assert second.json() == first.json()
    assert second["Location"] == first["Location"]
    assert second["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first
    assert AppointmentRecord.objects.count() == 1


def test_same_key_with_a_different_payload_returns_409(api):
    post_booking(api, booking(), key="k")

    response = post_booking(api, booking(start="2026-11-02T10:00:00Z"), key="k")

    assert_problem(response, 409, "idempotency_conflict")
    assert AppointmentRecord.objects.count() == 1


def test_failed_request_is_not_stored_so_the_client_can_retry(api):
    blocker = post_booking(api, booking(dealership=2, start="2026-11-02T14:00:00Z")).json()
    contender = booking(dealership=2, customer=2, vehicle=3, start="2026-11-02T14:00:00Z")

    assert_problem(post_booking(api, contender, key="contender"), 409, "no_capacity")
    assert not IdempotencyRecord.objects.filter(key="contender").exists()

    api.delete(f"/api/v1/appointments/{blocker['id']}/")
    retry = post_booking(api, contender, key="contender")

    assert retry.status_code == 201
    assert "Idempotent-Replayed" not in retry


def test_key_row_is_written_with_the_appointment(api):
    body = post_booking(api, booking(), key="stored").json()

    record = IdempotencyRecord.objects.get(key="stored")
    assert record.response_status == 201
    assert record.response_body is not None
    assert record.response_body["id"] == body["id"]
    assert len(record.request_hash) == 64
