from django.urls import path

from .views import (
    NearestShelterView,
    ResourceDetailView,
    ResourceListView,
    ShelterDetailView,
    ShelterListView,
    SupplyCommitView,
    SupplyListView,
    SupplyPlanView,
)

urlpatterns = [
    path("resources", ResourceListView.as_view(), name="resource-list"),
    path("resources/<str:code>", ResourceDetailView.as_view(), name="resource-detail"),

    path("shelters", ShelterListView.as_view(), name="shelter-list"),
    # nearest must precede <code>
    path("shelters/nearest", NearestShelterView.as_view(), name="shelter-nearest"),
    path("shelters/<str:code>", ShelterDetailView.as_view(), name="shelter-detail"),

    path("supply", SupplyListView.as_view(), name="supply-list"),
    path("supply/plan", SupplyPlanView.as_view(), name="supply-plan"),
    path("supply/commit", SupplyCommitView.as_view(), name="supply-commit"),
]
