"""Geometry helpers shared by more than one app.

Name every coordinate `lat` and `lon`, in that order, everywhere. Convert only
at the GeoJSON boundary, where the order flips to [lon, lat]. Swapping these is
the most common bug in this kind of project -- it puts the whole district in the
Bay of Bengal.
"""
# The one definition lives in the engine, so the optimiser and the API can never
# disagree by a rounding step. Safe to import: engine.py touches no Django app.
from apps.dispatch.engine import haversine_km  # noqa: F401


def cell_for(lat, lon):
    """Grid bucket key, "19.81,85.83" -- the entire spatial index this needs.

    Two decimals is ~1.1 km. ALWAYS two digits: string equality is what joins a
    report to its cell, and "19.8,85.8" stops matching silently.
    """
    return f"{lat:.2f},{lon:.2f}"


# The coastal belt every report belongs on, south-west to north-east. Same five
# points the dashboard draws its risk bands from
# (frontend/src/features/map/risk.js) -- if you move one, move both.
COASTLINE = [
    (19.735, 85.720),   # toward the Chilika mouth
    (19.790, 85.830),   # Puri beach
    (19.855, 85.950),   # Balighai
    (19.888, 86.100),   # Chandrabhaga / Konark
    (19.975, 86.280),   # Astaranga, the Devi river mouth
]

# Anything outside this is not Puri district.
DISTRICT_BBOX = (19.44, 85.10, 20.22, 86.40)   # min_lat, min_lon, max_lat, max_lon


def in_district(lat, lon):
    min_lat, min_lon, max_lat, max_lon = DISTRICT_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def coastal_landing(lat, lon):
    """Put an out-of-district report onto the coast it is about.

    A phone that texts the gateway from Rourkela -- 400 km inland -- is almost
    always someone relaying a message for family on the coast, or a handset whose
    location is simply wrong. Dropping the report loses a real call. Plotting it
    at its literal coordinates is worse: it puts a pin in the wrong half of the
    state, drags the map's viewport with it, and no unit in this district can
    ever reach it.

    So it lands on the nearest point of the district's coastline instead -- the
    stretch every report in this scenario is about -- and the CALLER IS TOLD, by
    the note create_incident appends to the description. The one thing this must
    never do is quietly pretend it knew where the person was.

    IN : lat, lon = float
    OUT: (lat, lon) on the coastline, nearest to where the report came from
    """
    best, best_d2 = COASTLINE[0], None
    for i in range(len(COASTLINE) - 1):
        (alat, alon), (blat, blon) = COASTLINE[i], COASTLINE[i + 1]
        dlat, dlon = blat - alat, blon - alon
        span = dlat * dlat + dlon * dlon
        t = 0.0 if span == 0 else ((lat - alat) * dlat + (lon - alon) * dlon) / span
        t = max(0.0, min(1.0, t))
        plat, plon = alat + t * dlat, alon + t * dlon
        d2 = (lat - plat) ** 2 + (lon - plon) ** 2
        if best_d2 is None or d2 < best_d2:
            best, best_d2 = (plat, plon), d2
    return round(best[0], 5), round(best[1], 5)


def parse_bbox(raw):
    """"min_lon,min_lat,max_lon,max_lat" -> dict, or None for "no filter".

    GeoJSON order, lon first -- this is the boundary the module docstring warns
    about, and the conversion happens here and nowhere else.

    Raises ValueError (-> HTTP 400) on anything but four numbers with min < max.
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

    Plain FloatField columns, no PostGIS: at district scale this is a sequential
    scan over a few thousand rows and it is fast enough.
    """
    if bbox is None:
        return queryset
    return queryset.filter(**{
        f"{lat_field}__gte": bbox["min_lat"], f"{lat_field}__lte": bbox["max_lat"],
        f"{lon_field}__gte": bbox["min_lon"], f"{lon_field}__lte": bbox["max_lon"],
    })
