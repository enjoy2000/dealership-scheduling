"""Immutable value objects and typed identifiers of the Scheduling domain."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import NewType
from zoneinfo import ZoneInfo

from contexts.scheduling.domain.errors import InvalidSlot

AppointmentId = NewType("AppointmentId", uuid.UUID)
CustomerId = NewType("CustomerId", int)
VehicleId = NewType("VehicleId", int)
DealershipId = NewType("DealershipId", int)
ServiceTypeId = NewType("ServiceTypeId", int)
BayId = NewType("BayId", int)
TechnicianId = NewType("TechnicianId", int)


class AppointmentStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


def _is_aware(moment: datetime) -> bool:
    return moment.tzinfo is not None and moment.utcoffset() is not None


@dataclass(frozen=True)
class TimeSlot:
    """Half-open interval `[start, end)`, stored in UTC (A5, A6)."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not (_is_aware(self.start) and _is_aware(self.end)):
            raise InvalidSlot("Time slot boundaries must be timezone-aware.")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))
        if self.end <= self.start:
            raise InvalidSlot("Time slot must end after it starts.")

    @classmethod
    def starting_at(cls, start: datetime, duration: timedelta) -> "TimeSlot":
        return cls(start, start + duration)

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def overlaps(self, other: "TimeSlot") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: "TimeSlot") -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True)
class OpeningHours:
    """A dealership's daily local opening window, applied every day (A6, A18)."""

    timezone: ZoneInfo
    open_time: time
    close_time: time

    def __post_init__(self) -> None:
        if self.close_time <= self.open_time:
            raise ValueError("Opening hours: close_time must be after open_time.")

    def window_on(self, local_date: date) -> TimeSlot:
        """The opening window of a dealership-local date, as a UTC slot (DST-aware)."""
        return TimeSlot(
            datetime.combine(local_date, self.open_time, tzinfo=self.timezone),
            datetime.combine(local_date, self.close_time, tzinfo=self.timezone),
        )

    def local_date_of(self, moment: datetime) -> date:
        return moment.astimezone(self.timezone).date()


_SKILL_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Skill:
    value: str

    def __post_init__(self) -> None:
        normalised = self.value.strip().lower()
        if not _SKILL_PATTERN.match(normalised):
            raise ValueError(f"Invalid skill name: {self.value!r}.")
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value


_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


@dataclass(frozen=True)
class Vin:
    """17-character vehicle identification number, excluding I, O and Q (§14.1)."""

    value: str

    def __post_init__(self) -> None:
        normalised = self.value.strip().upper()
        if not _VIN_PATTERN.match(normalised):
            raise ValueError(f"Invalid VIN: {self.value!r}.")
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value
