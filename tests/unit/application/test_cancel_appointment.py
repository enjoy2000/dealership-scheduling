import uuid

import pytest

from contexts.scheduling.application.dto import BookAppointmentCommand, CancelAppointmentCommand
from contexts.scheduling.application.errors import NotFoundError
from contexts.scheduling.domain.errors import CancellationNotAllowed
from contexts.scheduling.domain.events import AppointmentCancelled
from contexts.scheduling.domain.model.value_objects import AppointmentId, AppointmentStatus
from tests.unit.application.conftest import BRAKE_SERVICE, UPTOWN, World
from tests.unit.domain.time_helpers import utc


def book_uptown(world: World, vehicle: int = 1, customer: int = 1) -> uuid.UUID:
    details = world.book(
        BookAppointmentCommand(
            customer_id=customer,
            vehicle_id=vehicle,
            service_type_id=BRAKE_SERVICE,
            dealership_id=UPTOWN,
            start_time=utc(2026, 11, 2, 14),
        )
    )
    world.publisher.published.clear()
    return details.id


def test_cancel_marks_appointment_cancelled_and_publishes_event(world: World):
    appointment_id = book_uptown(world)

    world.cancel(CancelAppointmentCommand(appointment_id))

    stored = world.store.appointments[AppointmentId(appointment_id)]
    assert stored.status is AppointmentStatus.CANCELLED
    assert stored.cancelled_at == world.clock.now()
    [event] = world.publisher.published
    assert isinstance(event, AppointmentCancelled)
    assert not world.publisher.published_inside_transaction


def test_cancelling_frees_bay_and_technician(world: World):
    book_uptown(world)
    appointment_id = next(iter(world.store.appointments))
    world.cancel(CancelAppointmentCommand(appointment_id))

    book_uptown(world, vehicle=3, customer=2)

    assert len(world.store.confirmed()) == 1


def test_cancel_is_idempotent(world: World):
    appointment_id = book_uptown(world)
    world.cancel(CancelAppointmentCommand(appointment_id))
    first_cancelled_at = world.clock.now()
    world.publisher.published.clear()
    commits = world.uow.commits
    world.clock.current = utc(2026, 11, 1, 13)

    world.cancel(CancelAppointmentCommand(appointment_id))

    stored = world.store.appointments[AppointmentId(appointment_id)]
    assert stored.status is AppointmentStatus.CANCELLED
    assert stored.cancelled_at == first_cancelled_at
    assert world.uow.commits == commits
    assert world.publisher.published == []


def test_cancel_unknown_appointment_is_not_found(world: World):
    missing = uuid.UUID(int=999)

    with pytest.raises(NotFoundError) as raised:
        world.cancel(CancelAppointmentCommand(missing))

    assert raised.value.resource == "appointment"


@pytest.mark.parametrize("now", [utc(2026, 11, 2, 14), utc(2026, 11, 2, 14, 30)])
def test_cancel_at_or_after_start_is_not_allowed(world: World, now):
    appointment_id = book_uptown(world)
    world.clock.current = now

    with pytest.raises(CancellationNotAllowed):
        world.cancel(CancelAppointmentCommand(appointment_id))

    stored = world.store.appointments[AppointmentId(appointment_id)]
    assert stored.status is AppointmentStatus.CONFIRMED
    assert world.publisher.published == []
