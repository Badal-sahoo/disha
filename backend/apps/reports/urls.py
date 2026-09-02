from django.urls import path

from .views import HeatmapView, ReportDetailView, ReportListCreateView

urlpatterns = [
    path("reports", ReportListCreateView.as_view(), name="report-list"),
    # heatmap must precede <code> or "heatmap" is matched as an incident code
    path("reports/heatmap", HeatmapView.as_view(), name="report-heatmap"),
    path("reports/<str:code>", ReportDetailView.as_view(), name="report-detail"),
]
