"""resources serializers. These shapes appear inside GET /api/state as
resources[] and shelters[], and in the resource.update / shelter.update
WebSocket events."""
from rest_framework import serializers

from .models import Depot, Resource, Shelter, SupplyStock


class ResourceSerializer(serializers.ModelSerializer):
    """OUT (also GET /api/state resources[] and ws resource.update):
      {
        id:          int,
        code:        str,        # "BOAT-04"
        name:        str,
        kind:        str,        # "TEAM" | "BOAT" | "TRUCK" | "AMBULANCE"
        lat:         float,      # updated on every beacon ping
        lon:         float,
        capabilities: [str],     # ["BOAT","ROPE_RESCUE"] -- see engine.REQUIRED_CAPS
        capacity:    int,        # people it can move per trip
        speed_kmph:  float,
        status:      str,        # "IDLE"|"ENROUTE"|"ONSCENE"|"TRANSPORTING"|"OUT_OF_SERVICE"
        free_at:     str|None,   # ISO 8601 -- when it re-enters the solve
        base_name:   str,
      }
    """
    class Meta:
        model = Resource
        fields = ["id", "code", "name", "kind", "lat", "lon", "capabilities",
                  "capacity", "speed_kmph", "status", "free_at", "base_name"]
        read_only_fields = ["id", "code"]


class ResourcePatchSerializer(serializers.Serializer):
    """PATCH /api/resources/{code} -- the operator override.

    IN (every field optional; send only what changed):
      status:   str    "IDLE"|"ENROUTE"|"ONSCENE"|"TRANSPORTING"|"OUT_OF_SERVICE"
      lat:      float
      lon:      float
      capacity: int    >= 0

    A boat with a dead engine goes OUT_OF_SERVICE and leaves the next solve
    immediately -- resources.services.available_units() filters on status.
    """
    status = serializers.ChoiceField(choices=Resource.Status.choices, required=False)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)
    capacity = serializers.IntegerField(min_value=0, required=False)


class ShelterSerializer(serializers.ModelSerializer):
    """OUT (also GET /api/state shelters[] and ws shelter.update):
      {
        id:        int,
        code:      str,      # "SHL-11"
        name:      str,
        lat:       float,
        lon:       float,
        capacity:  int,
        occupancy: int,
        remaining: int,      # @property, never a column -- a stored copy drifts
        status:    str,      # "OPEN" | "FULL" | "INACCESSIBLE"
      }
    """
    remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Shelter
        fields = ["id", "code", "name", "lat", "lon", "capacity", "occupancy",
                  "remaining", "status"]
        read_only_fields = ["id", "code", "remaining"]


class NearestShelterSerializer(ShelterSerializer):
    """GET /api/shelters/nearest row -- ShelterSerializer plus distance.

    OUT: {...ShelterSerializer, km: float, eta_min: float}
      km      = straight-line kilometres from the query point
      eta_min = travel minutes; road-aware once USE_ROAD_GRAPH is on, otherwise
                km * engine.ROAD_FACTOR / speed
    """
    km = serializers.FloatField(read_only=True)
    eta_min = serializers.FloatField(read_only=True)

    class Meta(ShelterSerializer.Meta):
        fields = ShelterSerializer.Meta.fields + ["km", "eta_min"]


class ShelterPatchSerializer(serializers.Serializer):
    """PATCH /api/shelters/{code}

    IN (both optional):
      status:           str   "OPEN" | "FULL" | "INACCESSIBLE"
      occupancy_delta:  int   signed. +12 when a walk-in group arrives,
                              -12 when they leave. NOT an absolute occupancy --
                              a delta so two concurrent edits both land.
    """
    status = serializers.ChoiceField(choices=Shelter.Status.choices, required=False)
    occupancy_delta = serializers.IntegerField(required=False)


class DepotSerializer(serializers.ModelSerializer):
    """OUT: {id, code, name, lat, lon}"""
    class Meta:
        model = Depot
        fields = ["id", "code", "name", "lat", "lon"]


class SupplyStockSerializer(serializers.ModelSerializer):
    """GET /api/supply row.

    OUT: {
      id:         int,
      depot:      int,     # Depot PK
      depot_code: str,     # "DEP-02"
      item:       str,     # "KIT" | "WATER" | "FOOD" | "MEDICAL"
      quantity:   int,
    }
    """
    depot_code = serializers.CharField(source="depot.code", read_only=True)

    class Meta:
        model = SupplyStock
        fields = ["id", "depot", "depot_code", "item", "quantity"]


class SupplyFlowSerializer(serializers.Serializer):
    """One arrow on the map: GET /api/supply/plan out, POST /api/supply/commit in.

    {
      depot:      str,     # depot code   "DEP-02"
      shelter:    str,     # shelter code "SHL-11"
      item:       str,     # "KIT" | "WATER" | "FOOD" | "MEDICAL"
      quantity:   int,     # units to move -- drives arrow width on the map
      cost:       float,   # km * quantity, the min-cost-flow objective term
    }
    """
    depot = serializers.CharField()
    shelter = serializers.CharField()
    item = serializers.ChoiceField(choices=SupplyStock.Item.choices)
    quantity = serializers.IntegerField(min_value=1)
    cost = serializers.FloatField(required=False)
