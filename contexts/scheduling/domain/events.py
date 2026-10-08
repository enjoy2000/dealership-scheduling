"""Domain events recorded by the Appointment aggregate; dispatched after commit."""

from dataclasses import dataclass

from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    BayId,
    DealershipId,
    TechnicianId,
    TimeSlot,
    VehicleId,
)
from shared_kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class AppointmentConfirmed(DomainEvent):
    appointment_id: AppointmentId
    dealership_id: DealershipId
    vehicle_id: VehicleId
    bay_id: BayId
    technician_id: TechnicianId
    slot: TimeSlot


@dataclass(frozen=True, kw_only=True)
class AppointmentCancelled(DomainEvent):
    appointment_id: AppointmentId
    dealership_id: DealershipId
    slot: TimeSlot
