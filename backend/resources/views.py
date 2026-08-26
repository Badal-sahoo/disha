"""resources views. Pure-CRUD reads are real generic views -- that is
boilerplate, not logic, and it lets the dashboard be exercised on day 1.
Anything with a decision in it delegates to services.py.
"""
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOperator

from .models import Resource, Shelter, SupplyStock
from .serializers import (
    NearestShelterSerializer,
    ResourcePatchSerializer,
    ResourceSerializer,
    ShelterPatchSerializer,
    ShelterSerializer,
    SupplyFlowSerializer,
    SupplyStockSerializer,
)
from .services import adjust_occupancy, commit_supply_plan, compute_supply_plan, nearest_shelter


class ResourceListView(generics.ListAPIView):
    """GET /api/resources?status=&kind=

    IN:  status = "IDLE"|"ENROUTE"|"ONSCENE"|"TRANSPORTING"|"OUT_OF_SERVICE"  optional
         kind   = "TEAM"|"BOAT"|"TRUCK"|"AMBULANCE"                           optional
    OUT: 200 [ResourceSerializer, ...]   ordered by code
    """
    serializer_class = ResourceSerializer

    def get_queryset(self):
        qs = Resource.objects.all()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        return qs


class ResourceDetailView(generics.RetrieveUpdateAPIView):
    """GET   /api/resources/{code}
    PATCH /api/resources/{code}

    PATCH IN:  {status?, lat?, lon?, capacity?}   -- see ResourcePatchSerializer
          OUT: 200 ResourceSerializer
               403 when the caller is not an operator
               404 unknown code

    A status change here takes effect on the NEXT dispatch cycle -- the view
    does not re-solve. Flipping a unit to OUT_OF_SERVICE removes it from
    resources.services.available_units() immediately.
    """
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    lookup_field = "code"
    permission_classes = [IsOperator]

    def patch(self, request, *args, **kwargs):
        payload = ResourcePatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)

        resource = self.get_object()
        for field, value in payload.validated_data.items():
            setattr(resource, field, value)
        resource.save(update_fields=list(payload.validated_data) or None)

        from realtime.broadcast import broadcast
        broadcast("resource.update", ResourceSerializer(resource).data)
        return Response(ResourceSerializer(resource).data)


class ShelterListView(generics.ListAPIView):
    """GET /api/shelters?status=

    IN:  status = "OPEN" | "FULL" | "INACCESSIBLE"   optional
    OUT: 200 [ShelterSerializer, ...]   each row carries `remaining`
    """
    serializer_class = ShelterSerializer

    def get_queryset(self):
        qs = Shelter.objects.all()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs


class NearestShelterView(APIView):
    """GET /api/shelters/nearest?lat=&lon=&n=5&people=1

    IN:  lat, lon = float   required
         n        = int     optional, default 5
         people   = int     optional, default 1 -- shelters with fewer free beds
                            than this are excluded outright
    OUT: 200 [NearestShelterSerializer, ...]  nearest-first, ranked on LIVE
             occupancy. Never compute this client-side off a stale list.
         400 when lat/lon are missing or unparseable
    """
    def get(self, request):
        p = request.query_params
        try:
            lat, lon = float(p["lat"]), float(p["lon"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("lat and lon are required floats")
        n = int(p.get("n", 5))
        people = int(p.get("people", 1))

        return Response(
            NearestShelterSerializer(nearest_shelter(lat, lon, n, people), many=True).data
        )


class ShelterDetailView(generics.RetrieveAPIView):
    """GET   /api/shelters/{code}
    PATCH /api/shelters/{code}

    PATCH IN:  {status?, occupancy_delta?}
          OUT: 200 ShelterSerializer
               400 when the delta would push occupancy out of 0..capacity
               403 non-operator

    Flipping one to INACCESSIBLE reroutes every pending evacuation on the next
    cycle -- dispatch reads shelter status through engine.choose_shelter().
    """
    queryset = Shelter.objects.all()
    serializer_class = ShelterSerializer
    lookup_field = "code"

    def get_permissions(self):
        return [IsOperator()] if self.request.method == "PATCH" else super().get_permissions()

    def patch(self, request, *args, **kwargs):
        payload = ShelterPatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        shelter = self.get_object()

        if "status" in payload.validated_data:
            shelter.status = payload.validated_data["status"]
            shelter.save(update_fields=["status"])
        if "occupancy_delta" in payload.validated_data:
            shelter = adjust_occupancy(shelter, payload.validated_data["occupancy_delta"])

        from realtime.broadcast import broadcast
        broadcast("shelter.update", ShelterSerializer(shelter).data)
        return Response(ShelterSerializer(shelter).data)


class SupplyListView(generics.ListAPIView):
    """GET /api/supply

    OUT: 200 [{id, depot, depot_code, item, quantity}, ...]
    """
    queryset = SupplyStock.objects.select_related("depot").all()
    serializer_class = SupplyStockSerializer


class SupplyPlanView(APIView):
    """GET /api/supply/plan

    IN:  --
    OUT: 200 [{depot, shelter, item, quantity, cost}, ...]
         Read-only preview. Nothing moves until POST /api/supply/commit.
    """
    def get(self, request):
        return Response(SupplyFlowSerializer(compute_supply_plan(), many=True).data)


class SupplyCommitView(APIView):
    """POST /api/supply/commit

    IN:  {flows: [{depot, shelter, item, quantity}, ...]}
    OUT: 200 {committed: int, rejected: [{depot, shelter, item, reason}, ...]}
         400 malformed flows
         403 non-operator
    """
    permission_classes = [IsOperator]

    def post(self, request):
        payload = SupplyFlowSerializer(data=request.data.get("flows", []), many=True)
        payload.is_valid(raise_exception=True)
        return Response(commit_supply_plan(payload.validated_data))
