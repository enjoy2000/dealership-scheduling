import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from contexts.scheduling.application.dto import (
    AppointmentDetails,
    BookAppointmentCommand,
    NamedRef,
    ServiceTypeSummary,
    VehicleSummary,
)
from contexts.scheduling.application.errors import NotFoundError
from contexts.scheduling.domain.errors import (
    InvalidSlot,
    NoCapacityAvailable,
    OutsideOpeningHours,
    VehicleAlreadyBooked,
    VehicleNotOwnedByCustomer,
)
from contexts.scheduling.domain.events import AppointmentConfirmed
from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    AppointmentStatus,
    BayId,
    CustomerId,
    TechnicianId,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.services.resource_allocator import Allocation
from tests.unit.application.conftest import (
    BRAKE_SERVICE,
    DOWNTOWN,
    FULL_SERVICE,
    NOW,
    OIL_CHANGE,
    UPTOWN,
    World,
)
from tests.unit.domain.time_helpers import utc

MONDAY_9AM = utc(2026, 11, 2, 9)


def command(
    *,
    customer: int = 1,
    vehicle: int = 1,
    service_type: int = BRAKE_SERVICE,
    dealership: int = DOWNTOWN,
    start: datetime = MONDAY_9AM,
) -> BookAppointmentCommand:
    return BookAppointmentCommand(
        customer_id=customer,
        vehicle_id=vehicle,
        service_type_id=service_type,
        dealership_id=dealership,
        start_time=start,
    )


def competitor(bay: int, technician: int, start: datetime, minutes: int = 90) -> Appointment:
    """An appointment committed by a concurrent request."""
    return Appointment.schedule(
        appointment_id=AppointmentId(uuid.uuid4()),
        customer_id=CustomerId(3),
        vehicle_id=VehicleId(4),
        dealership_id=UPTOWN,
        service_type_id=BRAKE_SERVICE,
        allocation=Allocation(BayId(bay), TechnicianId(technician)),
        slot=TimeSlot.starting_at(start, timedelta(minutes=minutes)),
        now=NOW,
    )


class TestSuccessfulBooking:
    def test_returns_full_details_of_the_confirmed_appointment(self, world: World):
        details = world.book(command())

        assert details == AppointmentDetails(
            id=uuid.UUID(int=1),
            status="CONFIRMED",
            start_time=utc(2026, 11, 2, 9),
            end_time=utc(2026, 11, 2, 10, 30),
            customer=NamedRef(1, "Customer One"),
            vehicle=VehicleSummary(1, "1HGCM82633A004352"),
            service_type=ServiceTypeSummary(2, "Brake Service", 90),
            dealership=NamedRef(1, "Downtown Motors"),
            technician=NamedRef(2, "Bob"),
            service_bay=NamedRef(1, "Bay 1"),
        )

    def test_persists_appointment_linking_customer_vehicle_technician_bay(self, world: World):
        world.book(command())

        [stored] = world.store.appointments.values()
        assert stored.status is AppointmentStatus.CONFIRMED
        assert (stored.customer_id, stored.vehicle_id) == (1, 1)
        assert (stored.bay_id, stored.technician_id) == (1, 2)
        assert world.uow.commits == 1

    def test_publishes_confirmed_event_after_commit(self, world: World):
        world.book(command())

        [event] = world.publisher.published
        assert isinstance(event, AppointmentConfirmed)
        assert event.appointment_id == uuid.UUID(int=1)
        assert not world.publisher.published_inside_transaction

    def test_accepts_non_utc_start_times(self, world: World):
        start = datetime(2026, 11, 2, 4, tzinfo=timezone(timedelta(hours=-5)))

        details = world.book(command(start=start))

        assert details.start_time == utc(2026, 11, 2, 9)
        assert details.start_time.tzinfo == UTC


class TestAllocation:
    def test_least_loaded_qualified_technician_then_lowest_id(self, world: World):
        first = world.book(command(start=utc(2026, 11, 2, 9)))
        second = world.book(command(vehicle=3, customer=2, start=utc(2026, 11, 2, 13)))

        assert first.technician == NamedRef(2, "Bob")
        assert second.technician == NamedRef(3, "Chen")  # Bob already has one job that day

    def test_lowest_free_bay_is_used(self, world: World):
        world.book(command(start=utc(2026, 11, 2, 9)))

        second = world.book(command(vehicle=3, customer=2, start=utc(2026, 11, 2, 9)))

        assert second.service_bay == NamedRef(2, "Bay 2")
        assert second.technician == NamedRef(3, "Chen")

    def test_unqualified_technician_is_never_assigned(self, world: World):
        # Both brakes technicians (Bob, Chen) are busy; Alice is free but lacks the skill.
        world.book(command(start=utc(2026, 11, 2, 9)))
        world.book(command(vehicle=3, customer=2, start=utc(2026, 11, 2, 9)))

        with pytest.raises(NoCapacityAvailable):
            world.book(command(vehicle=4, customer=3, start=utc(2026, 11, 2, 9)))
        assert len(world.store.appointments) == 2


class TestCapacity:
    """Dealership 2 has exactly one bay and one technician (Dana)."""

    def test_back_to_back_bookings_on_the_same_resources_succeed(self, world: World):
        world.book(command(dealership=UPTOWN, start=utc(2026, 11, 2, 14)))
        world.book(
            command(dealership=UPTOWN, vehicle=3, customer=2, start=utc(2026, 11, 2, 15, 30))
        )

        assert len(world.store.confirmed()) == 2

    def test_overlapping_booking_is_rejected_and_nothing_is_persisted(self, world: World):
        world.book(command(dealership=UPTOWN, start=utc(2026, 11, 2, 14)))

        with pytest.raises(NoCapacityAvailable):
            world.book(
                command(dealership=UPTOWN, vehicle=3, customer=2, start=utc(2026, 11, 2, 15, 15))
            )
        assert len(world.store.appointments) == 1
        assert len(world.publisher.published) == 1

    def test_vehicle_cannot_be_double_booked_even_across_dealerships(self, world: World):
        world.book(command(dealership=DOWNTOWN, start=utc(2026, 11, 2, 15)))

        with pytest.raises(VehicleAlreadyBooked):
            world.book(command(dealership=UPTOWN, start=utc(2026, 11, 2, 15, 30)))


class TestValidation:
    @pytest.mark.parametrize(
        ("overrides", "resource"),
        [
            ({"service_type": 99}, "service_type"),
            ({"dealership": 99}, "dealership"),
            ({"customer": 99}, "customer"),
            ({"vehicle": 99}, "vehicle"),
        ],
    )
    def test_unknown_references_are_not_found(self, world: World, overrides, resource):
        with pytest.raises(NotFoundError) as raised:
            world.book(command(**overrides))

        assert raised.value.resource == resource
        assert raised.value.identifier == 99
        assert world.store.appointments == {}

    def test_vehicle_must_belong_to_customer(self, world: World):
        with pytest.raises(VehicleNotOwnedByCustomer):
            world.book(command(customer=2, vehicle=1))

    def test_start_in_the_past_is_invalid(self, world: World):
        with pytest.raises(InvalidSlot):
            world.book(command(start=utc(2026, 11, 1, 11, 45)))

    def test_start_off_the_grid_is_invalid(self, world: World):
        with pytest.raises(InvalidSlot):
            world.book(command(start=utc(2026, 11, 2, 9, 10)))

    def test_slot_running_past_closing_is_rejected(self, world: World):
        with pytest.raises(OutsideOpeningHours):
            world.book(command(service_type=FULL_SERVICE, start=utc(2026, 11, 2, 15, 15)))

    def test_rejections_publish_nothing_and_open_no_transaction(self, world: World):
        with pytest.raises(OutsideOpeningHours):
            world.book(command(service_type=OIL_CHANGE, start=utc(2026, 11, 2, 7)))

        assert world.publisher.published == []
        assert world.uow.commits == world.uow.rollbacks == 0


class TestRetryOnResourceConflict:
    def test_retries_after_a_conflict_and_succeeds(self, world: World):
        world.uow.injected_conflicts = [None]

        details = world.book(command())

        assert details.status == "CONFIRMED"
        assert world.uow.rollbacks == 1
        assert world.uow.commits == 1
        assert len(world.sleep.calls) == 1
        assert 0.01 <= world.sleep.calls[0] <= 0.05

    def test_retry_reallocates_around_the_concurrent_winner(self, world: World):
        # A concurrent request took Bay 1 with Bob between our check and our insert.
        world.uow.injected_conflicts = [competitor(bay=1, technician=2, start=utc(2026, 11, 2, 9))]

        details = world.book(command())

        assert details.service_bay == NamedRef(2, "Bay 2")
        assert details.technician == NamedRef(3, "Chen")

    def test_retry_reports_no_capacity_when_the_winner_took_the_last_slot(self, world: World):
        world.uow.injected_conflicts = [competitor(bay=4, technician=4, start=utc(2026, 11, 2, 14))]

        with pytest.raises(NoCapacityAvailable):
            world.book(command(dealership=UPTOWN, start=utc(2026, 11, 2, 14)))
        assert len(world.store.appointments) == 1  # only the competitor

    def test_gives_up_with_no_capacity_after_max_retries(self, world: World):
        world.uow.injected_conflicts = [None, None, None, None]

        with pytest.raises(NoCapacityAvailable):
            world.book(command())

        assert world.uow.rollbacks == 4  # first attempt + 3 retries
        assert len(world.sleep.calls) == 3
        assert world.store.appointments == {}
        assert world.publisher.published == []
