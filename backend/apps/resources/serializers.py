"""resources serializers. These shapes appear inside GET /api/state as
resources[] and shelters[], and in the resource.update / shelter.update
WebSocket events."""
from rest_framework import serializers

from .models import Resource, Shelter


class ResourceSerializer(serializers.ModelSerializer):
    """lat/lon are updated on every beacon ping; free_at is when the unit
    re-enters the solve. capabilities feed engine.REQUIRED_CAPS."""
    class Meta:
        model = Resource
        fields = ["id", "code", "name", "kind", "lat", "lon", "capabilities",
                  "capacity", "speed_kmph", "status", "free_at", "base_name"]
        read_only_fields = ["id", "code"]


class ResourcePatchSerializer(serializers.Serializer):
    """PATCH /api/resources/{code} -- the operator override. Send only what
    changed. A boat with a dead engine goes OUT_OF_SERVICE and leaves the next
    solve immediately, because available_units() filters on status."""
    status = serializers.ChoiceField(choices=Resource.Status.choices, required=False)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)
    capacity = serializers.IntegerField(min_value=0, required=False)


class ShelterSerializer(serializers.ModelSerializer):
    """`remaining` is a @property, never a column -- a stored copy drifts."""
    remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Shelter
        fields = ["id", "code", "kind", "name", "lat", "lon", "capacity",
                  "occupancy", "remaining", "status"]
        read_only_fields = ["id", "code", "remaining"]


class ShelterPatchSerializer(serializers.Serializer):
    """occupancy_delta is signed and relative, NOT an absolute occupancy, so two
    concurrent walk-in edits both land."""
    status = serializers.ChoiceField(choices=Shelter.Status.choices, required=False)
    occupancy_delta = serializers.IntegerField(required=False)
