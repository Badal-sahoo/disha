"""Which way a unit travels, and what is blocking it."""
import logging

from django.conf import settings

from ..adapters import engine_zones
from ..models import Zone

log = logging.getLogger(__name__)

_zone_cache = None
_road_network = None
_road_network_zones = None


def active_zones():
    """Active zones, cached in a module-level variable."""
    global _zone_cache
    if _zone_cache is None:
        _zone_cache = list(Zone.objects.filter(active=True))
    return _zone_cache


def invalidate_zone_cache():
    # ponytail: per-process cache. A second daphne worker keeps a stale copy --
    # move it to the Redis we already run if you ever scale past one process.
    global _zone_cache
    _zone_cache = None


_road_network = None
_road_network_zones = None      # which zones the loaded graph is currently weighted for


def road_network():
    """The compiled road graph, or None when we are not routing on roads.

    Loaded once and kept in memory. Reweighted only when the set of active cut
    zones has actually changed -- that rebuild is the one expensive thing at run
    time, and it must not happen on every request.
    """
    global _road_network, _road_network_zones

    if not settings.USE_ROAD_GRAPH:
        return None

    if _road_network is None:
        from ..models import RoadGraph
        from ..roadnet import RoadNetwork

        row = RoadGraph.objects.first()
        if row is None:
            # Not seeded yet. Say so once, then fall back to straight lines
            # rather than taking the whole dispatcher down.
            log.warning("USE_ROAD_GRAPH is on but no RoadGraph row exists -- "
                        "run `manage.py seed_roadgraph`. Using straight lines.")
            return None
        _road_network = RoadNetwork.from_bytes(bytes(row.data))

    zones = active_zones()
    fingerprint = tuple(sorted((z.pk, z.severity) for z in zones))
    if fingerprint != _road_network_zones:
        _road_network.apply_zones(zones)
        _road_network_zones = fingerprint

    return _road_network


def route_polyline(from_lat, from_lon, to_lat, to_lon, vclass="TRUCK"):
    """The path between two points, and how long it takes.

    With the road graph built and USE_ROAD_GRAPH on, the polyline follows real
    roads and bends around cut zones. Without it, the polyline is the direct
    segment -- but the MINUTES still account for flooding, because
    engine.travel_minutes penalises or blocks a route that clips a zone.
    """
    from ..engine import Resource as EngineResource, travel_minutes
    from ..roadnet import VEHICLE_CLASS, WHEELED

    network = road_network()
    if network is not None:
        result = network.route(from_lat, from_lon, to_lat, to_lon,
                               VEHICLE_CLASS.get(vclass, WHEELED))
        if result["polyline"]:
            return {"polyline": result["polyline"], "minutes": round(result["minutes"], 2)}
        # Every road in is cut. Fall through and report the straight-line
        # estimate, so the operator sees a number rather than an empty panel.

    speed = {"TRUCK": 35.0, "BOAT": 15.0, "TEAM": 5.0, "AMBULANCE": 40.0}.get(vclass, 35.0)
    unit = EngineResource(id="route", lat=from_lat, lon=from_lon, kind=vclass,
                          capabilities=set(), capacity=10, speed_kmph=speed,
                          status="IDLE", free_at=0.0)
    return {
        "polyline": [[from_lat, from_lon], [to_lat, to_lon]],
        "minutes": round(travel_minutes(unit, to_lat, to_lon, engine_zones(active_zones())), 2),
    }
