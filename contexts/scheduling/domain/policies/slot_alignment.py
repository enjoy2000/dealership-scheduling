"""A7: a start time must be in the future and on the slot grid."""

from datetime import UTC, datetime, timedelta

from contexts.scheduling.domain.errors import InvalidSlot

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class SlotAlignmentPolicy:
    def __init__(self, grid_minutes: int = 15) -> None:
        self._grid = timedelta(minutes=grid_minutes)

    def check(self, start: datetime, now: datetime) -> None:
        if start.tzinfo is None or start.utcoffset() is None:
            raise InvalidSlot("Start time must be timezone-aware.")
        if (start - _EPOCH) % self._grid:
            minutes = int(self._grid.total_seconds() // 60)
            raise InvalidSlot(f"Start time must be aligned to the {minutes}-minute grid.")
        if start <= now:
            raise InvalidSlot("Start time must be in the future.")
