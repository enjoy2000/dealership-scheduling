"""The application handlers wired to the real infrastructure adapters."""

from collections.abc import Sequence

import pytest

from contexts.scheduling.application.commands.book_appointment import BookAppointmentHandler
from contexts.scheduling.application.commands.cancel_appointment import CancelAppointmentHandler
from contexts.scheduling.application.dto import (
    BookAppointmentCommand,
    CancelAppointmentCommand,
    NamedRef,
)
from contexts.scheduling.domain.errors import NoCapacityAvailable
from contexts.scheduling.infrastructure.catalog_gateway import DjangoCatalogGateway
from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from contexts.scheduling.infrastructure.persistence.unit_of_work import DjangoUnitOfWork
from shared_kernel.events import DomainEvent
from tests.unit.application.fakes import FixedClock
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")


class NullPublisher:
    def publish(self, events: Sequence[DomainEvent]) -> None:
        pass


def handlers() -> tuple[BookAppointmentHandler, CancelAppointmentHandler]:
    clock = FixedClock(utc(2026, 11, 1, 12))
    uow = DjangoUnitOfWork()
    book = BookAppointmentHandler(
        uow=uow, catalog=DjangoCatalogGateway(), clock=clock, events=NullPublisher()
    )
    cancel = CancelAppointmentHandler(uow=uow, clock=clock, events=NullPublisher())
    return book, cancel


def uptown(vehicle: int, customer: int) -> BookAppointmentCommand:
    return BookAppointmentCommand(
        customer_id=customer,
        vehicle_id=vehicle,
        service_type_id=2,
        dealership_id=2,
        start_time=utc(2026, 11, 2, 14),
    )


def test_book_conflict_cancel_rebook_against_postgres():
    book, cancel = handlers()

    first = book(uptown(vehicle=1, customer=1))
    assert first.technician == NamedRef(4, "Dana")
    assert first.service_bay == NamedRef(4, "Bay 1")

    with pytest.raises(NoCapacityAvailable):
        book(uptown(vehicle=3, customer=2))

    cancel(CancelAppointmentCommand(first.id))
    second = book(uptown(vehicle=3, customer=2))

    assert second.status == "CONFIRMED"
    assert AppointmentRecord.objects.filter(status="CONFIRMED").count() == 1
    assert AppointmentRecord.objects.count() == 2
