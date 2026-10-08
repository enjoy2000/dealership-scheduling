import uuid
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from contexts.scheduling.application.dto import Availability, AvailableSlot, NamedRef
from contexts.scheduling.domain.model.value_objects import (
    BayId,
    DealershipId,
    Skill,
    TechnicianId,
    TimeSlot,
)
from contexts.scheduling.infrastructure.cache import DjangoAvailabilityCache
from contexts.scheduling.infrastructure.persistence.read_models import (
    DjangoAppointmentReadModel,
    DjangoAvailabilityReadModel,
)
from tests.infrastructure.conftest import insert_appointment
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")
DAY = TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 17))


def test_appointment_read_model_projects_scheduling_data():
    record = insert_appointment(start=utc(2026, 11, 2, 9))

    row = DjangoAppointmentReadModel().get(record.id)

    assert row is not None
    assert (row.start_time, row.end_time) == (utc(2026, 11, 2, 9), utc(2026, 11, 2, 10, 30))
    assert row.status == "CONFIRMED"
    assert (row.customer_id, row.vehicle_id, row.service_type_id, row.dealership_id) == (1, 1, 2, 1)
    assert row.technician == NamedRef(2, "Bob")
    assert row.service_bay == NamedRef(1, "Bay 1")
    assert DjangoAppointmentReadModel().get(uuid.uuid4()) is None


def test_day_schedule_lists_every_bay_and_qualified_technician_with_busy_intervals():
    insert_appointment(start=utc(2026, 11, 2, 9), bay=2, technician=3)
    insert_appointment(start=utc(2026, 11, 2, 7), minutes=60, bay=1, technician=2, vehicle=2)
    insert_appointment(  # cancelled: ignored
        start=utc(2026, 11, 2, 12),
        bay=3,
        technician=2,
        vehicle=3,
        customer=2,
        status="CANCELLED",
        cancelled_at=utc(2026, 11, 1),
    )
    insert_appointment(start=utc(2026, 11, 3, 9), bay=1, technician=2)  # other day

    schedule = DjangoAvailabilityReadModel().day_schedule(DealershipId(1), Skill("brakes"), DAY)

    assert set(schedule.bay_busy) == {BayId(1), BayId(2), BayId(3)}
    assert set(schedule.technician_busy) == {TechnicianId(2), TechnicianId(3)}  # not Alice
    assert schedule.bay_busy[BayId(1)] == []  # 07:00-08:00 ends as the window opens
    assert schedule.bay_busy[BayId(2)] == [TimeSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 10, 30))]
    assert schedule.technician_busy[TechnicianId(2)] == []


def test_day_schedule_uses_a_fixed_number_of_queries():
    for hour in range(8, 15):
        insert_appointment(start=utc(2026, 11, 2, hour), minutes=60)

    with CaptureQueriesContext(connection) as queries:
        DjangoAvailabilityReadModel().day_schedule(DealershipId(1), Skill("brakes"), DAY)

    assert len(queries) == 3


class TestDjangoAvailabilityCache:
    def availability(
        self, dealership: int = 1, service_type: int = 2, day: date = date(2026, 11, 2)
    ):
        slot = AvailableSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 10, 30))
        return Availability(dealership, service_type, day, (slot,))

    def test_round_trip(self):
        cache = DjangoAvailabilityCache(ttl_seconds=5)
        value = self.availability()

        cache.set(value)

        assert cache.get(1, 2, date(2026, 11, 2)) == value
        assert cache.get(1, 3, date(2026, 11, 2)) is None

    def test_invalidate_drops_every_service_type_for_that_dealership_day_only(self):
        cache = DjangoAvailabilityCache(ttl_seconds=5)
        brakes, oil = self.availability(service_type=2), self.availability(service_type=1)
        other_day = self.availability(day=date(2026, 11, 3))
        other_dealership = self.availability(dealership=2)
        for value in (brakes, oil, other_day, other_dealership):
            cache.set(value)

        cache.invalidate(1, date(2026, 11, 2))

        assert cache.get(1, 2, date(2026, 11, 2)) is None
        assert cache.get(1, 1, date(2026, 11, 2)) is None
        assert cache.get(1, 2, date(2026, 11, 3)) == other_day
        assert cache.get(2, 2, date(2026, 11, 2)) == other_dealership

    def test_zero_ttl_disables_caching(self):
        cache = DjangoAvailabilityCache(ttl_seconds=0)
        cache.set(self.availability())

        assert cache.get(1, 2, date(2026, 11, 2)) is None
