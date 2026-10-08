"""A world mirroring the §14.7 seed data, built from in-memory fakes."""

import itertools
import uuid
from dataclasses import dataclass
from datetime import time, timedelta
from zoneinfo import ZoneInfo

import pytest

from contexts.scheduling.application.commands.book_appointment import BookAppointmentHandler
from contexts.scheduling.application.commands.cancel_appointment import CancelAppointmentHandler
from contexts.scheduling.domain.model.references import (
    CustomerRef,
    DealershipCalendar,
    ServiceOffering,
    VehicleRef,
)
from contexts.scheduling.domain.model.resources import ServiceBay, Technician
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    BayId,
    CustomerId,
    DealershipId,
    OpeningHours,
    ServiceTypeId,
    Skill,
    TechnicianId,
    VehicleId,
    Vin,
)
from tests.unit.application.fakes import (
    FakeCatalogGateway,
    FakeUnitOfWork,
    FixedClock,
    RecordingEventPublisher,
    RecordingSleep,
    Store,
)
from tests.unit.domain.time_helpers import utc

NOW = utc(2026, 11, 1, 12)

DOWNTOWN = DealershipId(1)
UPTOWN = DealershipId(2)
OIL_CHANGE = ServiceTypeId(1)
BRAKE_SERVICE = ServiceTypeId(2)
FULL_SERVICE = ServiceTypeId(3)


def _technician(tech_id: int, dealership: DealershipId, name: str, *skills: str) -> Technician:
    return Technician(TechnicianId(tech_id), dealership, name, frozenset(Skill(s) for s in skills))


def seed_store() -> Store:
    return Store(
        bays=[
            ServiceBay(BayId(1), DOWNTOWN, "Bay 1"),
            ServiceBay(BayId(2), DOWNTOWN, "Bay 2"),
            ServiceBay(BayId(3), DOWNTOWN, "Bay 3"),
            ServiceBay(BayId(4), UPTOWN, "Bay 1"),
        ],
        technicians=[
            _technician(1, DOWNTOWN, "Alice", "oil_service", "general"),
            _technician(2, DOWNTOWN, "Bob", "brakes", "general"),
            _technician(3, DOWNTOWN, "Chen", "oil_service", "brakes"),
            _technician(4, UPTOWN, "Dana", "oil_service", "brakes", "general"),
        ],
    )


def seed_catalog() -> FakeCatalogGateway:
    return FakeCatalogGateway(
        offerings={
            OIL_CHANGE: ServiceOffering(
                OIL_CHANGE, "Oil Change", timedelta(minutes=30), Skill("oil_service")
            ),
            BRAKE_SERVICE: ServiceOffering(
                BRAKE_SERVICE, "Brake Service", timedelta(minutes=90), Skill("brakes")
            ),
            FULL_SERVICE: ServiceOffering(
                FULL_SERVICE, "Full Service", timedelta(minutes=120), Skill("general")
            ),
        },
        dealerships={
            DOWNTOWN: DealershipCalendar(
                DOWNTOWN,
                "Downtown Motors",
                OpeningHours(ZoneInfo("Europe/London"), time(8), time(17)),
            ),
            UPTOWN: DealershipCalendar(
                UPTOWN,
                "Uptown Auto",
                OpeningHours(ZoneInfo("America/New_York"), time(9), time(18)),
            ),
        },
        customers={
            CustomerId(1): CustomerRef(CustomerId(1), "Customer One"),
            CustomerId(2): CustomerRef(CustomerId(2), "Customer Two"),
            CustomerId(3): CustomerRef(CustomerId(3), "Customer Three"),
        },
        vehicles={
            VehicleId(1): VehicleRef(VehicleId(1), CustomerId(1), Vin("1HGCM82633A004352")),
            VehicleId(2): VehicleRef(VehicleId(2), CustomerId(1), Vin("5YJ3E1EA7KF317000")),
            VehicleId(3): VehicleRef(VehicleId(3), CustomerId(2), Vin("WVWZZZ1JZXW000001")),
            VehicleId(4): VehicleRef(VehicleId(4), CustomerId(3), Vin("3VWFE21C04M000001")),
        },
    )


def sequential_ids() -> "itertools.count[int]":
    return itertools.count(1)


@dataclass
class World:
    store: Store
    uow: FakeUnitOfWork
    catalog: FakeCatalogGateway
    clock: FixedClock
    publisher: RecordingEventPublisher
    sleep: RecordingSleep
    book: BookAppointmentHandler
    cancel: CancelAppointmentHandler


@pytest.fixture
def world() -> World:
    store = seed_store()
    uow = FakeUnitOfWork(store)
    catalog = seed_catalog()
    clock = FixedClock(NOW)
    publisher = RecordingEventPublisher(uow)
    sleep = RecordingSleep()
    counter = sequential_ids()
    book = BookAppointmentHandler(
        uow=uow,
        catalog=catalog,
        clock=clock,
        events=publisher,
        max_retries=3,
        sleep=sleep,
        new_id=lambda: AppointmentId(uuid.UUID(int=next(counter))),
    )
    cancel = CancelAppointmentHandler(uow=uow, clock=clock, events=publisher)
    return World(store, uow, catalog, clock, publisher, sleep, book, cancel)
