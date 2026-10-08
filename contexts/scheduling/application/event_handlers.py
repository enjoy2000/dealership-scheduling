"""Reactions to domain events (dispatched after commit)."""

from contexts.scheduling.application.ports import AvailabilityCache, CatalogGateway
from contexts.scheduling.domain.events import AppointmentCancelled, AppointmentConfirmed
from shared_kernel.events import DomainEvent


class InvalidateAvailability:
    """Booking or cancelling changes availability for that dealership's local day (§14.4)."""

    def __init__(self, *, cache: AvailabilityCache, catalog: CatalogGateway) -> None:
        self._cache = cache
        self._catalog = catalog

    def __call__(self, event: DomainEvent) -> None:
        if not isinstance(event, AppointmentConfirmed | AppointmentCancelled):
            return
        dealership = self._catalog.get_dealership_calendar(event.dealership_id)
        if dealership is not None:
            day = dealership.opening_hours.local_date_of(event.slot.start)
            self._cache.invalidate(event.dealership_id, day)
