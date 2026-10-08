"""Use case: book an appointment (SPEC §4.5)."""

import logging
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from contexts.scheduling.application.dto import (
    AppointmentDetails,
    BookAppointmentCommand,
    NamedRef,
    ServiceTypeSummary,
    VehicleSummary,
)
from contexts.scheduling.application.errors import NotFoundError
from contexts.scheduling.application.ports import (
    BookingObserver,
    CatalogGateway,
    Clock,
    EventPublisher,
    UnitOfWork,
)
from contexts.scheduling.domain.errors import (
    NoCapacityAvailable,
    ResourceConflict,
    VehicleAlreadyBooked,
)
from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.references import (
    CustomerRef,
    DealershipCalendar,
    ServiceOffering,
    VehicleRef,
)
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    CustomerId,
    DealershipId,
    ServiceTypeId,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.policies.opening_hours import OpeningHoursPolicy
from contexts.scheduling.domain.policies.slot_alignment import SlotAlignmentPolicy
from contexts.scheduling.domain.services.resource_allocator import ResourceAllocator

BACKOFF_SECONDS = (0.01, 0.05)

logger = logging.getLogger(__name__)


class _NullObserver:
    def booking_conflict(self) -> None:
        pass

    def booking_retry(self, attempt: int) -> None:
        pass


def _new_appointment_id() -> AppointmentId:
    return AppointmentId(uuid.uuid4())


@dataclass(frozen=True)
class _BookingContext:
    customer: CustomerRef
    vehicle: VehicleRef
    offering: ServiceOffering
    dealership: DealershipCalendar
    slot: TimeSlot


class BookAppointmentHandler:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        catalog: CatalogGateway,
        clock: Clock,
        events: EventPublisher,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        new_id: Callable[[], AppointmentId] = _new_appointment_id,
        observer: BookingObserver | None = None,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._clock = clock
        self._events = events
        self._max_retries = max_retries
        self._sleep = sleep
        self._new_id = new_id
        self._observer: BookingObserver = observer or _NullObserver()
        self._allocator = ResourceAllocator()
        self._slot_alignment = SlotAlignmentPolicy()
        self._opening_hours = OpeningHoursPolicy()

    def __call__(self, command: BookAppointmentCommand) -> AppointmentDetails:
        context = self._validate(command)
        # The DB exclusion constraints are the final guard (D2): if a concurrent booking
        # wins the race, re-run allocation against the now-current state.
        for attempt in range(self._max_retries + 1):
            try:
                return self._book(context)
            except ResourceConflict as conflict:
                self._observer.booking_conflict()
                if attempt == self._max_retries:
                    raise NoCapacityAvailable() from conflict
                self._observer.booking_retry(attempt + 1)
                logger.info(
                    "booking.retry",
                    extra={"attempt": attempt + 1, "dealership_id": command.dealership_id},
                )
                self._sleep(random.uniform(*BACKOFF_SECONDS))
        raise AssertionError("unreachable")  # pragma: no cover

    def _validate(self, command: BookAppointmentCommand) -> _BookingContext:
        offering = self._catalog.get_service_offering(ServiceTypeId(command.service_type_id))
        if offering is None:
            raise NotFoundError("service_type", command.service_type_id)
        dealership = self._catalog.get_dealership_calendar(DealershipId(command.dealership_id))
        if dealership is None:
            raise NotFoundError("dealership", command.dealership_id)
        customer = self._catalog.get_customer(CustomerId(command.customer_id))
        if customer is None:
            raise NotFoundError("customer", command.customer_id)
        vehicle = self._catalog.get_vehicle(VehicleId(command.vehicle_id))
        if vehicle is None:
            raise NotFoundError("vehicle", command.vehicle_id)
        vehicle.ensure_owned_by(customer.id)

        self._slot_alignment.check(command.start_time, now=self._clock.now())
        slot = TimeSlot.starting_at(command.start_time, offering.duration)
        self._opening_hours.check(slot, dealership.opening_hours)
        return _BookingContext(customer, vehicle, offering, dealership, slot)

    def _book(self, ctx: _BookingContext) -> AppointmentDetails:
        hours = ctx.dealership.opening_hours
        with self._uow as uow:
            if uow.appointments.vehicle_has_overlap(ctx.vehicle.id, ctx.slot):
                raise VehicleAlreadyBooked()
            bays = uow.resources.find_available_bays(ctx.dealership.id, ctx.slot)
            technicians = uow.resources.find_available_technicians(
                ctx.dealership.id,
                ctx.offering.required_skill,
                ctx.slot,
                load_window=hours.window_on(hours.local_date_of(ctx.slot.start)),
            )
            allocation = self._allocator.allocate(ctx.offering.required_skill, bays, technicians)
            appointment = Appointment.schedule(
                appointment_id=self._new_id(),
                customer_id=ctx.customer.id,
                vehicle_id=ctx.vehicle.id,
                dealership_id=ctx.dealership.id,
                service_type_id=ctx.offering.id,
                allocation=allocation,
                slot=ctx.slot,
                now=self._clock.now(),
            )
            uow.appointments.add(appointment)
            uow.commit()

        self._events.publish(appointment.pull_events())
        bay = next(b for b in bays if b.id == allocation.bay_id)
        technician = next(
            t.technician for t in technicians if t.technician.id == allocation.technician_id
        )
        return AppointmentDetails(
            id=appointment.id,
            status=appointment.status.value,
            start_time=ctx.slot.start,
            end_time=ctx.slot.end,
            customer=NamedRef(ctx.customer.id, ctx.customer.name),
            vehicle=VehicleSummary(ctx.vehicle.id, str(ctx.vehicle.vin)),
            service_type=ServiceTypeSummary(
                ctx.offering.id, ctx.offering.name, ctx.offering.duration_minutes
            ),
            dealership=NamedRef(ctx.dealership.id, ctx.dealership.name),
            technician=NamedRef(technician.id, technician.name),
            service_bay=NamedRef(bay.id, bay.name),
        )
