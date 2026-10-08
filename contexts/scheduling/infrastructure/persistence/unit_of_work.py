"""UnitOfWork over a Django database transaction.

`commit()` marks the work as complete; the transaction commits when the block exits.
Leaving without `commit()` (or with an exception) rolls back. Nested use (e.g. the
idempotency transaction around a booking, or tests) becomes a savepoint, so retries stay
isolated. State is a thread-local stack so one instance can serve concurrent threads.
"""

import threading
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from django.db import transaction

from contexts.scheduling.infrastructure.persistence.repositories import (
    DjangoAppointmentRepository,
    DjangoResourceRepository,
)


@dataclass
class _Frame:
    atomic: transaction.Atomic
    committed: bool = False


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

    @property
    def _stack(self) -> list[_Frame]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        stack: list[_Frame] = self._local.stack
        return stack

    def __enter__(self) -> Self:
        atomic = transaction.atomic()
        atomic.__enter__()
        self._stack.append(_Frame(atomic))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        frame = self._stack.pop()
        if exc_type is None and not frame.committed:
            transaction.set_rollback(True)
        frame.atomic.__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        self._stack[-1].committed = True

    def rollback(self) -> None:
        transaction.set_rollback(True)
        self._stack[-1].committed = False
