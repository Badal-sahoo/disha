from django.urls import path

from .views import (
    AssignmentHeadcountView,
    AssignmentStatusView,
    CommitView,
    ExplainView,
    KpiView,
    PlanView,
    ResponderAssignmentView,
    ResponderLocationView,
    RouteView,
    StateView,
    ZoneDetailView,
    ZoneListCreateView,
)

urlpatterns = [
    path("state", StateView.as_view(), name="state"),
    path("kpi", KpiView.as_view(), name="kpi"),

    # plan and commit must precede <code> or "plan" is read as an assignment code
    path("dispatch/plan", PlanView.as_view(), name="dispatch-plan"),
    path("dispatch/commit", CommitView.as_view(), name="dispatch-commit"),
    path("dispatch/<str:code>/explain", ExplainView.as_view(), name="dispatch-explain"),

    path("zones", ZoneListCreateView.as_view(), name="zone-list"),
    path("zones/<int:pk>", ZoneDetailView.as_view(), name="zone-detail"),

    path("route", RouteView.as_view(), name="route"),

    path("responder/assignment", ResponderAssignmentView.as_view(), name="responder-assignment"),
    path("responder/assignment/<str:code>/status", AssignmentStatusView.as_view(),
         name="responder-status"),
    path("responder/assignment/<str:code>/headcount", AssignmentHeadcountView.as_view(),
         name="responder-headcount"),
    path("responder/location", ResponderLocationView.as_view(), name="responder-location"),
]
