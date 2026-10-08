import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError

from contexts.scheduling.domain.errors import ResourceConflict
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
from contexts.scheduling.infrastructure.persistence.repositories import (
    DjangoAppointmentRepository,
)
from tests.infrastructure.conftest import insert_appointment
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")

NOW = utc(2026, 11, 1, 12)
SLOT = TimeSlot.starting_at(utc(2026, 11, 2, 9), timedelta(minutes=90))
repo = DjangoAppointmentRepository()


def scheduled(
    *, bay: int = 1, technician: int = 2, vehicle: int = 1, slot: TimeSlot = SLOT
) -> Appointment:
    return Appointment.schedule(
        appointment_id=AppointmentId(uuid.uuid4()),
        customer_id=CustomerId(1),
        vehicle_id=VehicleId(vehicle),
        dealership_id=DealershipId(1),
        service_type_id=ServiceTypeId(2),
        allocation=Allocation(BayId(bay), TechnicianId(technician)),
        slot=slot,
        now=NOW,
    )


def test_add_then_get_round_trips_the_aggregate():
    appointment = scheduled()

    repo.add(appointment)
    loaded = repo.get(appointment.id)

    assert loaded is not None
    assert loaded.id == appointment.id
    assert loaded.slot == SLOT
    assert loaded.status is AppointmentStatus.CONFIRMED
    assert (loaded.bay_id, loaded.technician_id, loaded.vehicle_id) == (1, 2, 1)
    assert loaded.created_at == NOW
    assert loaded.pull_events() == []


def test_get_unknown_returns_none():
    assert repo.get(AppointmentId(uuid.uuid4())) is None


@pytest.mark.parametrize(
    "clash", [{"bay": 1, "technician": 3}, {"bay": 2, "technician": 2}, {"bay": 2, "vehicle": 1}]
)
def test_exclusion_violation_is_translated_to_resource_conflict(clash):
    repo.add(scheduled())
    params = {"bay": 2, "technician": 3, "vehicle": 2} | clash

    with pytest.raises(ResourceConflict):
        repo.add(scheduled(**params))


def test_other_integrity_errors_are_not_translated():
    appointment = scheduled()
    repo.add(appointment)
    duplicate_pk = scheduled(bay=2, technician=3, vehicle=2)
    duplicate_pk._id = appointment.id  # same primary key: a unique, not exclusion, violation

    with pytest.raises(IntegrityError) as raised:
        repo.add(duplicate_pk)
    assert not isinstance(raised.value, ResourceConflict)


def test_connection_is_usable_after_a_translated_conflict():
    repo.add(scheduled())
    with pytest.raises(ResourceConflict):
        repo.add(scheduled(bay=2, technician=2, vehicle=2))

    assert repo.get(AppointmentId(uuid.uuid4())) is None


def test_save_persists_cancellation():
    appointment = scheduled()
    repo.add(appointment)

    appointment.cancel(now=NOW)
    repo.save(appointment)

    loaded = repo.get(appointment.id)
    assert loaded is not None
    assert loaded.status is AppointmentStatus.CANCELLED
    assert loaded.cancelled_at == NOW


class TestVehicleHasOverlap:
    def test_true_for_overlapping_confirmed_appointment(self):
        insert_appointment(start=utc(2026, 11, 2, 10), vehicle=1)

        assert repo.vehicle_has_overlap(VehicleId(1), SLOT)

    def test_false_for_back_to_back(self):
        insert_appointment(start=utc(2026, 11, 2, 10, 30), vehicle=1)

        assert not repo.vehicle_has_overlap(VehicleId(1), SLOT)

    def test_false_for_cancelled_or_other_vehicle(self):
        insert_appointment(
            start=utc(2026, 11, 2, 9), vehicle=1, status="CANCELLED", cancelled_at=NOW
        )
        insert_appointment(start=utc(2026, 11, 2, 9), vehicle=2, bay=2, technician=3)

        assert not repo.vehicle_has_overlap(VehicleId(1), SLOT)
