from django.urls import path

from .views import (
    NearestShelterView,
    ResourceDetailView,
    ResourceListView,
    ShelterDetailView,
    ShelterListView,
)

urlpatterns = [
    path("resources", ResourceListView.as_view(), name="resource-list"),
    path("resources/<str:code>", ResourceDetailView.as_view(), name="resource-detail"),

    path("shelters", ShelterListView.as_view(), name="shelter-list"),
    # nearest must precede <code>
    path("shelters/nearest", NearestShelterView.as_view(), name="shelter-nearest"),
    path("shelters/<str:code>", ShelterDetailView.as_view(), name="shelter-detail"),
]
