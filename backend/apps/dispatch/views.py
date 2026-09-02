"""dispatch views. Every decision lives in services.py; a view checks input,
calls a service and returns the output.

plan and commit are deliberately SEPARATE endpoints -- that is what lets the
operator flip the A/B toggle as often as they like without dispatching a boat
by accident.
"""
from django.http import Http404
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOperator, IsResponder, current_resource
from apps.common.geo import parse_bbox
from apps.realtime.ws import broadcast

from .models import Assignment, Zone
from .serializers import (
    AssignmentSerializer,
    CommitSerializer,
    ExplainSerializer,
    HeadcountSerializer,
    KpiSerializer,
    LocationSerializer,
    StatusUpdateSerializer,
    ZoneSerializer,
)
from .services.assign import build_plan, commit_plan, open_set, run_cycle
from .services.progress import apply_status, update_unit_location
from .services.reporting import build_state, compute_kpi, explain
from .services.routing import invalidate_zone_cache, route_polyline

class StateView(APIView):
    """GET /api/state?bbox=min_lon,min_lat,max_lon,max_lat

    OUT: 200 {t, incidents[], resources[], shelters[], zones[], assignments[],
              alerts[], kpi{}}   400 malformed bbox

    Called on page load AND after every WebSocket reconnect -- the reconciliation
    path that makes the delta stream safe.
    """
    def get(self, request):
        return Response(build_state(parse_bbox(request.query_params.get("bbox"))))


class PlanView(APIView):
    """GET /api/dispatch/plan

    OUT: 200 {assignments: [...PROPOSED...]}

    A PREVIEW: nothing is written and no unit is told anything.

    No `kpi` here on purpose. The strip shows what the district has ACTUALLY
    achieved, and only that. A predicted set of numbers sitting in the same five
    boxes -- tinted or not -- was read as the real thing, which is exactly the
    confusion the strip exists to prevent.
    """
    def get(self, request):
        incidents, units = open_set(timezone.now())
        return Response({
            "assignments": AssignmentSerializer(build_plan(incidents, units),
                                                many=True).data,
        })


class CommitView(APIView):
    """POST /api/dispatch/commit

    IN:  {codes: ["ASG0088", ...]}  or  {all: true}
    OUT: 200 {committed: int, rejected: [{code, reason}, ...]}
         400 neither codes[] nor all      403 non-operator

    Proposals are never written to the database, so this re-solves and keeps the
    codes the operator ticked. Anything whose unit was taken since they fetched
    the plan comes back in `rejected` -- the human is in the loop, and the world
    moved while they were deciding.
    """
    permission_classes = [IsOperator]

    def post(self, request):
        payload = CommitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        incidents, units = open_set(timezone.now())
        plan = build_plan(incidents, units)
        if not payload.validated_data.get("all"):
            wanted = set(payload.validated_data["codes"])
            plan = [a for a in plan if a.code in wanted]

        return Response(commit_plan(plan))


class ExplainView(APIView):
    """GET /api/dispatch/{code}/explain

    OUT: 200 {w, eta_min, gain, terms{severity, people, age, corroboration},
              alternatives[]}   404 unknown code

    The audit view. Turns a black box into a decision anyone can check.

    Codes come from two different places and both have to resolve here:

      committed -- a real row, looked up directly.
      proposed  -- never written to the database, so it is re-solved and picked
                   out by code, exactly as CommitView does. Looking only in the
                   table 404'd every "Why this unit?" on an uncommitted plan,
                   which is the case the button is actually for.
    """
    def get(self, request, code):
        assignment = (Assignment.objects
                      .select_related("incident", "resource")
                      .filter(code=code)
                      .first())

        if assignment is None:
            incidents, units = open_set(timezone.now())
            assignment = next(
                (a for a in build_plan(incidents, units) if a.code == code),
                None,
            )

        if assignment is None:
            raise Http404("No assignment with that code, proposed or committed.")

        return Response(ExplainSerializer(explain(assignment)).data)


class KpiView(APIView):
    """GET /api/kpi
    OUT: 200 {crit_mean, crit_p90, crit_sla_pct, unreached, awaiting}
    """
    def get(self, request):
        return Response(KpiSerializer(compute_kpi()).data)


class ZoneListCreateView(generics.ListCreateAPIView):
    """GET /api/zones  ·  POST /api/zones {lat, lon, radius_km, severity 1..5}

    Creating a zone drops the zone cache and re-optimises. Water recedes through
    ZoneDetailView, which is the same path in reverse.
    """
    queryset = Zone.objects.filter(active=True)
    serializer_class = ZoneSerializer

    def get_permissions(self):
        return [IsOperator()] if self.request.method == "POST" else super().get_permissions()

    def perform_create(self, serializer):
        zone = serializer.save(source=Zone.Source.OPERATOR, active=True)
        invalidate_zone_cache()
        broadcast("zone.new", ZoneSerializer(zone).data)
        run_cycle(trigger="zone")


class ZoneDetailView(generics.DestroyAPIView):
    """DELETE /api/zones/{id} -> 204. Soft-deletes, so a cleared zone leaves a record."""
    queryset = Zone.objects.filter(active=True)
    serializer_class = ZoneSerializer
    permission_classes = [IsOperator]

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active"])
        invalidate_zone_cache()
        broadcast("zone.removed", {"id": instance.id})
        run_cycle(trigger="zone")


class RouteView(APIView):
    """GET /api/route?from=lat,lon&to=lat,lon&vclass=TRUCK
    OUT: 200 {polyline: [[lat, lon], ...], minutes: float}   400 malformed from/to
    """
    def get(self, request):
        def point(raw, name):
            try:
                lat, lon = (float(x) for x in raw.split(","))
                return lat, lon
            except (AttributeError, ValueError):
                raise ValueError(f"{name} must be 'lat,lon'")

        f_lat, f_lon = point(request.query_params.get("from"), "from")
        t_lat, t_lon = point(request.query_params.get("to"), "to")
        return Response(route_polyline(f_lat, f_lon, t_lat, t_lon,
                                       request.query_params.get("vclass", "TRUCK")))


# ---------------------------------------------------------------------------
# Responder endpoints. The unit comes off the JWT, never out of the URL.
# ---------------------------------------------------------------------------
def _own_assignment(request, code):
    return generics.get_object_or_404(
        Assignment.objects.select_related("incident", "resource"),
        code=code, resource=current_resource(request))


class ResponderAssignmentView(APIView):
    """GET /api/responder/assignment -> 200 AssignmentSerializer | null

    Cold start and reconnect path. The socket is the fast path; this is the truth.
    """
    permission_classes = [IsResponder]

    def get(self, request):
        assignment = (Assignment.objects.select_related("incident", "resource", "shelter")
                      .filter(resource=current_resource(request))
                      .exclude(status__in=[Assignment.Status.COMPLETE,
                                           Assignment.Status.PROPOSED])
                      .order_by("-dispatched_at").first())
        return Response(AssignmentSerializer(assignment).data if assignment else None)


class AssignmentStatusView(APIView):
    """POST /api/responder/assignment/{code}/status {status}
    OUT: 200 {ok, next}   400 illegal transition   403 not this unit's   404 unknown
    """
    permission_classes = [IsResponder]

    def post(self, request, code):
        payload = StatusUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return Response(apply_status(_own_assignment(request, code),
                                     payload.validated_data["status"]))


class AssignmentHeadcountView(APIView):
    """POST /api/responder/assignment/{code}/headcount {rescued}

    Ground truth versus the citizen's estimate. Closes the incident.
    """
    permission_classes = [IsResponder]

    def post(self, request, code):
        payload = HeadcountSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return Response(apply_status(_own_assignment(request, code),
                                     Assignment.Status.COMPLETE,
                                     rescued=payload.validated_data["rescued"]))


class ResponderLocationView(APIView):
    """POST /api/responder/location {lat, lon, ts?} -> 200 {ok: true}

    The 20-second beacon: moves the unit and pushes it to every dashboard.
    """
    permission_classes = [IsResponder]

    def post(self, request):
        payload = LocationSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        update_unit_location(current_resource(request),
                             payload.validated_data["lat"],
                             payload.validated_data["lon"])
        return Response({"ok": True})
