"""Django ORM implementations of the domain repository ports."""

from collections.abc import Sequence

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.resources import ServiceBay, TechnicianLoad
from contexts.scheduling.domain.model.value_objects import (
    AppointmentId,
    DealershipId,
    Skill,
    TimeSlot,
    VehicleId,
)
from contexts.scheduling.infrastructure.persistence.error_translation import (
    exclusion_violation_as_resource_conflict,
)
from contexts.scheduling.infrastructure.persistence.mappers import (
    appointment_to_domain,
    appointment_to_record,
    bay_to_domain,
    technician_to_domain,
)
from contexts.scheduling.infrastructure.persistence.models import (
    CONFIRMED,
    AppointmentRecord,
    ServiceBayRecord,
    TechnicianRecord,
    TechnicianSkillRecord,
)
from contexts.scheduling.infrastructure.persistence.ranges import to_range


def _confirmed_overlapping(slot: TimeSlot) -> "QuerySet[AppointmentRecord]":
    return AppointmentRecord.objects.filter(status=CONFIRMED, time_range__overlap=to_range(slot))


class DjangoAppointmentRepository:
    def add(self, appointment: Appointment) -> None:
        # Savepoint: a rejected insert leaves the surrounding transaction usable.
        with exclusion_violation_as_resource_conflict(), transaction.atomic():
            appointment_to_record(appointment).save(force_insert=True)

    def save(self, appointment: Appointment) -> None:
        AppointmentRecord.objects.filter(pk=appointment.id).update(
            status=appointment.status.value, cancelled_at=appointment.cancelled_at
        )

    def get(self, appointment_id: AppointmentId) -> Appointment | None:
        # Row lock: concurrent cancels of the same appointment serialise.
        record = AppointmentRecord.objects.select_for_update().filter(pk=appointment_id).first()
        return appointment_to_domain(record) if record else None

    def vehicle_has_overlap(self, vehicle_id: VehicleId, slot: TimeSlot) -> bool:
        return _confirmed_overlapping(slot).filter(vehicle_id=vehicle_id).exists()


class DjangoResourceRepository:
    def find_available_bays(
        self, dealership_id: DealershipId, slot: TimeSlot
    ) -> Sequence[ServiceBay]:
        busy = _confirmed_overlapping(slot).filter(service_bay=OuterRef("pk"))
        records = (
            ServiceBayRecord.objects.filter(dealership_id=dealership_id)
            .exclude(Exists(busy))
            .order_by("id")
        )
        return [bay_to_domain(record) for record in records]

    def find_available_technicians(
        self,
        dealership_id: DealershipId,
        skill: Skill,
        slot: TimeSlot,
        load_window: TimeSlot,
    ) -> Sequence[TechnicianLoad]:
        busy = _confirmed_overlapping(slot).filter(technician=OuterRef("pk"))
        qualified = TechnicianSkillRecord.objects.filter(
            technician=OuterRef("pk"), skill=skill.value
        )
        records = (
            TechnicianRecord.objects.filter(dealership_id=dealership_id)
            .filter(Exists(qualified))
            .exclude(Exists(busy))
            .annotate(
                load=Count(
                    "appointments",
                    filter=Q(
                        appointments__status=CONFIRMED,
                        appointments__time_range__contained_by=to_range(load_window),
                    ),
                )
            )
            .prefetch_related("skills")
            .order_by("id")
        )
        return [TechnicianLoad(technician_to_domain(r), r.load) for r in records]
