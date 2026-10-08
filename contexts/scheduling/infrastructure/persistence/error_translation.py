"""Translate database errors into domain errors.

Only SQLSTATE 23P01 (exclusion_violation) means "resource taken concurrently". Other
integrity errors (unique, FK, check) are bugs or bad input and must not trigger retries.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import IntegrityError

from contexts.scheduling.domain.errors import ResourceConflict

EXCLUSION_VIOLATION = "23P01"


def is_exclusion_violation(error: IntegrityError) -> bool:
    return getattr(error.__cause__, "sqlstate", None) == EXCLUSION_VIOLATION


@contextmanager
def exclusion_violation_as_resource_conflict() -> Iterator[None]:
    try:
        yield
    except IntegrityError as error:
        if is_exclusion_violation(error):
            raise ResourceConflict() from error
        raise
