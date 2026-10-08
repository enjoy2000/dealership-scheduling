"""Read side (CQRS-lite, D5): projections straight from the tables, no aggregates."""

import uuid
from collections import defaultdict

from django.db.models import Exists, OuterRef

from contexts.scheduling.application.dto import AppointmentRow, NamedRef
from contexts.scheduling.domain.model.value_objects import (
    BayId,
    DealershipId,
    Skill,
    TechnicianId,
    TimeSlot,
)
from contexts.scheduling.domain.services.availability import DaySchedule
from contexts.scheduling.infrastructure.persistence.models import (
    CONFIRMED,
    AppointmentRecord,
    ServiceBayRecord,
    TechnicianRecord,
    TechnicianSkillRecord,
)
from contexts.scheduling.infrastructure.persistence.ranges import to_range, to_slot


class DjangoAppointmentReadModel:
    def get(self, appointment_id: uuid.UUID) -> AppointmentRow | None:
        record = (
            AppointmentRecord.objects.select_related("service_bay", "technician")
            .filter(pk=appointment_id)
            .first()
        )
        if record is None:
            return None
        slot = to_slot(record.time_range)
        return AppointmentRow(
            id=record.id,
            status=record.status,
            start_time=slot.start,
            end_time=slot.end,
            customer_id=record.customer_id,
            vehicle_id=record.vehicle_id,
            service_type_id=record.service_type_id,
            dealership_id=record.dealership_id,
            technician=NamedRef(record.technician.id, record.technician.name),
            service_bay=NamedRef(record.service_bay.id, record.service_bay.name),
        )


class DjangoAvailabilityReadModel:
    def day_schedule(
        self, dealership_id: DealershipId, skill: Skill, window: TimeSlot
    ) -> DaySchedule:
        # Three queries regardless of how many appointments or candidate starts (§14.4).
        bay_busy: dict[BayId, list[TimeSlot]] = {
            BayId(pk): []
            for pk in ServiceBayRecord.objects.filter(dealership_id=dealership_id).values_list(
                "id", flat=True
            )
        }
        qualified = TechnicianSkillRecord.objects.filter(
            technician=OuterRef("pk"), skill=skill.value
        )
        technician_busy: dict[TechnicianId, list[TimeSlot]] = {
            TechnicianId(pk): []
            for pk in TechnicianRecord.objects.filter(dealership_id=dealership_id)
            .filter(Exists(qualified))
            .values_list("id", flat=True)
        }
        appointments = AppointmentRecord.objects.filter(
            dealership_id=dealership_id, status=CONFIRMED, time_range__overlap=to_range(window)
        ).values_list("service_bay_id", "technician_id", "time_range")
        by_bay: defaultdict[int, list[TimeSlot]] = defaultdict(list)
        by_technician: defaultdict[int, list[TimeSlot]] = defaultdict(list)
        for bay_id, technician_id, time_range in appointments:
            slot = to_slot(time_range)
            by_bay[bay_id].append(slot)
            by_technician[technician_id].append(slot)
        for bay_id in bay_busy:
            bay_busy[bay_id] = by_bay[bay_id]
        for technician_id in technician_busy:
            technician_busy[technician_id] = by_technician[technician_id]
        return DaySchedule(bay_busy, technician_busy)
