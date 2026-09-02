"""Grid cells for the heat layer."""
from django.db.models import Count, F, Sum

from apps.common.geo import bbox_filter

from ..models import Incident


def heatmap_cells(bbox=None):
    """One grouped query, no Python loop over incidents.

    OUT: [{cell_id, lat, lon, weight, count}, ...] where lat/lon are the cell
    centre and weight is SUM(severity * corroborations).

    Cells, not pins -- twenty reports of one flood must not look like twenty floods.
    """
    incidents = Incident.objects.filter(status=Incident.Status.OPEN)
    if bbox:
        incidents = bbox_filter(incidents, bbox, "lat", "lon")

    cells = (incidents.values("cell_id")
             .annotate(weight=Sum(F("severity") * F("corroborations")), count=Count("id"))
             .order_by())

    out = []
    for cell in cells:
        lat, lon = cell["cell_id"].split(",")
        out.append({"cell_id": cell["cell_id"], "lat": float(lat), "lon": float(lon),
                    "weight": float(cell["weight"] or 0), "count": cell["count"] or 0})
    return out
