"""Seeds all demo data (SPEC §14.7). Each context seeds its own tables; contexts are
composed by command name so neither imports the other's models (A17)."""

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Seed demo reference data for every context."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        verbosity = options["verbosity"]
        call_command("seed_catalog", verbosity=verbosity)
        call_command("seed_resources", verbosity=verbosity)
