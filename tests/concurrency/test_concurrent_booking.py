"""SPEC §7 rule 5 / §8: concurrent requests against real PostgreSQL, one connection per
thread, released together by a barrier. The exclusion constraints decide the race."""

from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest

from contexts.scheduling.application.dto import BookAppointmentCommand, CancelAppointmentCommand
from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from tests.concurrency.helpers import booking_call, make_customers, outcome, run_concurrently
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.django_db(transaction=True)

THREADS = 20


def test_last_free_bay_and_technician_goes_to_exactly_one_request(container):
    # Uptown Auto: one bay, one technician (Dana).
    racers = make_customers(THREADS)
    start = utc(2026, 11, 2, 14)

    results = run_concurrently([booking_call(container, c, v, 2, start) for c, v in racers])

    outcomes = Counter(outcome(r) for r in results)
    assert outcomes == {"success": 1, "no_capacity": THREADS - 1}
    assert AppointmentRecord.objects.count() == 1


def test_hot_slot_successes_equal_capacity_and_nothing_is_double_booked(container):
    # Downtown Motors, Brake Service: 3 bays but only 2 brakes technicians (Bob, Chen).
    racers = make_customers(THREADS)
    start = utc(2026, 11, 2, 9)

    results = run_concurrently([booking_call(container, c, v, 1, start) for c, v in racers])

    outcomes = Counter(outcome(r) for r in results)
    assert outcomes == {"success": 2, "no_capacity": THREADS - 2}
    rows = AppointmentRecord.objects.all()
    assert sorted(r.technician_id for r in rows) == [2, 3]
    assert len({r.service_bay_id for r in rows}) == 2


def test_same_idempotency_key_sent_concurrently_books_once(container):
    command = BookAppointmentCommand(1, 1, 2, 1, utc(2026, 11, 2, 9))

    results = run_concurrently(
        [lambda: container.book_appointment("same-key", command) for _ in range(10)]
    )

    assert AppointmentRecord.objects.count() == 1
    ids = {r.value.id for r in results if not isinstance(r, Exception)}
    assert len(ids) == 1  # every success is the original booking or its replay
    fresh = [r for r in results if not isinstance(r, Exception) and not r.replayed]
    assert len(fresh) == 1
    assert {outcome(r) for r in results} <= {"success", "idempotency_conflict"}


def test_concurrent_cancels_of_one_appointment_are_idempotent(container):
    booked = container.book_appointment(
        "to-cancel", BookAppointmentCommand(1, 1, 2, 2, utc(2026, 11, 2, 14))
    ).value

    results = run_concurrently(
        [lambda: container.cancel_appointment(CancelAppointmentCommand(booked.id))] * 10
    )

    assert all(r is None for r in results)
    record = AppointmentRecord.objects.get(pk=booked.id)
    assert record.status == "CANCELLED"


def test_cancel_and_rebook_race_never_double_books(container):
    booked = container.book_appointment(
        "first", BookAppointmentCommand(1, 1, 2, 2, utc(2026, 11, 2, 14))
    ).value
    racers = make_customers(8)

    calls: list[Callable[[], Any]] = [
        lambda: container.cancel_appointment(CancelAppointmentCommand(booked.id))
    ]
    calls += [booking_call(container, c, v, 2, utc(2026, 11, 2, 14)) for c, v in racers]
    run_concurrently(calls)

    confirmed = AppointmentRecord.objects.filter(status="CONFIRMED")
    assert confirmed.count() <= 1
    assert AppointmentRecord.objects.get(pk=booked.id).status == "CANCELLED"
