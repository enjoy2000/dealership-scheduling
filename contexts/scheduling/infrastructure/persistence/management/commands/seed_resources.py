"""Seeds the Scheduling resources of SPEC §14.7 (bays, technicians, skills). Idempotent.

Dealerships are referenced by id only; run `seed_catalog` first (or `seed_demo`).
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection, transaction

from contexts.scheduling.infrastructure.persistence.models import (
    ServiceBayRecord,
    TechnicianRecord,
    TechnicianSkillRecord,
)

BAYS = [(1, 1, "Bay 1"), (2, 1, "Bay 2"), (3, 1, "Bay 3"), (4, 2, "Bay 1")]
TECHNICIANS = [
    (1, 1, "Alice", ["oil_service", "general"]),
    (2, 1, "Bob", ["brakes", "general"]),
    (3, 1, "Chen", ["oil_service", "brakes"]),
    (4, 2, "Dana", ["oil_service", "brakes", "general"]),
]


class Command(BaseCommand):
    help = "Seed Scheduling demo resources (service bays, technicians and skills)."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        for pk, dealership_id, name in BAYS:
            ServiceBayRecord.objects.update_or_create(
                id=pk, defaults={"dealership_id": dealership_id, "name": name}
            )
        for pk, dealership_id, name, skills in TECHNICIANS:
            technician, _ = TechnicianRecord.objects.update_or_create(
                id=pk, defaults={"dealership_id": dealership_id, "name": name}
            )
            technician.skills.exclude(skill__in=skills).delete()
            for skill in skills:
                TechnicianSkillRecord.objects.get_or_create(technician=technician, skill=skill)
        models = [ServiceBayRecord, TechnicianRecord, TechnicianSkillRecord]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS("Scheduling resources seeded."))
