"""Use case: cancel an appointment, freeing its bay and technician (A10, A19)."""

from contexts.scheduling.application.dto import CancelAppointmentCommand, CancellationResult
from contexts.scheduling.application.errors import NotFoundError
from contexts.scheduling.application.ports import Clock, EventPublisher, UnitOfWork
from contexts.scheduling.domain.errors import AppointmentAlreadyCancelled
from contexts.scheduling.domain.model.appointment import Appointment
from contexts.scheduling.domain.model.value_objects import AppointmentId


def _result(appointment: Appointment) -> CancellationResult:
    assert appointment.cancelled_at is not None
    return CancellationResult(
        id=appointment.id, status=appointment.status.value, cancelled_at=appointment.cancelled_at
    )


class CancelAppointmentHandler:
    def __init__(self, *, uow: UnitOfWork, clock: Clock, events: EventPublisher) -> None:
        self._uow = uow
        self._clock = clock
        self._events = events

    def __call__(self, command: CancelAppointmentCommand) -> CancellationResult:
        with self._uow as uow:
            appointment = uow.appointments.get(AppointmentId(command.appointment_id))
            if appointment is None:
                raise NotFoundError("appointment", command.appointment_id)
            try:
                appointment.cancel(now=self._clock.now())
            except AppointmentAlreadyCancelled:
                return _result(appointment)  # repeated cancel is idempotent; state unchanged
            uow.appointments.save(appointment)
            uow.commit()

        self._events.publish(appointment.pull_events())
        return _result(appointment)
