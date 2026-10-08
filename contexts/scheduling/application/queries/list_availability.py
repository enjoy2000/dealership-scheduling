"""Query: bookable start times for a dealership-local day (SPEC §14.4, A14)."""

from contexts.scheduling.application.dto import Availability, AvailableSlot, ListAvailabilityQuery
from contexts.scheduling.application.errors import NotFoundError
from contexts.scheduling.application.ports import (
    AvailabilityCache,
    AvailabilityReadModel,
    CatalogGateway,
    Clock,
)
from contexts.scheduling.domain.model.value_objects import DealershipId, ServiceTypeId
from contexts.scheduling.domain.services.availability import AvailabilityCalculator


class ListAvailabilityHandler:
    def __init__(
        self,
        *,
        read_model: AvailabilityReadModel,
        catalog: CatalogGateway,
        cache: AvailabilityCache,
        clock: Clock,
    ) -> None:
        self._read_model = read_model
        self._catalog = catalog
        self._cache = cache
        self._clock = clock
        self._calculator = AvailabilityCalculator()

    def __call__(self, query: ListAvailabilityQuery) -> Availability:
        cached = self._cache.get(query.dealership_id, query.service_type_id, query.date)
        if cached is not None:
            return cached

        offering = self._catalog.get_service_offering(ServiceTypeId(query.service_type_id))
        if offering is None:
            raise NotFoundError("service_type", query.service_type_id)
        dealership = self._catalog.get_dealership_calendar(DealershipId(query.dealership_id))
        if dealership is None:
            raise NotFoundError("dealership", query.dealership_id)

        window = dealership.opening_hours.window_on(query.date)
        schedule = self._read_model.day_schedule(dealership.id, offering.required_skill, window)
        slots = self._calculator.free_slots(window, offering.duration, self._clock.now(), schedule)
        result = Availability(
            dealership_id=dealership.id,
            service_type_id=offering.id,
            date=query.date,
            slots=tuple(AvailableSlot(s.start, s.end) for s in slots),
        )
        self._cache.set(result)
        return result
