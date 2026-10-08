from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "contexts.catalog"
    label = "catalog"
    verbose_name = "Catalog"
    default_auto_field = "django.db.models.BigAutoField"
