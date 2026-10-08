from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from contexts.scheduling.domain.errors import OutsideOpeningHours
from contexts.scheduling.domain.model.value_objects import OpeningHours, TimeSlot
from contexts.scheduling.domain.policies.opening_hours import OpeningHoursPolicy
from tests.unit.domain.time_helpers import utc

policy = OpeningHoursPolicy()


def slot(start: datetime, minutes: int) -> TimeSlot:
    return TimeSlot.starting_at(start, timedelta(minutes=minutes))


def test_opening_hours_require_close_after_open():
    with pytest.raises(ValueError, match="close"):
        OpeningHours(ZoneInfo("Europe/London"), time(17, 0), time(8, 0))


class TestLondonWinter:
    """2026-11-02: London is on GMT (UTC+0)."""

    def test_slot_starting_at_opening_is_accepted(self, london_hours):
        policy.check(slot(utc(2026, 11, 2, 8), 30), london_hours)

    def test_slot_ending_exactly_at_close_is_accepted(self, london_hours):
        policy.check(slot(utc(2026, 11, 2, 15, 30), 90), london_hours)

    def test_slot_starting_before_opening_is_rejected(self, london_hours):
        with pytest.raises(OutsideOpeningHours):
            policy.check(slot(utc(2026, 11, 2, 7, 45), 30), london_hours)

    def test_slot_running_past_close_is_rejected(self, london_hours):
        with pytest.raises(OutsideOpeningHours):
            policy.check(slot(utc(2026, 11, 2, 16, 45), 30), london_hours)


class TestLondonSummer:
    """2026-06-01: London is on BST (UTC+1), so 08:00 local is 07:00Z."""

    def test_local_opening_is_an_hour_earlier_in_utc(self, london_hours):
        policy.check(slot(utc(2026, 6, 1, 7), 30), london_hours)

    def test_utc_eight_to_five_is_not_local_opening_hours(self, london_hours):
        with pytest.raises(OutsideOpeningHours):
            policy.check(slot(utc(2026, 6, 1, 16), 30), london_hours)


class TestDstTransitionDays:
    def test_spring_forward_day_uses_bst(self, london_hours):
        # 2026-03-29 clocks go forward at 01:00 UTC; 08:00 BST == 07:00Z.
        policy.check(slot(utc(2026, 3, 29, 7), 30), london_hours)
        with pytest.raises(OutsideOpeningHours):
            policy.check(slot(utc(2026, 3, 29, 16), 30), london_hours)

    def test_fall_back_day_uses_gmt(self, london_hours):
        # 2026-10-25 clocks go back at 01:00 UTC; 08:00 GMT == 08:00Z.
        policy.check(slot(utc(2026, 10, 25, 8), 30), london_hours)
        with pytest.raises(OutsideOpeningHours):
            policy.check(slot(utc(2026, 10, 25, 7, 30), 30), london_hours)

    def test_new_york_after_fall_back(self, new_york_hours):
        # 2026-11-02 New York is on EST (UTC-5): 09:00-18:00 local == 14:00Z-23:00Z.
        policy.check(slot(utc(2026, 11, 2, 14), 120), new_york_hours)
        policy.check(slot(utc(2026, 11, 2, 22, 30), 30), new_york_hours)
        with pytest.raises(OutsideOpeningHours):
            policy.check(slot(utc(2026, 11, 2, 13, 45), 30), new_york_hours)

    def test_new_york_before_fall_back(self, new_york_hours):
        # 2026-10-30 New York is on EDT (UTC-4): 09:00 local == 13:00Z.
        policy.check(slot(utc(2026, 10, 30, 13), 30), new_york_hours)


def test_slot_must_fit_within_a_single_local_day():
    late_hours = OpeningHours(ZoneInfo("Europe/London"), time(0, 0), time(23, 45))
    with pytest.raises(OutsideOpeningHours):
        # 23:30 GMT to 00:30 GMT next day.
        policy.check(slot(utc(2026, 11, 2, 23, 30), 60), late_hours)


class TestOpeningWindow:
    def test_window_on_a_winter_day(self, london_hours):
        window = london_hours.window_on(date(2026, 11, 2))

        assert window == TimeSlot(utc(2026, 11, 2, 8), utc(2026, 11, 2, 17))

    def test_window_on_spring_forward_day(self, london_hours):
        window = london_hours.window_on(date(2026, 3, 29))

        assert window == TimeSlot(utc(2026, 3, 29, 7), utc(2026, 3, 29, 16))

    def test_local_date_of_instant(self, new_york_hours):
        # 02:00Z on 3 Nov is still 2 Nov in New York.
        assert new_york_hours.local_date_of(utc(2026, 11, 3, 2)) == date(2026, 11, 2)
