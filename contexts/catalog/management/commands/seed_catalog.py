"""Seeds the Catalog reference data of SPEC §14.7 with stable ids. Idempotent."""

from datetime import time
from typing import Any

from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection, transaction

from contexts.catalog.models import Customer, Dealership, ServiceType, Vehicle

DEALERSHIPS = [
    (1, "Downtown Motors", "Europe/London", time(8), time(17)),
    (2, "Uptown Auto", "America/New_York", time(9), time(18)),
]
SERVICE_TYPES = [
    (1, "Oil Change", 30, "oil_service"),
    (2, "Brake Service", 90, "brakes"),
    (3, "Full Service", 120, "general"),
]
CUSTOMERS = [
    (1, "Customer One", "customer.one@example.com"),
    (2, "Customer Two", "customer.two@example.com"),
    (3, "Customer Three", "customer.three@example.com"),
]
VEHICLES = [
    (1, 1, "1HGCM82633A004352", "Honda", "Accord", 2003),
    (2, 1, "5YJ3E1EA7KF317000", "Tesla", "Model 3", 2019),
    (3, 2, "WVWZZZ1JZXW000001", "Volkswagen", "Golf", 1999),
    (4, 3, "3VWFE21C04M000001", "Volkswagen", "Jetta", 2004),
]


class Command(BaseCommand):
    help = "Seed Catalog demo data (dealerships, service types, customers, vehicles)."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        for pk, name, tz, opens, closes in DEALERSHIPS:
            Dealership.objects.update_or_create(
                id=pk,
                defaults={"name": name, "timezone": tz, "open_time": opens, "close_time": closes},
            )
        for pk, name, minutes, skill in SERVICE_TYPES:
            ServiceType.objects.update_or_create(
                id=pk,
                defaults={"name": name, "duration_minutes": minutes, "required_skill": skill},
            )
        for pk, name, email in CUSTOMERS:
            Customer.objects.update_or_create(id=pk, defaults={"name": name, "email": email})
        for pk, customer_id, vin, make, model, year in VEHICLES:
            Vehicle.objects.update_or_create(
                id=pk,
                defaults={
                    "customer_id": customer_id,
                    "vin": vin,
                    "make": make,
                    "model": model,
                    "year": year,
                },
            )
        # Explicit ids above; move sequences past them so admin inserts don't collide.
        models = [Dealership, ServiceType, Customer, Vehicle]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)
        self.stdout.write(self.style.SUCCESS("Catalog seeded."))
