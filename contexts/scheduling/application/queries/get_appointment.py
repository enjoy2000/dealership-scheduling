"""Query: fetch one appointment (GET /appointments/{id}/)."""

from contexts.scheduling.application.dto import (
    AppointmentDetails,
    GetAppointmentQuery,
    NamedRef,
    ServiceTypeSummary,
    VehicleSummary,
)
from contexts.scheduling.application.errors import NotFoundError
from contexts.scheduling.application.ports import AppointmentReadModel, CatalogGateway
from contexts.scheduling.domain.model.value_objects import (
    CustomerId,
    DealershipId,
    ServiceTypeId,
    VehicleId,
)


class GetAppointmentHandler:
    def __init__(self, *, read_model: AppointmentReadModel, catalog: CatalogGateway) -> None:
        self._read_model = read_model
        self._catalog = catalog

    def __call__(self, query: GetAppointmentQuery) -> AppointmentDetails:
        row = self._read_model.get(query.appointment_id)
        if row is None:
            raise NotFoundError("appointment", query.appointment_id)
        # Catalog rows are FK-protected, so they always exist for a stored appointment.
        customer = self._catalog.get_customer(CustomerId(row.customer_id))
        vehicle = self._catalog.get_vehicle(VehicleId(row.vehicle_id))
        offering = self._catalog.get_service_offering(ServiceTypeId(row.service_type_id))
        dealership = self._catalog.get_dealership_calendar(DealershipId(row.dealership_id))
        if customer is None or vehicle is None or offering is None or dealership is None:
            raise LookupError(f"Appointment {row.id} references missing catalog data.")
        return AppointmentDetails(
            id=row.id,
            status=row.status,
            start_time=row.start_time,
            end_time=row.end_time,
            customer=NamedRef(customer.id, customer.name),
            vehicle=VehicleSummary(vehicle.id, str(vehicle.vin)),
            service_type=ServiceTypeSummary(offering.id, offering.name, offering.duration_minutes),
            dealership=NamedRef(dealership.id, dealership.name),
            technician=row.technician,
            service_bay=row.service_bay,
        )
