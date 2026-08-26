"""Geometry helpers shared by more than one app.

Name every coordinate `lat` and `lon`, in that order, everywhere. Convert only
at the GeoJSON boundary, where the order flips to [lon, lat]. Swapping these is
the single most common bug in this kind of project -- it puts the whole district
in the Bay of Bengal.
"""
import math


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points.

    IN:  lat1, lon1, lat2, lon2 = float   # degrees
    OUT: float                            # kilometres

    NOTE: dispatch/engine.py already ships an identical implementation.
          Import THAT one inside dispatch (`from dispatch.engine import
          haversine_km`) so the optimiser and the API can never disagree by a
          rounding step. This copy exists for apps that must not import
          dispatch -- resources, alerts.
    """
    r_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r_km * math.asin(math.sqrt(a))
def cell_for(lat, lon):
    """Grid bucket key. The entire spatial index this project needs.

    IN:  lat, lon = float                 # 19.8135, 85.8312
    OUT: str                              # "19.81,85.83"  (2dp ~ 1.1 km)

    Drives BOTH the heatmap and the corroboration count, which is why
    reports_incident.cell_id is indexed. Two decimal places, formatted with
    f"{lat:.2f},{lon:.2f}" -- always two digits, so "19.80,85.80" not
    "19.8,85.8", or string equality silently stops matching.
    """
    # Always two digits. "19.80,85.80", never "19.8,85.8" -- string equality is
    # what joins a report to its cell, and it stops matching silently otherwise.
    return f"{lat:.2f},{lon:.2f}"
def parse_bbox(raw):
    """Parse the ?bbox= query parameter used by /api/state, /api/alerts and
    /api/reports/heatmap.

    IN:  raw = str | None                 # "min_lon,min_lat,max_lon,max_lat"
                                          # e.g. "85.5,19.5,86.2,20.1"
    OUT: {min_lon: float, min_lat: float, max_lon: float, max_lat: float} | None
         None when raw is None or "" -- callers treat that as "no filter".

    RAISES: ValueError  -> the DRF handler turns this into HTTP 400
            when there are not exactly 4 comma-separated floats, or
            min >= max on either axis.

    NOTE: bbox is in GeoJSON order (lon first). This is the boundary the module
          docstring warns about -- convert here, and nowhere else.

    The "no filter" short-circuit below is implemented so that an unfiltered
    GET /api/state works the moment build_state() does -- a stub here would
    block every endpoint that merely ACCEPTS an optional bbox.
    """
    if not raw:
        return None
    parts = str(raw).split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be 'min_lon,min_lat,max_lon,max_lat'")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError:
        raise ValueError("bbox values must be four numbers")
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox min must be smaller than max on both axes")
    return {"min_lon": min_lon, "min_lat": min_lat,
            "max_lon": max_lon, "max_lat": max_lat}
def bbox_filter(queryset, bbox, lat_field="lat", lon_field="lon"):
    """Apply a parsed bbox to any queryset with lat/lon columns.

    IN:
      queryset  = QuerySet
      bbox      = the dict from parse_bbox() | None
      lat_field = str, default "lat"
      lon_field = str, default "lon"
    OUT:
      QuerySet  # unchanged when bbox is None

    DB: adds  WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s
        Plain FloatField columns -- no PostGIS. At district scale this is a
        sequential scan on a few thousand rows and it is fast enough.
    """
    if bbox is None:
        return queryset
    return queryset.filter(**{
        f"{lat_field}__gte": bbox["min_lat"], f"{lat_field}__lte": bbox["max_lat"],
        f"{lon_field}__gte": bbox["min_lon"], f"{lon_field}__lte": bbox["max_lon"],
    })