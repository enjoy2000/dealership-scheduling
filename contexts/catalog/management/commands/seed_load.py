"""Seeds load-test data for every context (composed by command name, like seed_demo)."""

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Seed load-test data: N dealerships x 8 bays x 8 technicians, M customers."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dealerships", type=int, default=50)
        parser.add_argument("--customers", type=int, default=5000)

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("seed_demo", verbosity=0)  # service types 1-3 are shared
        call_command(
            "seed_load_catalog", dealerships=options["dealerships"], customers=options["customers"]
        )
        call_command("seed_load_resources", dealerships=options["dealerships"])
        self.stdout.write(self.style.SUCCESS("Load data seeded."))
