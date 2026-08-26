"""dispatch views. Every route here is wired; the decisions all live in
services.py. Note that plan and commit are deliberately SEPARATE endpoints --
that is what lets the operator flip the A/B toggle as often as they like
without dispatching a single boat by accident.
"""
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOperator, IsResponder, current_resource
from common.geo import parse_bbox

from .models import Assignment, Zone
from .serializers import (
    AssignmentSerializer,
    CommitSerializer,
    ExplainSerializer,
    HeadcountSerializer,
    KpiSerializer,
    LocationSerializer,
    StatusUpdateSerializer,
    TimelineEventSerializer,
    ZoneSerializer,
)
from .services import (
    after_action_report,
    apply_status,
    build_plan,
    build_state,
    commit_plan,
    compute_kpi,
    explain,
    invalidate_zone_cache,
    open_set,
    route_polyline,
    run_cycle,
    timeline_events,
    update_unit_location,
)

POLICIES = ("OPTIMIZED", "GREEDY", "GREEDY_SEVERITY")


class StateView(APIView):
    """GET /api/state?bbox=min_lon,min_lat,max_lon,max_lat

    IN:  bbox = str | absent
    OUT: 200 {t, incidents[], resources[], shelters[], zones[], assignments[],
              alerts[], kpi{}}
         400 malformed bbox

    Called on page load AND after every WebSocket reconnect. The reconciliation
    path that makes the delta stream safe.
    """
    def get(self, request):
        return Response(build_state(parse_bbox(request.query_params.get("bbox"))))


class PlanView(APIView):
    """GET /api/dispatch/plan?policy=OPTIMIZED|GREEDY|GREEDY_SEVERITY

    IN:  policy = str, default "OPTIMIZED"
    OUT: 200 {policy, assignments: [...PROPOSED rows...], kpi: {...}}
         400 unknown policy

    A PREVIEW. Nothing is written, no unit is told anything. The server computes
    all three policies from the SAME state, which is what makes the dashboard
    comparison honest rather than a claim.
    """
    def get(self, request):
        policy = request.query_params.get("policy", "OPTIMIZED")
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")

        incidents, units = open_set(timezone.now())
        proposed = build_plan(incidents, units, policy)
        return Response({
            "policy": policy,
            "assignments": AssignmentSerializer(proposed, many=True).data,
            "kpi": KpiSerializer(compute_kpi(policy)).data,
        })


class CommitView(APIView):
    """POST /api/dispatch/commit

    IN:  {codes: ["ASG0088", ...]}  or  {all: true}
    OUT: 200 {committed: int, rejected: [{code, reason}, ...]}
         400 neither codes[] nor all
         403 non-operator

    Rejects anything whose unit was taken since the plan was fetched -- the
    human is in the loop, and the world moved while they were deciding.
    """
    permission_classes = [IsOperator]

    def post(self, request):
        payload = CommitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        if payload.validated_data.get("all"):
            incidents, units = open_set(timezone.now())
            selected = build_plan(incidents, units, "OPTIMIZED")
        else:
            selected = list(
                Assignment.objects.select_related("incident", "resource", "shelter")
                .filter(code__in=payload.validated_data["codes"],
                        status=Assignment.Status.PROPOSED)
            )

        return Response(commit_plan(selected))


class ExplainView(APIView):
    """GET /api/dispatch/{code}/explain

    IN:  code = str in the path      # "ASG0088"
    OUT: 200 {w, eta_min, gain, terms{severity, people, age, corroboration},
              alternatives[]}
         404 unknown code

    The audit view. Turns a black box into a decision anyone can check.
    """
    def get(self, request, code):
        assignment = generics.get_object_or_404(
            Assignment.objects.select_related("incident", "resource"), code=code
        )
        return Response(ExplainSerializer(explain(assignment)).data)


class KpiView(APIView):
    """GET /api/kpi?policy=OPTIMIZED

    IN:  policy = str, default "OPTIMIZED"
    OUT: 200 {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting}
    """
    def get(self, request):
        policy = request.query_params.get("policy", "OPTIMIZED")
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")
        return Response(KpiSerializer(compute_kpi(policy)).data)


class ZoneListCreateView(generics.ListCreateAPIView):
    """GET  /api/zones
    POST /api/zones

    POST IN:  {lat: float, lon: float, radius_km: float, severity: int 1..5}
         OUT: 201 ZoneSerializer
              403 non-operator

    Creating a zone reweights the road graph, drops the Dijkstra cache, re-warms
    and re-optimises -- measured at ~47 ms end to end. Ten seconds of demo,
    disproportionate impact.
    """
    queryset = Zone.objects.filter(active=True)
    serializer_class = ZoneSerializer

    def get_permissions(self):
        return [IsOperator()] if self.request.method == "POST" else super().get_permissions()

    def perform_create(self, serializer):
        zone = serializer.save(source=Zone.Source.OPERATOR, active=True)
        invalidate_zone_cache()

        from realtime.broadcast import broadcast
        broadcast("zone.new", ZoneSerializer(zone).data)
        run_cycle(trigger="zone")


class ZoneDetailView(generics.DestroyAPIView):
    """DELETE /api/zones/{id}

    IN:  id = int in the path
    OUT: 204
         403 non-operator
         404 unknown id

    Water recedes. Same rebuild path in reverse. Soft-deletes (active=False) so
    the timeline can still replay the period the road was cut.
    """
    queryset = Zone.objects.filter(active=True)
    serializer_class = ZoneSerializer
    permission_classes = [IsOperator]

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active"])
        invalidate_zone_cache()

        from realtime.broadcast import broadcast
        broadcast("zone.removed", {"id": instance.id})
        run_cycle(trigger="zone")


class RouteView(APIView):
    """GET /api/route?from=lat,lon&to=lat,lon&vclass=TRUCK

    IN:  from   = "19.81,85.83"   required
         to     = "19.86,85.90"   required
         vclass = "TRUCK"|"BOAT"|"TEAM"|"AMBULANCE"   optional, default TRUCK
    OUT: 200 {polyline: [[lat, lon], ...], minutes: float}
         400 malformed from/to

    Routes around the water, not through it.
    """
    def get(self, request):
        def _point(raw, name):
            try:
                lat, lon = (float(x) for x in raw.split(","))
                return lat, lon
            except (AttributeError, ValueError):
                raise ValueError(f"{name} must be 'lat,lon'")

        f_lat, f_lon = _point(request.query_params.get("from"), "from")
        t_lat, t_lon = _point(request.query_params.get("to"), "to")
        vclass = request.query_params.get("vclass", "TRUCK")
        return Response(route_polyline(f_lat, f_lon, t_lat, t_lon, vclass))


class TimelineView(APIView):
    """GET /api/timeline?from=ISO&to=ISO

    IN:  from, to = ISO 8601   both required
    OUT: 200 [{t, type, data}, ...]   ascending
         400 unparseable dates
    """
    def get(self, request):
        start = parse_datetime(request.query_params.get("from", "") or "")
        end = parse_datetime(request.query_params.get("to", "") or "")
        if start is None or end is None:
            raise ValueError("from and to must both be ISO 8601 datetimes")
        return Response(TimelineEventSerializer(timeline_events(start, end), many=True).data)


class AfterActionView(APIView):
    """GET /api/after-action?from=ISO&to=ISO&format=csv|pdf

    IN:  from, to = ISO 8601, format = "csv" (default) | "pdf"
    OUT: 200 a file download (Content-Disposition: attachment)
         400 unparseable dates
    """
    def get(self, request):
        from django.http import HttpResponse

        start = parse_datetime(request.query_params.get("from", "") or "")
        end = parse_datetime(request.query_params.get("to", "") or "")
        if start is None or end is None:
            raise ValueError("from and to must both be ISO 8601 datetimes")

        blob, content_type, filename = after_action_report(
            start, end, request.query_params.get("format", "csv")
        )
        response = HttpResponse(blob, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Responder endpoints. The unit comes off the JWT, never out of the URL.
# ---------------------------------------------------------------------------
class ResponderAssignmentView(APIView):
    """GET /api/responder/assignment

    IN:  -- (the unit is derived from the token via accounts.current_resource)
    OUT: 200 AssignmentSerializer | null
         403 caller is not a responder, or has no unit attached

    Cold start and reconnect path. The socket is the fast path; this is the truth.
    """
    permission_classes = [IsResponder]

    def get(self, request):
        resource = current_resource(request)
        assignment = (
            Assignment.objects.select_related("incident", "resource", "shelter")
            .filter(resource=resource)
            .exclude(status__in=[Assignment.Status.COMPLETE, Assignment.Status.PROPOSED])
            .order_by("-dispatched_at")
            .first()
        )
        return Response(AssignmentSerializer(assignment).data if assignment else None)


class AssignmentStatusView(APIView):
    """POST /api/responder/assignment/{code}/status

    IN:  {status: str, note?: str}
         ACCEPTED -> EN_ROUTE -> ON_SCENE -> TRANSPORTING -> COMPLETE
    OUT: 200 {ok: true, next: str|null}
         400 illegal transition
         403 not this unit's assignment
         404 unknown code
    """
    permission_classes = [IsResponder]

    def post(self, request, code):
        payload = StatusUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        assignment = generics.get_object_or_404(
            Assignment.objects.select_related("incident", "resource"),
            code=code, resource=current_resource(request),
        )
        return Response(apply_status(assignment,
                                     payload.validated_data["status"],
                                     payload.validated_data.get("note", "")))


class AssignmentHeadcountView(APIView):
    """POST /api/responder/assignment/{code}/headcount

    IN:  {rescued: int, note?: str}
    OUT: 200 {ok: true, next: null}
         403 not this unit's assignment
         404 unknown code

    Ground truth versus the citizen's estimate. Closes the incident and feeds
    the after-action report.
    """
    permission_classes = [IsResponder]

    def post(self, request, code):
        payload = HeadcountSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        assignment = generics.get_object_or_404(
            Assignment.objects.select_related("incident", "resource"),
            code=code, resource=current_resource(request),
        )
        return Response(apply_status(assignment,
                                     Assignment.Status.COMPLETE,
                                     payload.validated_data.get("note", ""),
                                     rescued=payload.validated_data["rescued"]))


class ResponderLocationView(APIView):
    """POST /api/responder/location

    IN:  {lat: float, lon: float, ts?: ISO 8601}
    OUT: 200 {ok: true}
         403 caller is not a responder

    The 20-second beacon. Also updates the unit's origin node for the next solve.
    """
    permission_classes = [IsResponder]

    def post(self, request):
        payload = LocationSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        update_unit_location(
            current_resource(request),
            payload.validated_data["lat"],
            payload.validated_data["lon"],
            payload.validated_data.get("ts"),
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)
