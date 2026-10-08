"""Composition root: builds infrastructure adapters and injects them into handlers.

Views obtain handlers from `get_container()`. Tests may install their own instance
(e.g. with a fixed clock) via `set_container()`.
"""

import time
from collections.abc import Callable
from datetime import timedelta
from functools import cached_property

from django.conf import settings

from contexts.scheduling.application.commands.book_appointment import BookAppointmentHandler
from contexts.scheduling.application.commands.cancel_appointment import CancelAppointmentHandler
from contexts.scheduling.application.decorators import Idempotent, Instrumented, Replayable
from contexts.scheduling.application.dto import (
    AppointmentDetails,
    Availability,
    BookAppointmentCommand,
    CancelAppointmentCommand,
    GetAppointmentQuery,
    ListAvailabilityQuery,
)
from contexts.scheduling.application.event_handlers import InvalidateAvailability
from contexts.scheduling.application.ports import Clock
from contexts.scheduling.application.queries.get_appointment import GetAppointmentHandler
from contexts.scheduling.application.queries.list_availability import ListAvailabilityHandler
from contexts.scheduling.application.serialization import (
    appointment_details_from_json,
    appointment_details_to_json,
)
from contexts.scheduling.domain.events import AppointmentCancelled, AppointmentConfirmed
from contexts.scheduling.infrastructure.cache import DjangoAvailabilityCache
from contexts.scheduling.infrastructure.catalog_gateway import DjangoCatalogGateway
from contexts.scheduling.infrastructure.clock import SystemClock
from contexts.scheduling.infrastructure.event_publisher import InProcessEventPublisher
from contexts.scheduling.infrastructure.idempotency import DjangoIdempotencyStore
from contexts.scheduling.infrastructure.persistence.read_models import (
    DjangoAppointmentReadModel,
    DjangoAvailabilityReadModel,
)
from contexts.scheduling.infrastructure.persistence.unit_of_work import DjangoUnitOfWork
from contexts.scheduling.infrastructure.telemetry.metrics import PrometheusTelemetry


class Container:
    def __init__(
        self, *, clock: Clock | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.clock: Clock = clock or SystemClock()
        self.sleep = sleep
        self.uow = DjangoUnitOfWork()
        self.catalog = DjangoCatalogGateway()
        self.events = InProcessEventPublisher()
        self.telemetry = PrometheusTelemetry()
        self.availability_cache = DjangoAvailabilityCache(settings.AVAILABILITY_CACHE_TTL_SECONDS)
        invalidate = InvalidateAvailability(cache=self.availability_cache, catalog=self.catalog)
        self.events.subscribe(AppointmentConfirmed, invalidate)
        self.events.subscribe(AppointmentCancelled, invalidate)

    @cached_property
    def book_appointment(
        self,
    ) -> Callable[[str, BookAppointmentCommand], Replayable[AppointmentDetails]]:
        handler = BookAppointmentHandler(
            uow=self.uow,
            catalog=self.catalog,
            clock=self.clock,
            events=self.events,
            max_retries=settings.BOOKING_MAX_RETRIES,
            sleep=self.sleep,
            observer=self.telemetry,
        )
        idempotent = Idempotent(
            handler,
            store=DjangoIdempotencyStore(
                clock=self.clock, ttl=timedelta(hours=settings.IDEMPOTENCY_TTL_HOURS)
            ),
            transaction=self.uow,
            encode=appointment_details_to_json,
            decode=appointment_details_from_json,
            status=201,
        )
        return Instrumented("book_appointment", idempotent, telemetry=self.telemetry)

    @cached_property
    def cancel_appointment(self) -> Callable[[CancelAppointmentCommand], None]:
        handler = CancelAppointmentHandler(uow=self.uow, clock=self.clock, events=self.events)
        return Instrumented("cancel_appointment", handler, telemetry=self.telemetry)

    @cached_property
    def get_appointment(self) -> Callable[[GetAppointmentQuery], AppointmentDetails]:
        handler = GetAppointmentHandler(
            read_model=DjangoAppointmentReadModel(), catalog=self.catalog
        )
        return Instrumented("get_appointment", handler, telemetry=self.telemetry)

    @cached_property
    def list_availability(self) -> Callable[[ListAvailabilityQuery], Availability]:
        handler = ListAvailabilityHandler(
            read_model=DjangoAvailabilityReadModel(),
            catalog=self.catalog,
            cache=self.availability_cache,
            clock=self.clock,
        )
        return Instrumented("list_availability", handler, telemetry=self.telemetry)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def set_container(container: Container | None) -> None:
    global _container
    _container = container
