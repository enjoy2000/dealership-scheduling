import uuid
from datetime import timedelta

import pytest

from contexts.scheduling.domain.errors import AppointmentAlreadyCancelled, CancellationNotAllowed
from contexts.scheduling.domain.events import AppointmentCancelled, AppointmentConfirmed
from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    AppointmentStatus,
    BayId,
    CustomerId,
    DealershipId,
    ServiceTypeId,
    TechnicianId,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.services.resource_allocator import Allocation
from tests.unit.domain.time_helpers import utc

BOOKED_AT = utc(2026, 11, 1, 12)
SLOT = TimeSlot.starting_at(utc(2026, 11, 2, 9), timedelta(minutes=90))
APPOINTMENT_ID = AppointmentId(uuid.UUID("5b1e8c1a-6d2f-4a35-9b0e-0f4f2f1c9a11"))


def schedule() -> Appointment:
    return Appointment.schedule(
        appointment_id=APPOINTMENT_ID,
        customer_id=CustomerId(1),
        vehicle_id=VehicleId(1),
        dealership_id=DealershipId(1),
        service_type_id=ServiceTypeId(2),
        allocation=Allocation(bay_id=BayId(1), technician_id=TechnicianId(2)),
        slot=SLOT,
        now=BOOKED_AT,
    )


class TestSchedule:
    def test_creates_confirmed_appointment_linking_all_parties(self):
        appointment = schedule()

        assert appointment.id == APPOINTMENT_ID
        assert appointment.status is AppointmentStatus.CONFIRMED
        assert appointment.customer_id == CustomerId(1)
        assert appointment.vehicle_id == VehicleId(1)
        assert appointment.dealership_id == DealershipId(1)
        assert appointment.service_type_id == ServiceTypeId(2)
        assert appointment.bay_id == BayId(1)
        assert appointment.technician_id == TechnicianId(2)
        assert appointment.slot == SLOT
        assert appointment.created_at == BOOKED_AT
        assert appointment.cancelled_at is None

    def test_records_appointment_confirmed(self):
        appointment = schedule()

        assert appointment.pull_events() == [
            AppointmentConfirmed(
                appointment_id=APPOINTMENT_ID,
                dealership_id=DealershipId(1),
                vehicle_id=VehicleId(1),
                bay_id=BayId(1),
                technician_id=TechnicianId(2),
                slot=SLOT,
                occurred_at=BOOKED_AT,
            )
        ]

    def test_pull_events_drains_the_queue(self):
        appointment = schedule()
        appointment.pull_events()

        assert appointment.pull_events() == []


class TestCancel:
    def test_cancel_before_start_frees_the_appointment(self):
        appointment = schedule()
        appointment.pull_events()
        cancel_time = utc(2026, 11, 2, 8, 59)

        appointment.cancel(now=cancel_time)

        assert appointment.status is AppointmentStatus.CANCELLED
        assert appointment.cancelled_at == cancel_time
        assert appointment.pull_events() == [
            AppointmentCancelled(
                appointment_id=APPOINTMENT_ID,
                dealership_id=DealershipId(1),
                slot=SLOT,
                occurred_at=cancel_time,
            )
        ]

    def test_cancelling_twice_is_rejected_and_records_nothing(self):
        appointment = schedule()
        appointment.cancel(now=BOOKED_AT)
        appointment.pull_events()

        with pytest.raises(AppointmentAlreadyCancelled):
            appointment.cancel(now=BOOKED_AT)
        assert appointment.pull_events() == []

    @pytest.mark.parametrize("cancel_time", [SLOT.start, SLOT.start + timedelta(minutes=1)])
    def test_cancel_at_or_after_start_is_not_allowed(self, cancel_time):
        appointment = schedule()

        with pytest.raises(CancellationNotAllowed):
            appointment.cancel(now=cancel_time)
        assert appointment.status is AppointmentStatus.CONFIRMED


def test_reconstituted_appointment_has_no_pending_events():
    appointment = Appointment(
        id=APPOINTMENT_ID,
        customer_id=CustomerId(1),
        vehicle_id=VehicleId(1),
        dealership_id=DealershipId(1),
        service_type_id=ServiceTypeId(2),
        bay_id=BayId(1),
        technician_id=TechnicianId(2),
        slot=SLOT,
        status=AppointmentStatus.CANCELLED,
        created_at=BOOKED_AT,
        cancelled_at=BOOKED_AT,
    )

    assert appointment.pull_events() == []
    assert appointment.is_cancelled


def test_cancelled_appointment_requires_cancelled_at():
    with pytest.raises(ValueError, match="cancelled_at"):
        Appointment(
            id=APPOINTMENT_ID,
            customer_id=CustomerId(1),
            vehicle_id=VehicleId(1),
            dealership_id=DealershipId(1),
            service_type_id=ServiceTypeId(2),
            bay_id=BayId(1),
            technician_id=TechnicianId(2),
            slot=SLOT,
            status=AppointmentStatus.CANCELLED,
            created_at=BOOKED_AT,
            cancelled_at=None,
        )
