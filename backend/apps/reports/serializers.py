"""reports serializers. IncidentSerializer's output IS the incidents[] entry in
GET /api/state and the incident.new WebSocket payload -- there is exactly one
incident shape in this system and this is it."""
from rest_framework import serializers

from .models import Incident


class IncidentSerializer(serializers.ModelSerializer):
    """Appears in four places: the POST /api/reports response, GET /api/reports
    rows, GET /api/state incidents[], and ws incident.new."""
    class Meta:
        model = Incident
        fields = ["id", "code", "client_ref", "lat", "lon", "kind", "severity",
                  "people", "description", "photo", "source", "reporter_phone",
                  "cell_id", "corroborations", "status", "reported_at",
                  "first_response_at"]
        read_only_fields = ["id", "code", "cell_id", "corroborations", "status",
                            "reported_at", "first_response_at"]


class IncidentCreateSerializer(serializers.Serializer):
    """Validation only -- it does NOT save. The view hands validated_data to
    reports.services.create_incident(), which is the single door in.

    multipart/form-data when a photo is attached, JSON otherwise. client_ref is
    the UUID the phone generates, so a retried POST is a no-op rather than a
    duplicate pin. accuracy_m is kept for triage and dropped before create.
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
    reporter_phone = serializers.CharField(max_length=20, required=False,
                                           allow_blank=True, default="")


class HeatCellSerializer(serializers.Serializer):
    """One heatmap cell. Cells, not pins -- twenty reports of one flood must not
    look like twenty floods."""
    cell_id = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    weight = serializers.FloatField()
    count = serializers.IntegerField()
