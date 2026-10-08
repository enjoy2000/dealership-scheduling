from django.contrib import admin
from django.http import HttpRequest

from contexts.scheduling.infrastructure.persistence.models import (
    AppointmentRecord,
    ServiceBayRecord,
    TechnicianRecord,
    TechnicianSkillRecord,
)


@admin.register(ServiceBayRecord)
class ServiceBayAdmin(admin.ModelAdmin[ServiceBayRecord]):
    list_display = ("id", "name", "dealership")
    list_select_related = ("dealership",)


class TechnicianSkillInline(admin.TabularInline[TechnicianSkillRecord, TechnicianRecord]):
    model = TechnicianSkillRecord
    extra = 0


@admin.register(TechnicianRecord)
class TechnicianAdmin(admin.ModelAdmin[TechnicianRecord]):
    list_display = ("id", "name", "dealership")
    list_select_related = ("dealership",)
    inlines = (TechnicianSkillInline,)


@admin.register(AppointmentRecord)
class AppointmentAdmin(admin.ModelAdmin[AppointmentRecord]):
    """Read-only: appointments are created and cancelled only through the API's rules."""

    list_display = ("id", "status", "time_range", "dealership", "service_bay", "technician")
    list_filter = ("status", "dealership")
    list_select_related = ("dealership", "service_bay", "technician")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False
