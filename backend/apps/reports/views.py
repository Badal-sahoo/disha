"""reports views: validate -> call service -> serialise -> respond. No business
logic here, which is what lets one create_incident() serve both the app and an
SMS without knowing the difference."""
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.geo import parse_bbox
from apps.dispatch.services.assign import run_cycle

from .models import Incident
from .serializers import HeatCellSerializer, IncidentCreateSerializer, IncidentSerializer
from .services.heatmap import heatmap_cells
from .services.internet_ingestion import report_from_app


class ReportListCreateView(generics.ListCreateAPIView):
    """GET  /api/reports?status=&kind=&since=   -> 200 [IncidentSerializer, ...]
    POST /api/reports                         -> 201 IncidentSerializer

    A photo makes the POST multipart; without one it is plain JSON. A repeated
    client_ref returns the existing row rather than an error.

    The successful create triggers run_cycle("report") HERE, in the view --
    never inside the model's save() and never inside the service, because
    reports must not import dispatch.
    """
    serializer_class = IncidentSerializer

    def get_queryset(self):
        qs = Incident.objects.all()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("since"):
            since = parse_datetime(p["since"])
            if since is None:
                raise ValueError("since must be an ISO 8601 datetime")
            qs = qs.filter(reported_at__gte=since)
        return qs

    def create(self, request, *args, **kwargs):
        payload = IncidentCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        incident = report_from_app(payload.validated_data)
        run_cycle(trigger="report")           # debounced to one solve per 2 s
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class ReportDetailView(generics.RetrieveAPIView):
    """GET /api/reports/{code} -> IncidentSerializer + {assignments: [...]}."""
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    lookup_field = "code"

    def retrieve(self, request, *args, **kwargs):
        from apps.dispatch.serializers import AssignmentSerializer

        incident = self.get_object()
        data = IncidentSerializer(incident).data
        data["assignments"] = AssignmentSerializer(
            incident.assignments.select_related("resource", "shelter").all(), many=True).data
        return Response(data)


class HeatmapView(APIView):
    """GET /api/reports/heatmap?bbox= -> [{cell_id, lat, lon, weight, count}, ...]."""
    def get(self, request):
        bbox = parse_bbox(request.query_params.get("bbox"))
        return Response(HeatCellSerializer(heatmap_cells(bbox), many=True).data)
