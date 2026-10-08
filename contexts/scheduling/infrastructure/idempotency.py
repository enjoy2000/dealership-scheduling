"""IdempotencyStore on PostgreSQL (SPEC §14.5)."""

from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction

from contexts.scheduling.application.errors import IdempotencyConflictError
from contexts.scheduling.application.ports import Clock, StoredResponse
from contexts.scheduling.infrastructure.persistence.models import IdempotencyRecord

UNIQUE_VIOLATION = "23505"


class DjangoIdempotencyStore:
    def __init__(self, *, clock: Clock, ttl: timedelta) -> None:
        self._clock = clock
        self._ttl = ttl

    def _cutoff(self) -> datetime:
        return self._clock.now() - self._ttl

    def find(self, key: str) -> StoredResponse | None:
        record = IdempotencyRecord.objects.filter(
            key=key, created_at__gte=self._cutoff(), response_status__isnull=False
        ).first()
        if record is None:
            return None
        return StoredResponse(record.request_hash, record.response_status, record.response_body)

    def reserve(self, key: str, request_hash: str) -> None:
        IdempotencyRecord.objects.filter(key=key, created_at__lt=self._cutoff()).delete()
        try:
            # Blocks while a concurrent transaction holds the same key, then fails if it
            # committed: the duplicate request loses (409), it never runs twice.
            with transaction.atomic():
                IdempotencyRecord.objects.create(
                    key=key, request_hash=request_hash, created_at=self._clock.now()
                )
        except IntegrityError as error:
            if getattr(error.__cause__, "sqlstate", None) == UNIQUE_VIOLATION:
                raise IdempotencyConflictError(
                    "A request with this Idempotency-Key is already being processed."
                ) from error
            raise

    def complete(self, key: str, status: int, body: dict[str, Any]) -> None:
        IdempotencyRecord.objects.filter(key=key).update(response_status=status, response_body=body)
