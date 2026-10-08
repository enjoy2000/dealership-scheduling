"""UnitOfWork over a Django database transaction.

`commit()` marks the work as complete; the transaction commits when the block exits.
Leaving without `commit()` (or with an exception) rolls back. Used inside an outer atomic
block (tests, ATOMIC_REQUESTS) it becomes a savepoint, so retries stay isolated.
State is thread-local so one instance can serve concurrent threads.
"""

import threading
from types import TracebackType
from typing import Self

from django.db import transaction

from contexts.scheduling.infrastructure.persistence.repositories import (
    DjangoAppointmentRepository,
    DjangoResourceRepository,
)


class DjangoUnitOfWork:
    def __init__(self) -> None:
        self._appointments = DjangoAppointmentRepository()
        self._resources = DjangoResourceRepository()
        self._local = threading.local()

    @property
    def appointments(self) -> DjangoAppointmentRepository:
        return self._appointments

    @property
    def resources(self) -> DjangoResourceRepository:
        return self._resources

    def __enter__(self) -> Self:
        atomic = transaction.atomic()
        atomic.__enter__()
        self._local.atomic = atomic
        self._local.committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None and not self._local.committed:
            transaction.set_rollback(True)
        atomic, self._local.atomic = self._local.atomic, None
        atomic.__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        self._local.committed = True

    def rollback(self) -> None:
        transaction.set_rollback(True)
        self._local.committed = False
