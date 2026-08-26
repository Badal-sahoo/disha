"""alerts serializers -- CAP warnings in, device registrations out."""
from rest_framework import serializers

from .models import Alert, Device


class AlertSerializer(serializers.ModelSerializer):
    """OUT (GET /api/alerts rows, GET /api/state alerts[], ws alert.new):
      {
        id:         int,
        identifier: str,          # the CAP identifier. Unique -> re-polling the
                                  #   same feed never duplicates a row.
        event:      str,          # "Cyclone Warning"
        severity:   str,          # "Minor"|"Moderate"|"Severe"|"Extreme"
        urgency:    str,          # "Immediate"|"Expected"|"Future"|"Past"|""
        certainty:  str,          # "Observed"|"Likely"|"Possible"|"Unlikely"|""
        polygon:    [[lat, lon], ...],   # NOTE lat first. GeoJSON flips this;
                                         #   convert only at the GeoJSON boundary.
        sent_at:    str,          # ISO 8601
        expires_at: str|None,
        active:     bool,
      }
      raw_xml is deliberately NOT exposed -- it is for you at 1 a.m. when a field
      parsed wrong, not for the wire.
    """
    class Meta:
        model = Alert
        fields = ["id", "identifier", "event", "severity", "urgency", "certainty",
                  "polygon", "sent_at", "expires_at", "active"]
        read_only_fields = fields


class DeviceSerializer(serializers.ModelSerializer):
    """POST /api/devices

    IN:  {
      token:    str,     # FCM/APNs token, unique
      platform: str,     # "ANDROID" | "IOS"
      lat:      float,   # ROUND TO ~1 km BEFORE SAVING. You never need street
      lon:      float,   #   precision to warn someone a cyclone is coming.
    }
    OUT: 200 {ok: true}    -- upsert on token, so re-registering is safe
    """
    class Meta:
        model = Device
        fields = ["token", "platform", "lat", "lon"]


class PrepositionSerializer(serializers.Serializer):
    """POST /api/alerts/{id}/preposition

    IN:  {max_units?: int}      # default 5; how many idle units to stage
    OUT: [AssignmentSerializer, ...]   the staged dispatches

    The early-warning payoff, and demo beat two: units move before anyone has
    reported anything.
    """
    max_units = serializers.IntegerField(min_value=1, max_value=50, required=False, default=5)


class BroadcastSerializer(serializers.Serializer):
    """POST /api/alerts/{id}/broadcast

    IN:  {
      text:     str,          # <= 160 chars if SMS is in channels
      channels: [str],        # any of ["PUSH", "SMS"]
    }
    OUT: {queued: int, devices: int, numbers: int}
         queued  = messages handed to the sender
         devices = registered devices found inside the polygon
         numbers = distinct phone numbers found (from reports_incident.reporter_phone)
    """
    text = serializers.CharField(max_length=480)
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=["PUSH", "SMS"]),
        allow_empty=False,
    )
