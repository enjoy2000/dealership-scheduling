"""JSON codecs for DTOs that are persisted (idempotent responses)."""

import uuid
from datetime import datetime
from typing import Any

from contexts.scheduling.application.dto import (
    AppointmentDetails,
    NamedRef,
    ServiceTypeSummary,
    VehicleSummary,
)


def appointment_details_to_json(details: AppointmentDetails) -> dict[str, Any]:
    return {
        "id": str(details.id),
        "status": details.status,
        "start_time": details.start_time.isoformat(),
        "end_time": details.end_time.isoformat(),
        "customer": {"id": details.customer.id, "name": details.customer.name},
        "vehicle": {"id": details.vehicle.id, "vin": details.vehicle.vin},
        "service_type": {
            "id": details.service_type.id,
            "name": details.service_type.name,
            "duration_minutes": details.service_type.duration_minutes,
        },
        "dealership": {"id": details.dealership.id, "name": details.dealership.name},
        "technician": {"id": details.technician.id, "name": details.technician.name},
        "service_bay": {"id": details.service_bay.id, "name": details.service_bay.name},
    }


def appointment_details_from_json(data: dict[str, Any]) -> AppointmentDetails:
    return AppointmentDetails(
        id=uuid.UUID(data["id"]),
        status=data["status"],
        start_time=datetime.fromisoformat(data["start_time"]),
        end_time=datetime.fromisoformat(data["end_time"]),
        customer=NamedRef(**data["customer"]),
        vehicle=VehicleSummary(**data["vehicle"]),
        service_type=ServiceTypeSummary(**data["service_type"]),
        dealership=NamedRef(**data["dealership"]),
        technician=NamedRef(**data["technician"]),
        service_bay=NamedRef(**data["service_bay"]),
    )
