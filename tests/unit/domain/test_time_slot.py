from datetime import datetime, timedelta, timezone

import pytest

from contexts.scheduling.domain.errors import InvalidSlot
from contexts.scheduling.domain.model.value_objects import TimeSlot
from tests.unit.domain.time_helpers import utc


def test_slot_requires_end_after_start():
    with pytest.raises(InvalidSlot):
        TimeSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 9))
    with pytest.raises(InvalidSlot):
        TimeSlot(utc(2026, 11, 2, 10), utc(2026, 11, 2, 9))


def test_slot_rejects_naive_datetimes():
    with pytest.raises(InvalidSlot):
        TimeSlot(datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))


def test_slot_is_normalised_to_utc():
    plus_one = timezone(timedelta(hours=1))
    slot = TimeSlot(datetime(2026, 11, 2, 10, tzinfo=plus_one), utc(2026, 11, 2, 10))

    assert slot.start == utc(2026, 11, 2, 9)
    assert slot.start.utcoffset() == timedelta(0)
    assert slot == TimeSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 10))


def test_starting_at_builds_slot_from_duration():
    slot = TimeSlot.starting_at(utc(2026, 11, 2, 9), timedelta(minutes=90))

    assert slot.end == utc(2026, 11, 2, 10, 30)
    assert slot.duration == timedelta(minutes=90)


def test_back_to_back_slots_do_not_overlap():
    first = TimeSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 10))
    second = TimeSlot(utc(2026, 11, 2, 10), utc(2026, 11, 2, 11))

    assert not first.overlaps(second)
    assert not second.overlaps(first)


def test_one_minute_overlap_is_detected():
    first = TimeSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 10))
    second = TimeSlot(utc(2026, 11, 2, 9, 59), utc(2026, 11, 2, 11))

    assert first.overlaps(second)
    assert second.overlaps(first)


def test_containing_slot_overlaps():
    outer = TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 12))
    inner = TimeSlot(utc(2026, 11, 2, 9), utc(2026, 11, 2, 10))

    assert outer.overlaps(inner)
    assert outer.contains(inner)
    assert not inner.contains(outer)


def test_contains_includes_shared_boundaries():
    window = TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 17))

    assert window.contains(TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 17)))
    assert not window.contains(TimeSlot(utc(2026, 11, 2, 16, 45), utc(2026, 11, 2, 17, 15)))
