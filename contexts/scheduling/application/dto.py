"""Command and result DTOs: plain data crossing the application boundary."""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BookAppointmentCommand:
    customer_id: int
    vehicle_id: int
    service_type_id: int
    dealership_id: int
    start_time: datetime


@dataclass(frozen=True)
class CancelAppointmentCommand:
    appointment_id: uuid.UUID


@dataclass(frozen=True)
class NamedRef:
    id: int
    name: str


@dataclass(frozen=True)
class VehicleSummary:
    id: int
    vin: str


@dataclass(frozen=True)
class ServiceTypeSummary:
    id: int
    name: str
    duration_minutes: int


@dataclass(frozen=True)
class AppointmentDetails:
    """Shape of the 201 body (SPEC §6, §14.3)."""

    id: uuid.UUID
    status: str
    start_time: datetime
    end_time: datetime
    customer: NamedRef
    vehicle: VehicleSummary
    service_type: ServiceTypeSummary
    dealership: NamedRef
    technician: NamedRef
    service_bay: NamedRef
