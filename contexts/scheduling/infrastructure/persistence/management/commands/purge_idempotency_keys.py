"""Deletes idempotency keys older than IDEMPOTENCY_TTL_HOURS (SPEC §14.5). Run from cron."""

from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from contexts.scheduling.infrastructure.persistence.models import IdempotencyRecord


class Command(BaseCommand):
    help = "Delete expired idempotency keys."

    def handle(self, *args: Any, **options: Any) -> None:
        cutoff = datetime.now(UTC) - timedelta(hours=settings.IDEMPOTENCY_TTL_HOURS)
        deleted, _ = IdempotencyRecord.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} expired idempotency keys.")
