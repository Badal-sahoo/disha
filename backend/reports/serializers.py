"""reports serializers. IncidentSerializer's output shape IS the `incidents[]`
entry inside GET /api/state and the `incident.new` WebSocket payload -- there is
exactly one incident shape in this system and this is it."""
from rest_framework import serializers

from .models import Incident


class IncidentSerializer(serializers.ModelSerializer):
    """OUT (this exact shape appears in 4 places: POST /api/reports response,
    GET /api/reports rows, GET /api/state incidents[], ws incident.new):
      {
        id:                int,
        code:              str,        # "INC0142"
        client_ref:        str,        # the phone's UUID, dedupe key
        lat:               float,
        lon:               float,
        kind:              str,        # "FLOOD" | "CYCLONE" | "LANDSLIDE"
        severity:          int,        # 1..5
        people:            int,
        description:       str,
        photo:             str|None,   # media URL
        source:            str,        # "APP" | "SMS" | "IVR"
        reporter_phone:    str,
        cell_id:           str,        # "19.81,85.83"
        corroborations:    int,
        status:            str,        # "OPEN" | "ASSIGNED" | "RESOLVED"
        reported_at:       str,        # ISO 8601
        first_response_at: str|None,   # ISO 8601 -- every benchmark derives from this
      }
    """
    class Meta:
        model = Incident
        fields = [
            "id", "code", "client_ref", "lat", "lon", "kind", "severity",
            "people", "description", "photo", "source", "reporter_phone",
            "cell_id", "corroborations", "status", "reported_at",
            "first_response_at",
        ]
        read_only_fields = [
            "id", "code", "cell_id", "corroborations", "status",
            "reported_at", "first_response_at",
        ]


class IncidentCreateSerializer(serializers.Serializer):
    """Validation only -- it does NOT save. The view hands validated_data to
    reports.services.create_incident(), which is the single door in.

    IN (multipart/form-data when a photo is attached, else JSON):
      client_ref:     str    required, unique. UUID the phone generates so a
                             retried POST is a no-op instead of a duplicate pin.
      lat:            float  required, -90..90
      lon:            float  required, -180..180
      kind:           str    required, "FLOOD" | "CYCLONE" | "LANDSLIDE"
      severity:       int    required, 1..5
      people:         int    optional, default 1
      description:    str    optional, default ""
      photo:          file   optional, <= 500 KB, image/*
      accuracy_m:     float  optional -- GPS accuracy, NOT stored on the model.
                             Kept here so ingest can decide whether to trust the
                             fix; drop it before create.
      reporter_phone: str    optional, default ""
    """
    client_ref = serializers.CharField(max_length=64)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    kind = serializers.ChoiceField(choices=Incident.Kind.choices)
    severity = serializers.IntegerField(min_value=1, max_value=5)
    people = serializers.IntegerField(min_value=1, default=1)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    photo = serializers.ImageField(required=False, allow_null=True)
    accuracy_m = serializers.FloatField(required=False, allow_null=True)
    reporter_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class HeatCellSerializer(serializers.Serializer):
    """GET /api/reports/heatmap row.

    OUT: {
      cell_id: str,    # "19.81,85.83"
      lat:     float,  # cell centre
      lon:     float,
      weight:  float,  # SUM(severity * corroborations) over open incidents in the cell
      count:   int,    # how many incidents rolled up
    }
    Cells, not pins -- twenty reports of one flood must not look like twenty floods.
    """
    cell_id = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    weight = serializers.FloatField()
    count = serializers.IntegerField()
