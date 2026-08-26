"""dispatch serializers. AssignmentSerializer's shape is what the ops dashboard
draws lines from, what a responder phone receives on /ws/unit/{code}, and what
GET /api/state returns as assignments[]."""
from rest_framework import serializers

from .models import Assignment, Zone


class AssignmentSerializer(serializers.ModelSerializer):
    """OUT (POST /api/dispatch/commit rows, GET /api/state assignments[],
            ws assignment.new / assignment.update, GET /api/responder/assignment):
      {
        id:             int,
        code:           str,        # "ASG0088"
        incident:       int,        # Incident PK
        incident_code:  str,        # "INC0142"
        incident_lat:   float,      # denormalised so the map can draw the line
        incident_lon:   float,      #   without a second lookup
        resource:       int,        # Resource PK
        resource_code:  str,        # "BOAT-04"
        resource_lat:   float,
        resource_lon:   float,
        shelter:        int|None,   # Shelter PK, null when no evacuation
        shelter_code:   str|None,
        eta_min:        float,      # travel minutes, unit -> incident
        gain:           float,      # priority-weighted minutes saved; bigger is better.
                                    # This is what makes /explain possible later.
        policy:         str,        # "OPTIMIZED" | "GREEDY" | "GREEDY_SEVERITY"
        status:         str,        # "PROPOSED"|"DISPATCHED"|"ACCEPTED"|"EN_ROUTE"
                                    # |"ON_SCENE"|"TRANSPORTING"|"COMPLETE"
        rescued_count:  int|None,   # ground truth, set at COMPLETE
        dispatched_at:  str|None,   # ISO 8601
        arrived_at:     str|None,
        completed_at:   str|None,
      }
      PROPOSED rows are previews no unit ever sees. Only DISPATCHED and beyond
      are real.
    """
    incident_code = serializers.CharField(source="incident.code", read_only=True)
    incident_lat = serializers.FloatField(source="incident.lat", read_only=True)
    incident_lon = serializers.FloatField(source="incident.lon", read_only=True)
    resource_code = serializers.CharField(source="resource.code", read_only=True)
    resource_lat = serializers.FloatField(source="resource.lat", read_only=True)
    resource_lon = serializers.FloatField(source="resource.lon", read_only=True)
    shelter_code = serializers.CharField(source="shelter.code", read_only=True, default=None)

    class Meta:
        model = Assignment
        fields = ["id", "code", "incident", "incident_code", "incident_lat",
                  "incident_lon", "resource", "resource_code", "resource_lat",
                  "resource_lon", "shelter", "shelter_code", "eta_min", "gain",
                  "policy", "status", "rescued_count", "dispatched_at",
                  "arrived_at", "completed_at"]
        read_only_fields = fields


class ZoneSerializer(serializers.ModelSerializer):
    """POST /api/zones in, and the ws zone.new payload out.

    IN:  {lat: float, lon: float, radius_km: float, severity: int 1..5}
    OUT: {
      id:         int,
      lat:        float,
      lon:        float,
      radius_km:  float,
      severity:   int,     # 5 = impassable to anything without a hull;
                           # 1..4 just slow wheeled units down (engine.BLOCKED_DETOUR)
      source:     str,     # "OPERATOR" | "CAP"
      active:     bool,
      created_at: str,     # ISO 8601
    }
    """
    class Meta:
        model = Zone
        fields = ["id", "lat", "lon", "radius_km", "severity", "source", "active", "created_at"]
        read_only_fields = ["id", "source", "active", "created_at"]


class KpiSerializer(serializers.Serializer):
    """The five numbers on the dashboard strip. Computed PER POLICY so the A/B
    toggle shows a real difference rather than the same figures twice.

    OUT: {
      crit_mean:    float,   # mean minutes to first response, severity >= 4
      crit_p90:     float,   # 90th percentile of the same
      crit_sla_pct: float,   # 0..100, share of critical incidents reached inside the SLA
      unreached:    int,     # open critical incidents with no assignment at all
      awaiting:     int,     # all open incidents with no assignment
    }
    """
    crit_mean = serializers.FloatField()
    crit_p90 = serializers.FloatField()
    crit_sla_pct = serializers.FloatField()
    unreached = serializers.IntegerField()
    awaiting = serializers.IntegerField()


class ExplainSerializer(serializers.Serializer):
    """GET /api/dispatch/{code}/explain -- the audit view. Turns a black box
    into a decision anyone can check, and it is your answer to "why should NDRF
    trust this?"

    OUT: {
      w:        float,     # the incident's total priority, 0..1
      eta_min:  float,
      gain:     float,     # w * (DISPATCH_HORIZON_MIN - eta_min)
      terms: {             # the four weighted contributions, summing to w
        severity:      float,   # 0.45 * (severity-1)/4
        people:        float,   # 0.25 * min(people/50, 1)
        age:           float,   # 0.20 * min(age_min/45, 1)
        corroboration: float,   # 0.10 * min((corrob-1)/4, 1)
      },
      alternatives: [      # optional: the runners-up, for "why not that boat?"
        {resource_code: str, eta_min: float, gain: float, reason: str},
      ],
    }
    """
    w = serializers.FloatField()
    eta_min = serializers.FloatField()
    gain = serializers.FloatField()
    terms = serializers.DictField(child=serializers.FloatField())
    alternatives = serializers.ListField(child=serializers.DictField(), required=False)


class PlanSerializer(serializers.Serializer):
    """GET /api/dispatch/plan

    OUT: {
      policy:      str,                    # echoed back
      assignments: [AssignmentSerializer, ...],   # status is always "PROPOSED"
      kpi:         KpiSerializer,
    }
    """
    policy = serializers.CharField()
    assignments = AssignmentSerializer(many=True)
    kpi = KpiSerializer()


class CommitSerializer(serializers.Serializer):
    """POST /api/dispatch/commit

    IN:  {codes: [str, ...]}   -- assignment codes to commit, e.g. ["ASG0088"]
         or {all: true}        -- commit the whole current plan
         Exactly one of the two.
    """
    codes = serializers.ListField(child=serializers.CharField(), required=False)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get("codes") and not attrs.get("all"):
            raise serializers.ValidationError("Send either codes[] or all=true.")
        return attrs


class StatusUpdateSerializer(serializers.Serializer):
    """POST /api/responder/assignment/{code}/status

    IN:  {status: str, note?: str}
         status walks ACCEPTED -> EN_ROUTE -> ON_SCENE -> TRANSPORTING -> COMPLETE.
         Each transition frees or holds the unit in the next dispatch cycle.
    """
    status = serializers.ChoiceField(choices=Assignment.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class HeadcountSerializer(serializers.Serializer):
    """POST /api/responder/assignment/{code}/headcount

    IN:  {rescued: int >= 0, note?: str}
         Actual people rescued versus the citizen's estimate. This is what
         closes an incident and the ground truth the after-action report is
         built from.
    """
    rescued = serializers.IntegerField(min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class LocationSerializer(serializers.Serializer):
    """POST /api/responder/location -- the 20-second beacon.

    IN:  {lat: float, lon: float, ts?: ISO 8601}
         ts is optional; the server stamps now() when it is absent.
    """
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    ts = serializers.DateTimeField(required=False)


class TimelineEventSerializer(serializers.Serializer):
    """GET /api/timeline row. The event log IS the timeline -- do not build a
    second store for it.

    OUT: {
      t:      str,    # ISO 8601
      type:   str,    # same 10 strings as the WebSocket event types
      data:   obj,    # the payload that was broadcast at the time
    }
    F15 folds these back into state with the SAME applyDelta reducer the live
    dashboard uses, replayed from zero.
    """
    t = serializers.DateTimeField()
    type = serializers.CharField()
    data = serializers.DictField()
