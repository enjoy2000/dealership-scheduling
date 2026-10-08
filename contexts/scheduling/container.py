"""Composition root: builds infrastructure adapters and injects them into handlers.

Views obtain handlers from `get_container()`. Tests may install their own instance
(e.g. with a fixed clock) via `set_container()`.
"""

import time
from collections.abc import Callable
from functools import cached_property

from django.conf import settings

from contexts.scheduling.application.commands.book_appointment import BookAppointmentHandler
from contexts.scheduling.application.commands.cancel_appointment import CancelAppointmentHandler
from contexts.scheduling.application.ports import Clock
from contexts.scheduling.infrastructure.catalog_gateway import DjangoCatalogGateway
from contexts.scheduling.infrastructure.clock import SystemClock
from contexts.scheduling.infrastructure.event_publisher import InProcessEventPublisher
from contexts.scheduling.infrastructure.persistence.unit_of_work import DjangoUnitOfWork


class Container:
    def __init__(
        self, *, clock: Clock | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.clock: Clock = clock or SystemClock()
        self.sleep = sleep
        self.uow = DjangoUnitOfWork()
        self.catalog = DjangoCatalogGateway()
        self.events = InProcessEventPublisher()

    @cached_property
    def book_appointment(self) -> BookAppointmentHandler:
        return BookAppointmentHandler(
            uow=self.uow,
            catalog=self.catalog,
            clock=self.clock,
            events=self.events,
            max_retries=settings.BOOKING_MAX_RETRIES,
            sleep=self.sleep,
        )

    @cached_property
    def cancel_appointment(self) -> CancelAppointmentHandler:
        return CancelAppointmentHandler(uow=self.uow, clock=self.clock, events=self.events)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def set_container(container: Container | None) -> None:
    global _container
    _container = container
