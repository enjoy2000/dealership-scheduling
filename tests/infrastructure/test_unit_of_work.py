import uuid
from datetime import timedelta

import pytest

from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    BayId,
    CustomerId,
    DealershipId,
    ServiceTypeId,
    TechnicianId,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.services.resource_allocator import Allocation
from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from contexts.scheduling.infrastructure.persistence.unit_of_work import DjangoUnitOfWork
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")


def appointment() -> Appointment:
    return Appointment.schedule(
        appointment_id=AppointmentId(uuid.uuid4()),
        customer_id=CustomerId(1),
        vehicle_id=VehicleId(1),
        dealership_id=DealershipId(1),
        service_type_id=ServiceTypeId(2),
        allocation=Allocation(BayId(1), TechnicianId(2)),
        slot=TimeSlot.starting_at(utc(2026, 11, 2, 9), timedelta(minutes=90)),
        now=utc(2026, 11, 1, 12),
    )


def test_commit_persists_changes():
    uow = DjangoUnitOfWork()
    with uow:
        uow.appointments.add(appointment())
        uow.commit()

    assert AppointmentRecord.objects.count() == 1


def test_leaving_without_commit_rolls_back():
    uow = DjangoUnitOfWork()
    with uow:
        uow.appointments.add(appointment())

    assert AppointmentRecord.objects.count() == 0


def test_exception_rolls_back():
    uow = DjangoUnitOfWork()

    def failing_work() -> None:
        with uow:
            uow.appointments.add(appointment())
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        failing_work()

    assert AppointmentRecord.objects.count() == 0


def test_explicit_rollback_discards_changes():
    uow = DjangoUnitOfWork()
    with uow:
        uow.appointments.add(appointment())
        uow.rollback()

    assert AppointmentRecord.objects.count() == 0


def test_unit_of_work_is_reusable():
    uow = DjangoUnitOfWork()
    with uow:
        uow.appointments.add(appointment())
    with uow:
        uow.appointments.add(appointment())
        uow.commit()

    assert AppointmentRecord.objects.count() == 1
