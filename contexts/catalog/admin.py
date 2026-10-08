from django.contrib import admin

from contexts.catalog.models import Customer, Dealership, ServiceType, Vehicle


@admin.register(Dealership)
class DealershipAdmin(admin.ModelAdmin[Dealership]):
    list_display = ("id", "name", "timezone", "open_time", "close_time")


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin[ServiceType]):
    list_display = ("id", "name", "duration_minutes", "required_skill")


class VehicleInline(admin.TabularInline[Vehicle, Customer]):
    model = Vehicle
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin[Customer]):
    list_display = ("id", "name", "email")
    inlines = (VehicleInline,)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin[Vehicle]):
    list_display = ("id", "vin", "customer", "make", "model", "year")
    list_select_related = ("customer",)
