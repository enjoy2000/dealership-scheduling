"""Scheduling domain errors. Each carries a stable `code` used by outer layers (SPEC §14.2)."""


class DomainError(Exception):
    code = "domain_error"
    default_message = "Domain rule violated."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class NoCapacityAvailable(DomainError):
    code = "no_capacity"
    default_message = "No service bay and qualified technician are free for the requested time."


class VehicleAlreadyBooked(DomainError):
    code = "vehicle_already_booked"
    default_message = "The vehicle already has an overlapping confirmed appointment."


class InvalidSlot(DomainError):
    code = "invalid_slot"
    default_message = "The requested time slot is invalid."


class OutsideOpeningHours(DomainError):
    code = "outside_opening_hours"
    default_message = "The appointment must fit within the dealership's opening hours."


class VehicleNotOwnedByCustomer(DomainError):
    code = "vehicle_not_owned"
    default_message = "The vehicle does not belong to the customer."


class CancellationNotAllowed(DomainError):
    code = "cancellation_not_allowed"
    default_message = "An appointment can only be cancelled before its start time."


class AppointmentAlreadyCancelled(DomainError):
    code = "appointment_already_cancelled"
    default_message = "The appointment is already cancelled."


class ResourceConflict(DomainError):
    """Raised by infrastructure when the database rejects an overlapping booking."""

    code = "resource_conflict"
    default_message = "A bay, technician or vehicle was booked concurrently."
