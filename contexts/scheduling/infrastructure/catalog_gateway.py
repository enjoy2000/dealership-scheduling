"""CatalogGateway adapter: the only Scheduling module allowed to read Catalog models (ACL).

Translates Catalog rows into Scheduling's own value objects.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from contexts.catalog.models import Customer, Dealership, ServiceType, Vehicle
from contexts.scheduling.domain.model.references import (
    CustomerRef,
    DealershipCalendar,
    ServiceOffering,
    VehicleRef,
)
from contexts.scheduling.domain.model.value_objects import (
    CustomerId,
    DealershipId,
    OpeningHours,
    ServiceTypeId,
    Skill,
    VehicleId,
    Vin,
)


class DjangoCatalogGateway:
    def get_service_offering(self, service_type_id: ServiceTypeId) -> ServiceOffering | None:
        row = ServiceType.objects.filter(pk=service_type_id).first()
        if row is None:
            return None
        return ServiceOffering(
            ServiceTypeId(row.id),
            row.name,
            timedelta(minutes=row.duration_minutes),
            Skill(row.required_skill),
        )

    def get_dealership_calendar(self, dealership_id: DealershipId) -> DealershipCalendar | None:
        row = Dealership.objects.filter(pk=dealership_id).first()
        if row is None:
            return None
        hours = OpeningHours(ZoneInfo(row.timezone), row.open_time, row.close_time)
        return DealershipCalendar(DealershipId(row.id), row.name, hours)

    def get_customer(self, customer_id: CustomerId) -> CustomerRef | None:
        row = Customer.objects.filter(pk=customer_id).only("id", "name").first()
        return CustomerRef(CustomerId(row.id), row.name) if row else None

    def get_vehicle(self, vehicle_id: VehicleId) -> VehicleRef | None:
        row = Vehicle.objects.filter(pk=vehicle_id).only("id", "customer_id", "vin").first()
        if row is None:
            return None
        return VehicleRef(VehicleId(row.id), CustomerId(row.customer_id), Vin(row.vin))
