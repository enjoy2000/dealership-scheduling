import uuid
from datetime import date

import pytest

from contexts.scheduling.application.dto import (
    BookAppointmentCommand,
    CancelAppointmentCommand,
    GetAppointmentQuery,
    ListAvailabilityQuery,
    NamedRef,
)
from contexts.scheduling.application.errors import NotFoundError
from tests.unit.application.conftest import BRAKE_SERVICE, DOWNTOWN, UPTOWN, World
from tests.unit.domain.time_helpers import utc

MONDAY = date(2026, 11, 2)


def uptown_booking(
    start_hour: int = 14, vehicle: int = 1, customer: int = 1
) -> BookAppointmentCommand:
    return BookAppointmentCommand(
        customer_id=customer,
        vehicle_id=vehicle,
        service_type_id=BRAKE_SERVICE,
        dealership_id=UPTOWN,
        start_time=utc(2026, 11, 2, start_hour),
    )


def availability(world: World, dealership: int = UPTOWN, day: date = MONDAY):
    return world.list_availability(ListAvailabilityQuery(dealership, BRAKE_SERVICE, day))


class TestGetAppointment:
    def test_returns_the_same_details_as_booking(self, world: World):
        booked = world.book(uptown_booking())

        assert world.get_appointment(GetAppointmentQuery(booked.id)) == booked

    def test_reports_cancelled_status(self, world: World):
        booked = world.book(uptown_booking())
        world.cancel(CancelAppointmentCommand(booked.id))

        assert world.get_appointment(GetAppointmentQuery(booked.id)).status == "CANCELLED"

    def test_unknown_appointment_is_not_found(self, world: World):
        with pytest.raises(NotFoundError):
            world.get_appointment(GetAppointmentQuery(uuid.uuid4()))


class TestListAvailability:
    def test_new_york_day_in_utc(self, world: World):
        result = availability(world)

        assert (result.dealership_id, result.service_type_id, result.date) == (2, 2, MONDAY)
        # 09:00-18:00 EST == 14:00Z-23:00Z; 90-minute service: last start 21:30Z.
        assert result.slots[0].start_time == utc(2026, 11, 2, 14)
        assert result.slots[0].end_time == utc(2026, 11, 2, 15, 30)
        assert result.slots[-1].start_time == utc(2026, 11, 2, 21, 30)
        assert len(result.slots) == 31

    def test_booked_interval_is_removed(self, world: World):
        world.book(uptown_booking(start_hour=14))
        world.availability_cache.entries.clear()

        starts = {s.start_time for s in availability(world).slots}

        assert utc(2026, 11, 2, 14) not in starts
        assert utc(2026, 11, 2, 15, 15) not in starts
        assert utc(2026, 11, 2, 15, 30) in starts  # back-to-back
        assert utc(2026, 11, 2, 12, 45) not in starts  # outside hours anyway

    def test_result_is_cached_and_served_from_cache(self, world: World):
        first = availability(world)
        world.availability_read_model.calls = 0

        second = availability(world)

        assert second == first
        assert world.availability_read_model.calls == 0

    def test_booking_and_cancel_invalidate_that_dealership_and_day(self, world: World):
        availability(world)
        other_day = availability(world, day=date(2026, 11, 3))
        downtown = availability(world, dealership=DOWNTOWN)

        booked = world.book(uptown_booking(start_hour=14))
        after_booking = availability(world)
        assert utc(2026, 11, 2, 14) not in {s.start_time for s in after_booking.slots}

        world.cancel(CancelAppointmentCommand(booked.id))
        after_cancel = availability(world)
        assert utc(2026, 11, 2, 14) in {s.start_time for s in after_cancel.slots}

        # Untouched keys stay cached.
        assert world.availability_cache.get(UPTOWN, BRAKE_SERVICE, date(2026, 11, 3)) == other_day
        assert world.availability_cache.get(DOWNTOWN, BRAKE_SERVICE, MONDAY) == downtown

    def test_only_qualified_technicians_count(self, world: World):
        # Downtown brakes: Bob and Chen. Book both at 09:00 -> 09:00 not offered even
        # though Alice (no brakes skill) and Bay 3 are free.
        for vehicle, customer in [(1, 1), (3, 2)]:
            world.book(
                BookAppointmentCommand(
                    customer, vehicle, BRAKE_SERVICE, DOWNTOWN, utc(2026, 11, 2, 9)
                )
            )
        world.availability_cache.entries.clear()

        starts = {s.start_time for s in availability(world, dealership=DOWNTOWN).slots}

        assert utc(2026, 11, 2, 9) not in starts
        assert utc(2026, 11, 2, 8) not in starts  # 08:00-09:30 overlaps both
        assert utc(2026, 11, 2, 10, 30) in starts

    @pytest.mark.parametrize(("dealership", "service_type"), [(99, BRAKE_SERVICE), (UPTOWN, 99)])
    def test_unknown_references_are_not_found_and_not_cached(
        self, world: World, dealership, service_type
    ):
        with pytest.raises(NotFoundError):
            world.list_availability(ListAvailabilityQuery(dealership, service_type, MONDAY))
        assert world.availability_cache.entries == {}


def test_get_appointment_names_match_booking(world: World):
    booked = world.book(uptown_booking())

    details = world.get_appointment(GetAppointmentQuery(booked.id))

    assert details.technician == NamedRef(4, "Dana")
    assert details.service_bay == NamedRef(4, "Bay 1")
