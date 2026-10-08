"""Ports the application layer depends on; infrastructure provides the adapters.

Idempotency and availability-cache ports arrive with milestones 6 and 7.
"""

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol, Self

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
    VehicleId,
)
from contexts.scheduling.domain.repositories import AppointmentRepository, ResourceRepository
from shared_kernel.clock import Clock
from shared_kernel.events import DomainEvent

__all__ = ["CatalogGateway", "Clock", "EventPublisher", "UnitOfWork"]


class UnitOfWork(Protocol):
    """One database transaction. Leaving the block without `commit()` rolls back."""

    @property
    def appointments(self) -> AppointmentRepository: ...

    @property
    def resources(self) -> ResourceRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class CatalogGateway(Protocol):
    """Anti-corruption layer over the Catalog context. Returns None for unknown ids."""

    def get_service_offering(self, service_type_id: ServiceTypeId) -> ServiceOffering | None: ...

    def get_dealership_calendar(self, dealership_id: DealershipId) -> DealershipCalendar | None: ...

    def get_customer(self, customer_id: CustomerId) -> CustomerRef | None: ...

    def get_vehicle(self, vehicle_id: VehicleId) -> VehicleRef | None: ...


class EventPublisher(Protocol):
    """Dispatches domain events in-process, called only after commit."""

    def publish(self, events: Sequence[DomainEvent]) -> None: ...
