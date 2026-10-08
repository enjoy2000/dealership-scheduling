"""Mappers between ORM records and domain objects (D3)."""

from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.resources import ServiceBay, Technician
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    AppointmentStatus,
    BayId,
    CustomerId,
    DealershipId,
    ServiceTypeId,
    Skill,
    TechnicianId,
    VehicleId,
)
from contexts.scheduling.infrastructure.persistence.models import (
    AppointmentRecord,
    ServiceBayRecord,
    TechnicianRecord,
)
from contexts.scheduling.infrastructure.persistence.ranges import to_range, to_slot


def appointment_to_record(appointment: Appointment) -> AppointmentRecord:
    return AppointmentRecord(
        id=appointment.id,
        customer_id=appointment.customer_id,
        vehicle_id=appointment.vehicle_id,
        dealership_id=appointment.dealership_id,
        service_type_id=appointment.service_type_id,
        service_bay_id=appointment.bay_id,
        technician_id=appointment.technician_id,
        time_range=to_range(appointment.slot),
        status=appointment.status.value,
        created_at=appointment.created_at,
        cancelled_at=appointment.cancelled_at,
    )


def appointment_to_domain(record: AppointmentRecord) -> Appointment:
    return Appointment(
        id=AppointmentId(record.id),
        customer_id=CustomerId(record.customer_id),
        vehicle_id=VehicleId(record.vehicle_id),
        dealership_id=DealershipId(record.dealership_id),
        service_type_id=ServiceTypeId(record.service_type_id),
        bay_id=BayId(record.service_bay_id),
        technician_id=TechnicianId(record.technician_id),
        slot=to_slot(record.time_range),
        status=AppointmentStatus(record.status),
        created_at=record.created_at,
        cancelled_at=record.cancelled_at,
    )


def bay_to_domain(record: ServiceBayRecord) -> ServiceBay:
    return ServiceBay(BayId(record.id), DealershipId(record.dealership_id), record.name)


def technician_to_domain(record: TechnicianRecord) -> Technician:
    """Expects `skills` to be prefetched."""
    return Technician(
        TechnicianId(record.id),
        DealershipId(record.dealership_id),
        record.name,
        frozenset(Skill(s.skill) for s in record.skills.all()),
    )
