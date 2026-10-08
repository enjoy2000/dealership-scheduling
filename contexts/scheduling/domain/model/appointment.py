"""The Appointment aggregate root (D1: the only aggregate in Scheduling)."""

from datetime import datetime

from contexts.scheduling.domain.errors import AppointmentAlreadyCancelled, CancellationNotAllowed
from contexts.scheduling.domain.events import AppointmentCancelled, AppointmentConfirmed
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    AppointmentStatus,
    BayId,
    CustomerId,
    DealershipId,
    ServiceTypeId,
    TechnicianId,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.domain.services.resource_allocator import Allocation
from shared_kernel.events import DomainEvent


class Appointment:
    """A reservation of one bay and one technician for one vehicle over a time slot.

    Use `schedule()` to book; the constructor reconstitutes persisted state without events.
    """

    def __init__(
        self,
        *,
        id: AppointmentId,
        customer_id: CustomerId,
        vehicle_id: VehicleId,
        dealership_id: DealershipId,
        service_type_id: ServiceTypeId,
        bay_id: BayId,
        technician_id: TechnicianId,
        slot: TimeSlot,
        status: AppointmentStatus,
        created_at: datetime,
        cancelled_at: datetime | None = None,
    ) -> None:
        if (status is AppointmentStatus.CANCELLED) != (cancelled_at is not None):
            raise ValueError("cancelled_at must be set exactly when the status is CANCELLED.")
        self._id = id
        self._customer_id = customer_id
        self._vehicle_id = vehicle_id
        self._dealership_id = dealership_id
        self._service_type_id = service_type_id
        self._bay_id = bay_id
        self._technician_id = technician_id
        self._slot = slot
        self._status = status
        self._created_at = created_at
        self._cancelled_at = cancelled_at
        self._events: list[DomainEvent] = []

    @classmethod
    def schedule(
        cls,
        *,
        appointment_id: AppointmentId,
        customer_id: CustomerId,
        vehicle_id: VehicleId,
        dealership_id: DealershipId,
        service_type_id: ServiceTypeId,
        allocation: Allocation,
        slot: TimeSlot,
        now: datetime,
    ) -> "Appointment":
        appointment = cls(
            id=appointment_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            dealership_id=dealership_id,
            service_type_id=service_type_id,
            bay_id=allocation.bay_id,
            technician_id=allocation.technician_id,
            slot=slot,
            status=AppointmentStatus.CONFIRMED,
            created_at=now,
        )
        appointment._events.append(
            AppointmentConfirmed(
                appointment_id=appointment_id,
                dealership_id=dealership_id,
                vehicle_id=vehicle_id,
                bay_id=allocation.bay_id,
                technician_id=allocation.technician_id,
                slot=slot,
                occurred_at=now,
            )
        )
        return appointment

    def cancel(self, now: datetime) -> None:
        """A19: only before the start time. A second cancel is rejected so callers can
        treat it as an idempotent no-op."""
        if self._status is AppointmentStatus.CANCELLED:
            raise AppointmentAlreadyCancelled()
        if now >= self._slot.start:
            raise CancellationNotAllowed()
        self._status = AppointmentStatus.CANCELLED
        self._cancelled_at = now
        self._events.append(
            AppointmentCancelled(
                appointment_id=self._id,
                dealership_id=self._dealership_id,
                slot=self._slot,
                occurred_at=now,
            )
        )

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events

    @property
    def is_cancelled(self) -> bool:
        return self._status is AppointmentStatus.CANCELLED

    @property
    def id(self) -> AppointmentId:
        return self._id

    @property
    def customer_id(self) -> CustomerId:
        return self._customer_id

    @property
    def vehicle_id(self) -> VehicleId:
        return self._vehicle_id

    @property
    def dealership_id(self) -> DealershipId:
        return self._dealership_id

    @property
    def service_type_id(self) -> ServiceTypeId:
        return self._service_type_id

    @property
    def bay_id(self) -> BayId:
        return self._bay_id

    @property
    def technician_id(self) -> TechnicianId:
        return self._technician_id

    @property
    def slot(self) -> TimeSlot:
        return self._slot

    @property
    def status(self) -> AppointmentStatus:
        return self._status

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def cancelled_at(self) -> datetime | None:
        return self._cancelled_at
