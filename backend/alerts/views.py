"""alerts views. The list/register endpoints are real; the two that act
(preposition, broadcast) delegate to services.py."""
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOperator
from common.geo import parse_bbox

from .models import Alert, Device
from .serializers import (
    AlertSerializer,
    BroadcastSerializer,
    DeviceSerializer,
    PrepositionSerializer,
)
from .services import devices_in, numbers_in, preposition, send_push, send_sms_bulk


class AlertListView(generics.ListAPIView):
    """GET /api/alerts?bbox=&active=true

    IN:  bbox   = "min_lon,min_lat,max_lon,max_lat"   optional
         active = "true" | "false"                    optional, default true
    OUT: 200 [AlertSerializer, ...]   newest first

    The console list. Severity-coloured on the IMD green/yellow/orange/red
    ladder by the frontend, not here.
    """
    serializer_class = AlertSerializer

    def get_queryset(self):
        qs = Alert.objects.all()
        if self.request.query_params.get("active", "true").lower() != "false":
            qs = qs.filter(active=True)
        # bbox is validated here so a malformed one is a 400, not a silent
        # unfiltered list. The polygon test itself lives in services.
        parse_bbox(self.request.query_params.get("bbox"))
        return qs


class DeviceRegisterView(APIView):
    """POST /api/devices

    IN:  {token: str, platform: "ANDROID"|"IOS", lat: float, lon: float}
    OUT: 200 {ok: true}
         400 invalid payload

    Upserts on token, so an app that re-registers on every launch is fine.
    Round the location to ~1 km before it reaches here -- coarse location only.
    """
    def post(self, request):
        payload = DeviceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        Device.objects.update_or_create(
            token=payload.validated_data["token"],
            defaults=payload.validated_data,
        )
        return Response({"ok": True})


class PrepositionView(APIView):
    """POST /api/alerts/{id}/preposition

    IN:  {max_units?: int}   default 5
    OUT: 200 [AssignmentSerializer, ...]
         403 non-operator
         404 unknown alert

    Stages idle units toward the predicted impact area before any citizen has
    reported anything.
    """
    permission_classes = [IsOperator]

    def post(self, request, pk):
        from dispatch.serializers import AssignmentSerializer

        payload = PrepositionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        alert = generics.get_object_or_404(Alert, pk=pk)
        made = preposition(alert, payload.validated_data["max_units"])
        return Response(AssignmentSerializer(made, many=True).data)


class BroadcastView(APIView):
    """POST /api/alerts/{id}/broadcast

    IN:  {text: str, channels: ["PUSH"] | ["SMS"] | ["PUSH","SMS"]}
    OUT: 200 {queued: int, devices: int, numbers: int}
         403 non-operator
         404 unknown alert

    Warns citizens inside the polygon. Thousands of sends must not block the
    request, which is why the response says `queued`, not `sent`.
    """
    permission_classes = [IsOperator]

    def post(self, request, pk):
        payload = BroadcastSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        alert = generics.get_object_or_404(Alert, pk=pk)
        text = payload.validated_data["text"]
        channels = payload.validated_data["channels"]

        queued, devices, numbers = 0, [], []
        if "PUSH" in channels:
            devices = list(devices_in(alert.polygon))
            queued += send_push([d.token for d in devices], text, alert)["queued"]
        if "SMS" in channels:
            numbers = numbers_in(alert.polygon)
            queued += send_sms_bulk(numbers, text)["queued"]

        return Response({"queued": queued, "devices": len(devices), "numbers": len(numbers)})
