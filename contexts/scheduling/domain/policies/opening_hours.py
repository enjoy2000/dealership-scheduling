"""A6: a slot must fit within the dealership's opening hours of a single local day."""

from contexts.scheduling.domain.errors import OutsideOpeningHours
from contexts.scheduling.domain.model.value_objects import OpeningHours, TimeSlot


class OpeningHoursPolicy:
    def check(self, slot: TimeSlot, hours: OpeningHours) -> None:
        # The window of the start's local day, converted to UTC, is DST-correct; a slot
        # that spills into another local day cannot fit inside it.
        window = hours.window_on(hours.local_date_of(slot.start))
        if not window.contains(slot):
            raise OutsideOpeningHours()
