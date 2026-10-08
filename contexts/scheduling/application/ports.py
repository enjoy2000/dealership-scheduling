"""Ports the application layer depends on; infrastructure provides the adapters."""

import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from types import TracebackType
from typing import Any, Protocol, Self

from contexts.scheduling.application.dto import AppointmentRow, Availability
from contexts.scheduling.domain.model.references import (
    CustomerRef,
    DealershipCalendar,
    ServiceOffering,
    VehicleRef,
)
from contexts.scheduling.domain.model.value_objects import (
    CustomerId,
    DealershipId,
    ServiceTypeId,
    Skill,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.repositories import AppointmentRepository, ResourceRepository
from contexts.scheduling.domain.services.availability import DaySchedule
from shared_kernel.clock import Clock
from shared_kernel.events import DomainEvent

__all__ = [
    "AppointmentReadModel",
    "AvailabilityCache",
    "AvailabilityReadModel",
    "BookingObserver",
    "CatalogGateway",
    "Clock",
    "EventPublisher",
    "IdempotencyStore",
    "StoredResponse",
    "Transaction",
    "UnitOfWork",
    "UseCaseTelemetry",
]


class Transaction(Protocol):
    """A database transaction. Leaving the block without `commit()` rolls back.
    Nested use becomes a savepoint."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class UnitOfWork(Transaction, Protocol):
    """A transaction that also exposes the Scheduling repositories."""

    @property
    def appointments(self) -> AppointmentRepository: ...

    @property
    def resources(self) -> ResourceRepository: ...


class CatalogGateway(Protocol):
    """Anti-corruption layer over the Catalog context. Returns None for unknown ids."""

    def get_service_offering(self, service_type_id: ServiceTypeId) -> ServiceOffering | None: ...

    def get_dealership_calendar(self, dealership_id: DealershipId) -> DealershipCalendar | None: ...

    def get_customer(self, customer_id: CustomerId) -> CustomerRef | None: ...

    def get_vehicle(self, vehicle_id: VehicleId) -> VehicleRef | None: ...


class EventPublisher(Protocol):
    """Dispatches domain events in-process, called only after commit."""

    def publish(self, events: Sequence[DomainEvent]) -> None: ...


class AppointmentReadModel(Protocol):
    """CQRS-lite read side (D5): reads bypass the aggregate."""

    def get(self, appointment_id: uuid.UUID) -> AppointmentRow | None: ...


class AvailabilityReadModel(Protocol):
    def day_schedule(
        self, dealership_id: DealershipId, skill: Skill, window: TimeSlot
    ) -> DaySchedule:
        """All bays and all technicians holding `skill` at the dealership, each with the
        confirmed appointments overlapping `window`. A small, fixed number of queries."""
        ...


class AvailabilityCache(Protocol):
    """Short-lived cache of availability listings (A14). Entries may be up to the TTL stale;
    booking always re-validates against the database."""

    def get(self, dealership_id: int, service_type_id: int, day: date) -> Availability | None: ...

    def set(self, value: Availability) -> None: ...

    def invalidate(self, dealership_id: int, day: date) -> None: ...


@dataclass(frozen=True)
class StoredResponse:
    request_hash: str
    status: int | None
    body: dict[str, Any] | None


class IdempotencyStore(Protocol):
    """Idempotency keys (SPEC §14.5). `reserve` and `complete` must run inside the same
    transaction as the use case, so a concurrent duplicate loses on the unique key."""

    def find(self, key: str) -> StoredResponse | None:
        """A completed, unexpired response for `key`, if any."""
        ...

    def reserve(self, key: str, request_hash: str) -> None:
        """Claim `key`. Raises `IdempotencyConflictError` if it is already taken."""
        ...

    def complete(self, key: str, status: int, body: dict[str, Any]) -> None: ...


class UseCaseTelemetry(Protocol):
    """Tracing span + metrics for one use-case invocation (SPEC §9)."""

    def span(
        self, use_case: str, attributes: Mapping[str, object]
    ) -> AbstractContextManager[None]: ...

    def record(self, use_case: str, outcome: str, duration_seconds: float) -> None:
        """Called inside the span once the outcome is known."""
        ...


class BookingObserver(Protocol):
    """Contention signals from inside the booking use case."""

    def booking_conflict(self) -> None: ...

    def booking_retry(self, attempt: int) -> None: ...
