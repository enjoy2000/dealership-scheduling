"""Conversion between the domain TimeSlot and PostgreSQL tstzrange values."""

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

from contexts.scheduling.domain.model.value_objects import TimeSlot


def to_range(slot: TimeSlot) -> DateTimeTZRange:
    return DateTimeTZRange(slot.start, slot.end, "[)")


def to_slot(value: DateTimeTZRange) -> TimeSlot:
    return TimeSlot(value.lower, value.upper)
