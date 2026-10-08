"""Bookable start times for one dealership-local day (SPEC §14.4). Pure and set-based:
the caller loads the day's busy intervals once; candidates are evaluated in memory."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from contexts.scheduling.domain.model.value_objects import BayId, TechnicianId, TimeSlot

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class DaySchedule:
    """Busy intervals per bay and per *qualified* technician of a dealership within a day.

    Every bay and qualified technician appears as a key, even with no bookings.
    """

    bay_busy: Mapping[BayId, Sequence[TimeSlot]]
    technician_busy: Mapping[TechnicianId, Sequence[TimeSlot]]


def _is_free(busy: Sequence[TimeSlot], slot: TimeSlot) -> bool:
    return not any(interval.overlaps(slot) for interval in busy)


class AvailabilityCalculator:
    def __init__(self, grid_minutes: int = 15) -> None:
        self._grid = timedelta(minutes=grid_minutes)

    def free_slots(
        self, window: TimeSlot, duration: timedelta, now: datetime, schedule: DaySchedule
    ) -> list[TimeSlot]:
        """Grid-aligned slots inside `window`, starting after `now`, for which at least one
        bay and one qualified technician are free for the whole duration (§7 rule 13)."""
        slots: list[TimeSlot] = []
        start = self._first_grid_point_at_or_after(window.start)
        while start + duration <= window.end:
            slot = TimeSlot.starting_at(start, duration)
            if (
                start > now
                and any(_is_free(busy, slot) for busy in schedule.bay_busy.values())
                and any(_is_free(busy, slot) for busy in schedule.technician_busy.values())
            ):
                slots.append(slot)
            start += self._grid
        return slots

    def _first_grid_point_at_or_after(self, moment: datetime) -> datetime:
        remainder = (moment - _EPOCH) % self._grid
        return moment if not remainder else moment + (self._grid - remainder)
