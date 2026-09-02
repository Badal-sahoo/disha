"""resources views. Pure-CRUD reads are generic views -- boilerplate, not logic.
Anything with a decision in it delegates to services.py.
"""
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOperator
from apps.realtime.ws import broadcast

from .models import Resource, Shelter
from .serializers import (
    ResourcePatchSerializer,
    ResourceSerializer,
    ShelterPatchSerializer,
    ShelterSerializer,
)
from .services import adjust_occupancy, nearest_shelter


def _filtered(model, params, *fields):
    qs = model.objects.all()
    for f in fields:
        if params.get(f):
            qs = qs.filter(**{f: params[f]})
    return qs


class ResourceListView(generics.ListAPIView):
    """GET /api/resources?status=&kind= -> 200 [ResourceSerializer, ...] by code."""
    serializer_class = ResourceSerializer

    def get_queryset(self):
        return _filtered(Resource, self.request.query_params, "status", "kind")


class ResourceDetailView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/resources/{code}

    PATCH takes {status?, lat?, lon?, capacity?} and needs an operator. The
    change takes effect on the NEXT dispatch cycle -- this view does not
    re-solve. Flipping a unit to OUT_OF_SERVICE removes it from
    available_units() immediately.
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

        data = ResourceSerializer(resource).data
        broadcast("resource.update", data)
        return Response(data)


class ShelterListView(generics.ListAPIView):
    """GET /api/shelters?status= -> rows carrying `remaining`."""
    serializer_class = ShelterSerializer

    def get_queryset(self):
        return _filtered(Shelter, self.request.query_params, "status")


class NearestShelterView(APIView):
    """GET /api/shelters/nearest?lat=&lon=&n=5&people=1

    Nearest-first, ranked on LIVE occupancy; shelters with fewer free beds than
    `people` are excluded outright. Never compute this client-side off a stale
    list. 400 when lat/lon are missing or unparseable.
    """
    def get(self, request):
        p = request.query_params
        try:
            lat, lon = float(p["lat"]), float(p["lon"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("lat and lon are required floats")

        shelters = nearest_shelter(lat, lon, int(p.get("n", 5)), int(p.get("people", 1)))
        return Response(ShelterSerializer(shelters, many=True).data)


class ShelterDetailView(generics.RetrieveAPIView):
    """GET / PATCH /api/shelters/{code}

    PATCH takes {status?, occupancy_delta?} and needs an operator. Flipping one
    to INACCESSIBLE reroutes every pending evacuation on the next cycle --
    dispatch reads shelter status through engine.choose_shelter().
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

        data = ShelterSerializer(shelter).data
        broadcast("shelter.update", data)
        return Response(data)
