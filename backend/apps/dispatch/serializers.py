"""dispatch serializers. AssignmentSerializer's shape is what the map draws its
lines from and what GET /api/state returns as assignments[]."""
from rest_framework import serializers

from .models import Assignment, Zone


class AssignmentSerializer(serializers.ModelSerializer):
    """Incident and resource coordinates are denormalised onto the row so the
    map can draw the line without a second lookup. PROPOSED rows are previews no
    unit ever sees; only DISPATCHED and beyond are real.

    `polyline` is the road path from the unit to the incident, present only when
    USE_ROAD_GRAPH is on. The frontend draws it when it is there and falls back
    to a straight segment when it is not.
    """
    incident_code = serializers.CharField(source="incident.code", read_only=True)
    incident_lat = serializers.FloatField(source="incident.lat", read_only=True)
    incident_lon = serializers.FloatField(source="incident.lon", read_only=True)
    resource_code = serializers.CharField(source="resource.code", read_only=True)
    resource_lat = serializers.FloatField(source="resource.lat", read_only=True)
    resource_lon = serializers.FloatField(source="resource.lon", read_only=True)
    shelter_code = serializers.CharField(source="shelter.code", read_only=True, default=None)
    # SHELTER | HOSPITAL. The dashboard says "-> DHH Puri" differently from
    # "-> Konark MCS", and an operator must be able to tell at a glance that a
    # casualty is going somewhere with a doctor.
    shelter_kind = serializers.CharField(source="shelter.kind", read_only=True, default=None)
    polyline = serializers.SerializerMethodField()

    def get_polyline(self, assignment):
        """The road path, thinned for drawing. None when we route on straight lines."""
        from .roadnet import VEHICLE_CLASS, WHEELED, simplify
        from .services.routing import road_network

        network = road_network()
        if network is None or assignment.resource_id is None:
            return None

        # From where the unit set out, not where it has already been moved to.
        start_lat = assignment.origin_lat if assignment.origin_lat is not None \
            else assignment.resource.lat
        start_lon = assignment.origin_lon if assignment.origin_lon is not None \
            else assignment.resource.lon

        route = network.route(
            start_lat, start_lon,
            assignment.incident.lat, assignment.incident.lon,
            VEHICLE_CLASS.get(assignment.resource.kind, WHEELED),
        )
        return simplify(route["polyline"]) or None

    class Meta:
        model = Assignment
        fields = ["id", "code", "incident", "incident_code", "incident_lat",
                  "incident_lon", "resource", "resource_code", "resource_lat",
                  "resource_lon", "origin_lat", "origin_lon",
                  "shelter", "shelter_code", "shelter_kind", "eta_min", "gain",
                  "status", "leg", "rescued_count", "dispatched_at",
                  "arrived_at", "completed_at", "polyline"]
        read_only_fields = fields


class ZoneSerializer(serializers.ModelSerializer):
    """POST /api/zones in, ws zone.new out.

    severity 5 is impassable to anything without a hull; 1..4 only slow wheeled
    units down (engine.BLOCKED_DETOUR).
    """
    class Meta:
        model = Zone
        fields = ["id", "lat", "lon", "radius_km", "severity", "source", "active", "created_at"]
        read_only_fields = ["id", "source", "active", "created_at"]


class KpiSerializer(serializers.Serializer):
    """The five numbers on the dashboard strip.

    crit_* cover severity >= 4 only; unreached and awaiting count open incidents
    with no assignment.
    """
    # Nullable: null means "no unit has arrived yet", which the dashboard shows
    # as "--". Zero would mean an instant response and read as a perfect score.
    crit_mean = serializers.FloatField(allow_null=True)
    crit_p90 = serializers.FloatField(allow_null=True)
    crit_sla_pct = serializers.FloatField(allow_null=True)
    unreached = serializers.IntegerField()
    awaiting = serializers.IntegerField()


class ExplainSerializer(serializers.Serializer):
    """The audit view: w is the incident's total priority 0..1, terms are the
    four weighted contributions that sum to it, and alternatives are the
    runners-up with why each lost."""
    w = serializers.FloatField()
    eta_min = serializers.FloatField()
    gain = serializers.FloatField()
    terms = serializers.DictField(child=serializers.FloatField())
    alternatives = serializers.ListField(child=serializers.DictField(), required=False)
    # The clustered scene the priority was computed from -- reports, people,
    # severity, corroborations. Without it the panel quotes one caller's
    # headcount to justify a decision made on the whole village's.
    scene = serializers.DictField(required=False)


class CommitSerializer(serializers.Serializer):
    """{codes: [...]} to commit specific proposals, or {all: true} for the whole
    current plan. Exactly one of the two."""
    codes = serializers.ListField(child=serializers.CharField(), required=False)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get("codes") and not attrs.get("all"):
            raise serializers.ValidationError("Send either codes[] or all=true.")
        return attrs


class StatusUpdateSerializer(serializers.Serializer):
    """status walks ACCEPTED -> EN_ROUTE -> ON_SCENE -> TRANSPORTING -> COMPLETE;
    each transition frees or holds the unit in the next dispatch cycle."""
    status = serializers.ChoiceField(choices=Assignment.Status.choices)


class HeadcountSerializer(serializers.Serializer):
    """Actual people rescued versus the citizen's estimate. This closes the incident."""
    rescued = serializers.IntegerField(min_value=0)


class LocationSerializer(serializers.Serializer):
    """The 20-second beacon. ts is optional; the server stamps now() without it."""
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    ts = serializers.DateTimeField(required=False)
