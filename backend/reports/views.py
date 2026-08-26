"""reports views. Fully wired: validate -> call service -> serialise -> respond.
No business logic lives here, which is what lets the same create_incident()
serve the app, an SMS and an IVR call without knowing the difference.
"""
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.geo import parse_bbox
from dispatch.services import run_cycle

from .models import Incident
from .serializers import (
    HeatCellSerializer,
    IncidentCreateSerializer,
    IncidentSerializer,
)
from .services import create_incident, heatmap_cells


class ReportListCreateView(generics.ListCreateAPIView):
    """GET  /api/reports?status=&kind=&since=
    POST /api/reports

    GET  IN:  status = "OPEN"|"ASSIGNED"|"RESOLVED"   optional
              kind   = "FLOOD"|"CYCLONE"|"LANDSLIDE"  optional
              since  = ISO 8601                       optional, reported_at >= since
         OUT: 200 [IncidentSerializer, ...]  (newest first)

    POST IN:  IncidentCreateSerializer fields (see that class)
         OUT: 201 IncidentSerializer  -- or 200 with the existing row when
              client_ref was already seen (a retry is a no-op, not an error)
              400 {detail, code:"invalid"} on bad input
              501 {detail, code:"not_implemented"} while the service is a stub

    A successful create triggers dispatch.services.run_cycle("report") HERE,
    in the view -- never inside the model's save() and never inside the service,
    because reports must not import dispatch (blueprint 01).
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
        data = dict(payload.validated_data)
        data.pop("accuracy_m", None)          # trusted for triage, not stored

        incident = create_incident(data, source=Incident.Source.APP)
        run_cycle(trigger="report")           # debounced to one solve per 2 s

        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class ReportDetailView(generics.RetrieveAPIView):
    """GET /api/reports/{code}

    IN:  code = str in the path        # "INC0142"
    OUT: 200 IncidentSerializer + {assignments: [AssignmentSerializer, ...]}
         404 when no such code
    """
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    lookup_field = "code"

    def retrieve(self, request, *args, **kwargs):
        from dispatch.serializers import AssignmentSerializer

        incident = self.get_object()
        data = IncidentSerializer(incident).data
        data["assignments"] = AssignmentSerializer(
            incident.assignments.select_related("resource", "shelter").all(), many=True
        ).data
        return Response(data)


class HeatmapView(APIView):
    """GET /api/reports/heatmap?bbox=min_lon,min_lat,max_lon,max_lat

    IN:  bbox = str | absent
    OUT: 200 [{cell_id, lat, lon, weight, count}, ...]
         400 when bbox is malformed
    """
    def get(self, request):
        bbox = parse_bbox(request.query_params.get("bbox"))
        return Response(HeatCellSerializer(heatmap_cells(bbox), many=True).data)
