from django.urls import path

from contexts.scheduling.interface.api.views import (
    AppointmentCollectionView,
    AppointmentDetailView,
    AvailabilityView,
)

urlpatterns = [
    path("appointments/", AppointmentCollectionView.as_view(), name="appointment-list"),
    path("appointments/<uuid:id>/", AppointmentDetailView.as_view(), name="appointment-detail"),
    path("availability/", AvailabilityView.as_view(), name="availability"),
]
