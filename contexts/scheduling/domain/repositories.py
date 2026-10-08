"""Repository ports of the Scheduling domain, implemented by infrastructure."""

from collections.abc import Sequence
from typing import Protocol

from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.resources import ServiceBay, TechnicianLoad
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    DealershipId,
    Skill,
    TimeSlot,
    VehicleId,
)


class AppointmentRepository(Protocol):
    def add(self, appointment: Appointment) -> None:
        """Persist a new appointment. Raises `ResourceConflict` if the database rejects
        an overlapping bay, technician or vehicle booking."""
        ...

    def save(self, appointment: Appointment) -> None:
        """Persist state changes of an existing appointment (e.g. cancellation)."""
        ...

    def get(self, appointment_id: AppointmentId) -> Appointment | None: ...

    def vehicle_has_overlap(self, vehicle_id: VehicleId, slot: TimeSlot) -> bool:
        """True if the vehicle has a confirmed appointment overlapping `slot`."""
        ...


class ResourceRepository(Protocol):
    def find_available_bays(
        self, dealership_id: DealershipId, slot: TimeSlot
    ) -> Sequence[ServiceBay]:
        """Bays of the dealership with no confirmed appointment overlapping `slot`."""
        ...

    def find_available_technicians(
        self,
        dealership_id: DealershipId,
        skill: Skill,
        slot: TimeSlot,
        load_window: TimeSlot,
    ) -> Sequence[TechnicianLoad]:
        """Technicians holding `skill` who are free for `slot`, each with the number of
        confirmed appointments they have within `load_window` (the local day)."""
        ...
