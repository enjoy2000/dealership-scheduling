from datetime import timedelta

from contexts.scheduling.domain.model.value_objects import BayId, TechnicianId, TimeSlot
from contexts.scheduling.domain.services.availability import AvailabilityCalculator, DaySchedule
from tests.unit.domain.time_helpers import utc

WINDOW = TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 12))  # 08:00-12:00
EARLY = utc(2026, 11, 1, 12)
calculator = AvailabilityCalculator()


def starts(slots: list[TimeSlot]) -> list[str]:
    return [s.start.strftime("%H:%M") for s in slots]


def schedule(bays=None, technicians=None) -> DaySchedule:
    return DaySchedule(
        bay_busy=bays if bays is not None else {BayId(1): []},
        technician_busy=technicians if technicians is not None else {TechnicianId(1): []},
    )


def busy(start_hour: int, start_minute: int, minutes: int) -> TimeSlot:
    return TimeSlot.starting_at(
        utc(2026, 11, 2, start_hour, start_minute), timedelta(minutes=minutes)
    )


def test_every_grid_start_that_fits_before_closing_is_offered():
    slots = calculator.free_slots(WINDOW, timedelta(minutes=90), EARLY, schedule())

    assert starts(slots)[0] == "08:00"
    assert starts(slots)[-1] == "10:30"  # 10:30 + 90 min == 12:00 closing
    assert len(slots) == 11
    assert slots[0] == busy(8, 0, 90)


def test_starts_in_the_past_are_dropped():
    now = utc(2026, 11, 2, 9, 10)

    slots = calculator.free_slots(WINDOW, timedelta(minutes=30), now, schedule())

    assert starts(slots)[0] == "09:15"


def test_start_equal_to_now_is_dropped():
    slots = calculator.free_slots(WINDOW, timedelta(minutes=30), utc(2026, 11, 2, 9), schedule())

    assert starts(slots)[0] == "09:15"


def test_slot_needs_a_free_bay_and_a_free_qualified_technician():
    day = schedule(
        bays={BayId(1): [busy(9, 0, 60)], BayId(2): []},
        technicians={TechnicianId(1): [busy(10, 0, 60)]},
    )

    slots = calculator.free_slots(WINDOW, timedelta(minutes=60), EARLY, day)

    # Bay 2 is always free, so only the technician's 10:00-11:00 job blocks starts.
    assert starts(slots) == ["08:00", "08:15", "08:30", "08:45", "09:00", "11:00"]


def test_back_to_back_with_existing_appointments_is_offered():
    day = schedule(bays={BayId(1): [busy(9, 0, 60)]}, technicians={TechnicianId(1): []})

    slots = calculator.free_slots(WINDOW, timedelta(minutes=60), EARLY, day)

    assert "08:00" in starts(slots)  # ends exactly when the 09:00 job starts
    assert "10:00" in starts(slots)  # starts exactly when it ends
    assert "08:15" not in starts(slots)


def test_no_bays_or_no_qualified_technicians_means_no_slots():
    assert calculator.free_slots(WINDOW, timedelta(minutes=30), EARLY, schedule(bays={})) == []
    assert (
        calculator.free_slots(WINDOW, timedelta(minutes=30), EARLY, schedule(technicians={})) == []
    )


def test_off_grid_opening_time_starts_at_the_next_grid_point():
    window = TimeSlot(utc(2026, 11, 2, 8, 10), utc(2026, 11, 2, 9))

    slots = calculator.free_slots(window, timedelta(minutes=30), EARLY, schedule())

    assert starts(slots) == ["08:15", "08:30"]


def test_service_longer_than_the_window_has_no_slots():
    window = TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 9))

    assert calculator.free_slots(window, timedelta(minutes=90), EARLY, schedule()) == []
