from django.apps import AppConfig


class SchedulingPersistenceConfig(AppConfig):
    name = "contexts.scheduling.infrastructure.persistence"
    label = "scheduling"
    verbose_name = "Scheduling"
    default_auto_field = "django.db.models.BigAutoField"
