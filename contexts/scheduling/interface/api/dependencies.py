"""The use cases the API needs, supplied by the composition root at startup.

The interface layer never imports `container.py` or infrastructure; `config/urls.py`
installs the provider (dependency inversion, enforced by import-linter).
"""

from collections.abc import Callable
from typing import Protocol

from django.core.exceptions import ImproperlyConfigured

from contexts.scheduling.application.dto import (
    AppointmentDetails,
    BookAppointmentCommand,
    CancelAppointmentCommand,
)


class SchedulingUseCases(Protocol):
    @property
    def book_appointment(self) -> Callable[[BookAppointmentCommand], AppointmentDetails]: ...

    @property
    def cancel_appointment(self) -> Callable[[CancelAppointmentCommand], None]: ...


_provider: Callable[[], SchedulingUseCases] | None = None


def install_use_cases(provider: Callable[[], SchedulingUseCases]) -> None:
    global _provider
    _provider = provider


def use_cases() -> SchedulingUseCases:
    if _provider is None:
        raise ImproperlyConfigured("Scheduling use cases are not installed (see config/urls.py).")
    return _provider()
