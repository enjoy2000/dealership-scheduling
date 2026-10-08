"""Load-test reference data with deterministic ids (see tests/load/README.md).
VINs avoid I, O and Q: bulk_create skips model validators, and the domain rejects them.

Dealerships 1001..1000+N (Europe/London, 08:00-18:00); customers and vehicles
100001..100000+M (vehicle id == customer id). Idempotent.
"""

from datetime import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from contexts.catalog.models import Customer, Dealership, Vehicle

DEALERSHIP_BASE = 1000
CUSTOMER_BASE = 100_000


class Command(BaseCommand):
    help = "Seed Catalog data for load tests."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dealerships", type=int, default=50)
        parser.add_argument("--customers", type=int, default=5000)

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        Dealership.objects.bulk_create(
            [
                Dealership(
                    id=DEALERSHIP_BASE + n,
                    name=f"Load Dealer {n}",
                    timezone="Europe/London",
                    open_time=time(8),
                    close_time=time(18),
                )
                for n in range(1, options["dealerships"] + 1)
            ],
            ignore_conflicts=True,
        )
        ids = range(CUSTOMER_BASE + 1, CUSTOMER_BASE + options["customers"] + 1)
        Customer.objects.bulk_create(
            [Customer(id=i, name=f"Load Customer {i}", email=f"load{i}@example.com") for i in ids],
            ignore_conflicts=True,
        )
        Vehicle.objects.bulk_create(
            [
                Vehicle(
                    id=i, customer_id=i, vin=f"LDXT{i:013d}", make="Make", model="Model", year=2022
                )
                for i in ids
            ],
            ignore_conflicts=True,
        )
