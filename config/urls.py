from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.health import healthz, readyz
from contexts.scheduling.container import get_container
from contexts.scheduling.interface.api.dependencies import install_use_cases

# Composition: the API obtains its use cases from the container without importing it.
install_use_cases(get_container)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("", include("django_prometheus.urls")),  # /metrics
    path("api/v1/", include("contexts.scheduling.interface.api.urls")),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
