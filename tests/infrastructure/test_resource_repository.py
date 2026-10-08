from datetime import timedelta

import pytest

from contexts.scheduling.domain.model.value_objects import DealershipId, Skill, TimeSlot
from contexts.scheduling.infrastructure.persistence.repositories import DjangoResourceRepository
from tests.infrastructure.conftest import insert_appointment
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")

DOWNTOWN = DealershipId(1)
SLOT = TimeSlot.starting_at(utc(2026, 11, 2, 9), timedelta(minutes=90))
DAY = TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 17))
repo = DjangoResourceRepository()


def test_all_bays_of_the_dealership_are_free_initially():
    bays = repo.find_available_bays(DOWNTOWN, SLOT)

    assert [(b.id, b.name, b.dealership_id) for b in bays] == [
        (1, "Bay 1", 1),
        (2, "Bay 2", 1),
        (3, "Bay 3", 1),
    ]


def test_busy_bay_is_excluded_but_back_to_back_is_free():
    insert_appointment(start=utc(2026, 11, 2, 10), bay=1)
    insert_appointment(start=utc(2026, 11, 2, 7), minutes=120, bay=2, technician=3, vehicle=2)

    assert [b.id for b in repo.find_available_bays(DOWNTOWN, SLOT)] == [2, 3]


def test_cancelled_appointments_do_not_occupy_bays():
    insert_appointment(start=utc(2026, 11, 2, 9), status="CANCELLED", cancelled_at=utc(2026, 11, 1))

    assert len(repo.find_available_bays(DOWNTOWN, SLOT)) == 3


def test_only_qualified_technicians_with_their_skills():
    technicians = repo.find_available_technicians(DOWNTOWN, Skill("brakes"), SLOT, DAY)

    assert [(t.technician.name, t.load) for t in technicians] == [("Bob", 0), ("Chen", 0)]
    assert technicians[0].technician.skills == frozenset({Skill("brakes"), Skill("general")})


def test_busy_technician_is_excluded():
    insert_appointment(start=utc(2026, 11, 2, 9, 45), technician=2)

    technicians = repo.find_available_technicians(DOWNTOWN, Skill("brakes"), SLOT, DAY)

    assert [t.technician.name for t in technicians] == ["Chen"]


def test_load_counts_confirmed_appointments_within_the_window_only():
    insert_appointment(start=utc(2026, 11, 2, 13), technician=2, vehicle=1)
    insert_appointment(start=utc(2026, 11, 2, 15), technician=2, vehicle=2, bay=2)
    insert_appointment(  # cancelled: not counted
        start=utc(2026, 11, 2, 11),
        technician=2,
        vehicle=3,
        customer=2,
        status="CANCELLED",
        cancelled_at=utc(2026, 11, 1),
    )
    insert_appointment(start=utc(2026, 11, 3, 9), technician=2, vehicle=1)  # another day

    technicians = repo.find_available_technicians(DOWNTOWN, Skill("brakes"), SLOT, DAY)

    assert {t.technician.name: t.load for t in technicians} == {"Bob": 2, "Chen": 0}


def test_other_dealerships_resources_are_never_returned():
    uptown = DealershipId(2)
    slot = TimeSlot.starting_at(utc(2026, 11, 2, 14), timedelta(minutes=90))
    window = TimeSlot(utc(2026, 11, 2, 14), utc(2026, 11, 2, 23))

    assert [b.name for b in repo.find_available_bays(uptown, slot)] == ["Bay 1"]
    assert [
        t.technician.name
        for t in repo.find_available_technicians(uptown, Skill("brakes"), slot, window)
    ] == ["Dana"]
