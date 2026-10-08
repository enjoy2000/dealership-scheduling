"""Load-test resources: 8 bays and 8 technicians per load dealership (ids by formula).

Technician k holds two of the three skills, so each skill has 5-6 qualified technicians.
Run `seed_load_catalog` first (dealerships are referenced by id only).
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.core.management.color import no_style
from django.db import connection, transaction

from contexts.scheduling.infrastructure.persistence.models import (
    ServiceBayRecord,
    TechnicianRecord,
    TechnicianSkillRecord,
)

DEALERSHIP_BASE = 1000
PER_DEALERSHIP = 8
SKILLS = ("oil_service", "brakes", "general")


def resource_id(dealership_number: int, index: int) -> int:
    return 10_000 + dealership_number * PER_DEALERSHIP + index


class Command(BaseCommand):
    help = "Seed Scheduling resources for load tests."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dealerships", type=int, default=50)

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        bays, technicians, skills = [], [], []
        for n in range(1, options["dealerships"] + 1):
            dealership_id = DEALERSHIP_BASE + n
            for k in range(PER_DEALERSHIP):
                pk = resource_id(n, k)
                bays.append(
                    ServiceBayRecord(id=pk, dealership_id=dealership_id, name=f"Bay {k + 1}")
                )
                technicians.append(
                    TechnicianRecord(id=pk, dealership_id=dealership_id, name=f"Tech {n}-{k + 1}")
                )
                skills += [
                    TechnicianSkillRecord(technician_id=pk, skill=SKILLS[k % 3]),
                    TechnicianSkillRecord(technician_id=pk, skill=SKILLS[(k + 1) % 3]),
                ]
        ServiceBayRecord.objects.bulk_create(bays, ignore_conflicts=True)
        TechnicianRecord.objects.bulk_create(technicians, ignore_conflicts=True)
        TechnicianSkillRecord.objects.bulk_create(skills, ignore_conflicts=True)
        models = [ServiceBayRecord, TechnicianRecord, TechnicianSkillRecord]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)
