from datetime import datetime

import pytest

from contexts.scheduling.domain.errors import InvalidSlot
from contexts.scheduling.domain.policies.slot_alignment import SlotAlignmentPolicy
from tests.unit.domain.time_helpers import utc

NOW = utc(2026, 11, 1, 12)
policy = SlotAlignmentPolicy()


@pytest.mark.parametrize("minute", [0, 15, 30, 45])
def test_future_start_on_the_grid_is_accepted(minute):
    policy.check(utc(2026, 11, 2, 9, minute), now=NOW)


@pytest.mark.parametrize("minute", [1, 5, 14, 59])
def test_start_off_the_grid_is_rejected(minute):
    with pytest.raises(InvalidSlot, match="15-minute"):
        policy.check(utc(2026, 11, 2, 9, minute), now=NOW)


def test_start_with_seconds_is_rejected():
    with pytest.raises(InvalidSlot):
        policy.check(utc(2026, 11, 2, 9).replace(second=30), now=NOW)


def test_start_in_the_past_is_rejected():
    with pytest.raises(InvalidSlot, match="future"):
        policy.check(utc(2026, 11, 1, 11, 45), now=NOW)


def test_start_equal_to_now_is_rejected():
    with pytest.raises(InvalidSlot, match="future"):
        policy.check(NOW, now=NOW)


def test_naive_start_is_rejected():
    with pytest.raises(InvalidSlot):
        policy.check(datetime(2026, 11, 2, 9), now=NOW)
