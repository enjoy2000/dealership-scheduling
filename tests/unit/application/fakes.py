"""In-memory fakes of the application ports. They mimic the database's exclusion
constraints so handlers can be tested without PostgreSQL."""

import copy
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

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
    CustomerId,
    DealershipId,
    ServiceTypeId,
    Skill,
    TimeSlot,
    VehicleId,
)
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

    def publish(self, events: Sequence[DomainEvent]) -> None:
        self.published_inside_transaction |= self._uow.in_transaction
        self.published.extend(events)


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
