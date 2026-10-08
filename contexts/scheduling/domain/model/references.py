"""Scheduling's own view of Catalog data, returned by the CatalogGateway port (ACL).

Scheduling never sees Catalog's models; it references them by id and reads these values.
"""

from dataclasses import dataclass
from datetime import timedelta

from contexts.scheduling.domain.errors import VehicleNotOwnedByCustomer
from contexts.scheduling.domain.model.value_objects import (
    CustomerId,
    DealershipId,
    OpeningHours,
    ServiceTypeId,
    Skill,
    VehicleId,
    Vin,
)


@dataclass(frozen=True)
class ServiceOffering:
    """A service type as Scheduling needs it: fixed duration and one required skill (A2)."""

    id: ServiceTypeId
    name: str
    duration: timedelta
    required_skill: Skill

    def __post_init__(self) -> None:
        if self.duration <= timedelta(0):
            raise ValueError("Service offering duration must be positive.")

    @property
    def duration_minutes(self) -> int:
        return int(self.duration.total_seconds() // 60)


@dataclass(frozen=True)
class DealershipCalendar:
    id: DealershipId
    name: str
    opening_hours: OpeningHours


@dataclass(frozen=True)
class CustomerRef:
    id: CustomerId
    name: str


@dataclass(frozen=True)
class VehicleRef:
    id: VehicleId
    customer_id: CustomerId
    vin: Vin

    def ensure_owned_by(self, customer_id: CustomerId) -> None:
        """A8: a vehicle can only be booked by the customer who owns it."""
        if self.customer_id != customer_id:
            raise VehicleNotOwnedByCustomer()
