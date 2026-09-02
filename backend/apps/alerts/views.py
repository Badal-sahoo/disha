"""alerts views: list the warnings the CAP feed brought in."""
from rest_framework import generics

from apps.common.geo import parse_bbox

from .models import Alert
from .serializers import AlertSerializer


class AlertListView(generics.ListAPIView):
    """GET /api/alerts?bbox=&active=true -- newest first.

    The frontend colours these on the IMD green/yellow/orange/red ladder.
    """
    serializer_class = AlertSerializer

    def get_queryset(self):
        qs = Alert.objects.all()
        if self.request.query_params.get("active", "true").lower() != "false":
            qs = qs.filter(active=True)
        # Validated here so a malformed bbox is a 400 rather than a silent
        # unfiltered list; the polygon test itself lives in services.
        parse_bbox(self.request.query_params.get("bbox"))
        return qs
