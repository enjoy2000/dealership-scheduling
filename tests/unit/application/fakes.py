"""In-memory fakes of the application ports. They mimic the database's exclusion
constraints so handlers can be tested without PostgreSQL."""

import copy
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from types import TracebackType
from typing import Self

from contexts.scheduling.application.dto import AppointmentRow, Availability, NamedRef
from contexts.scheduling.domain.errors import ResourceConflict
from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.references import (
    CustomerRef,
    DealershipCalendar,
    ServiceOffering,
    VehicleRef,
)
from contexts.scheduling.domain.model.resources import ServiceBay, Technician, TechnicianLoad
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    BayId,
    CustomerId,
    DealershipId,
    ServiceTypeId,
    Skill,
    TechnicianId,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.services.availability import DaySchedule
from shared_kernel.events import DomainEvent


def _clashes(a: Appointment, b: Appointment) -> bool:
    shares_resource = (
        a.bay_id == b.bay_id or a.technician_id == b.technician_id or a.vehicle_id == b.vehicle_id
    )
    return shares_resource and a.slot.overlaps(b.slot)


@dataclass
class Store:
    """Committed state, shared by successive units of work."""

    bays: list[ServiceBay] = field(default_factory=list)
    technicians: list[Technician] = field(default_factory=list)
    appointments: dict[AppointmentId, Appointment] = field(default_factory=dict)

    def confirmed(self) -> list[Appointment]:
        return [a for a in self.appointments.values() if not a.is_cancelled]


class FakeAppointmentRepository:
    def __init__(self, uow: "FakeUnitOfWork") -> None:
        self._uow = uow

    @property
    def _working(self) -> dict[AppointmentId, Appointment]:
        return self._uow.working

    def add(self, appointment: Appointment) -> None:
        if self._uow.injected_conflicts:
            competitor = self._uow.injected_conflicts.pop(0)
            if competitor is not None:
                # A concurrent transaction committed first.
                self._uow.store.appointments[competitor.id] = copy.deepcopy(competitor)
            raise ResourceConflict()
        confirmed = [a for a in self._working.values() if not a.is_cancelled]
        if any(_clashes(appointment, other) for other in confirmed):
            raise ResourceConflict()
        self._working[appointment.id] = appointment

    def save(self, appointment: Appointment) -> None:
        self._working[appointment.id] = appointment

    def get(self, appointment_id: AppointmentId) -> Appointment | None:
        return self._working.get(appointment_id)

    def vehicle_has_overlap(self, vehicle_id: VehicleId, slot: TimeSlot) -> bool:
        return any(
            a.vehicle_id == vehicle_id and not a.is_cancelled and a.slot.overlaps(slot)
            for a in self._working.values()
        )


class FakeResourceRepository:
    def __init__(self, uow: "FakeUnitOfWork") -> None:
        self._uow = uow

    def _busy(self, slot: TimeSlot) -> list[Appointment]:
        return [
            a for a in self._uow.working.values() if not a.is_cancelled and a.slot.overlaps(slot)
        ]

    def find_available_bays(
        self, dealership_id: DealershipId, slot: TimeSlot
    ) -> Sequence[ServiceBay]:
        busy = {a.bay_id for a in self._busy(slot)}
        return [
            b for b in self._uow.store.bays if b.dealership_id == dealership_id and b.id not in busy
        ]

    def find_available_technicians(
        self, dealership_id: DealershipId, skill: Skill, slot: TimeSlot, load_window: TimeSlot
    ) -> Sequence[TechnicianLoad]:
        busy = {a.technician_id for a in self._busy(slot)}
        loads = []
        for technician in self._uow.store.technicians:
            if (
                technician.dealership_id != dealership_id
                or technician.id in busy
                or not technician.is_qualified_for(skill)
            ):
                continue
            load = sum(
                1
                for a in self._uow.working.values()
                if a.technician_id == technician.id
                and not a.is_cancelled
                and load_window.contains(a.slot)
            )
            loads.append(TechnicianLoad(technician, load))
        return loads


class FakeUnitOfWork:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.working: dict[AppointmentId, Appointment] = {}
        self.appointments = FakeAppointmentRepository(self)
        self.resources = FakeResourceRepository(self)
        self.commits = 0
        self.rollbacks = 0
        self.in_transaction = False
        # Each entry makes one `add` raise ResourceConflict; a non-None entry is a
        # competing appointment committed by "another transaction" just before.
        self.injected_conflicts: list[Appointment | None] = []

    def __enter__(self) -> Self:
        self.working = copy.deepcopy(self.store.appointments)
        self.in_transaction = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.in_transaction:
            self.rollback()

    def commit(self) -> None:
        self.store.appointments = self.working
        self.commits += 1
        self.in_transaction = False

    def rollback(self) -> None:
        self.working = {}
        self.rollbacks += 1
        self.in_transaction = False


@dataclass
class FakeCatalogGateway:
    offerings: dict[ServiceTypeId, ServiceOffering] = field(default_factory=dict)
    dealerships: dict[DealershipId, DealershipCalendar] = field(default_factory=dict)
    customers: dict[CustomerId, CustomerRef] = field(default_factory=dict)
    vehicles: dict[VehicleId, VehicleRef] = field(default_factory=dict)

    def get_service_offering(self, service_type_id: ServiceTypeId) -> ServiceOffering | None:
        return self.offerings.get(service_type_id)

    def get_dealership_calendar(self, dealership_id: DealershipId) -> DealershipCalendar | None:
        return self.dealerships.get(dealership_id)

    def get_customer(self, customer_id: CustomerId) -> CustomerRef | None:
        return self.customers.get(customer_id)

    def get_vehicle(self, vehicle_id: VehicleId) -> VehicleRef | None:
        return self.vehicles.get(vehicle_id)


@dataclass
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class RecordingEventPublisher:
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow
        self.published: list[DomainEvent] = []
        self.published_inside_transaction = False
        self.subscribers: list[Callable[[DomainEvent], None]] = []

    def publish(self, events: Sequence[DomainEvent]) -> None:
        self.published_inside_transaction |= self._uow.in_transaction
        self.published.extend(events)
        for event in events:
            for subscriber in self.subscribers:
                subscriber(event)


class FakeAppointmentReadModel:
    def __init__(self, store: Store) -> None:
        self._store = store

    def get(self, appointment_id: uuid.UUID) -> AppointmentRow | None:
        appointment = self._store.appointments.get(AppointmentId(appointment_id))
        if appointment is None:
            return None
        bay = next(b for b in self._store.bays if b.id == appointment.bay_id)
        tech = next(t for t in self._store.technicians if t.id == appointment.technician_id)
        return AppointmentRow(
            id=appointment.id,
            status=appointment.status.value,
            start_time=appointment.slot.start,
            end_time=appointment.slot.end,
            customer_id=appointment.customer_id,
            vehicle_id=appointment.vehicle_id,
            service_type_id=appointment.service_type_id,
            dealership_id=appointment.dealership_id,
            technician=NamedRef(tech.id, tech.name),
            service_bay=NamedRef(bay.id, bay.name),
        )


class FakeAvailabilityReadModel:
    def __init__(self, store: Store) -> None:
        self._store = store
        self.calls = 0

    def day_schedule(
        self, dealership_id: DealershipId, skill: Skill, window: TimeSlot
    ) -> DaySchedule:
        self.calls += 1
        bay_busy: dict[BayId, list[TimeSlot]] = {
            b.id: [] for b in self._store.bays if b.dealership_id == dealership_id
        }
        tech_busy: dict[TechnicianId, list[TimeSlot]] = {
            t.id: []
            for t in self._store.technicians
            if t.dealership_id == dealership_id and t.is_qualified_for(skill)
        }
        for a in self._store.confirmed():
            if a.dealership_id == dealership_id and a.slot.overlaps(window):
                if a.bay_id in bay_busy:
                    bay_busy[a.bay_id].append(a.slot)
                if a.technician_id in tech_busy:
                    tech_busy[a.technician_id].append(a.slot)
        return DaySchedule(bay_busy, tech_busy)


class FakeAvailabilityCache:
    def __init__(self) -> None:
        self.entries: dict[tuple[int, int, date], Availability] = {}
        self.invalidations: defaultdict[tuple[int, date], int] = defaultdict(int)

    def get(self, dealership_id: int, service_type_id: int, day: date) -> Availability | None:
        return self.entries.get((dealership_id, service_type_id, day))

    def set(self, value: Availability) -> None:
        self.entries[(value.dealership_id, value.service_type_id, value.date)] = value

    def invalidate(self, dealership_id: int, day: date) -> None:
        self.invalidations[(dealership_id, day)] += 1
        for key in [k for k in self.entries if (k[0], k[2]) == (dealership_id, day)]:
            del self.entries[key]


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
