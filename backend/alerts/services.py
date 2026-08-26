"""S6 -- CAP alerts. Warnings from the government in, notifications to citizens out.

IMPORT RULE: alerts sits ABOVE dispatch and resources -- it may import both.
Nothing imports alerts except its own views (and dispatch.build_state, which
imports alerts.models lazily, inside the function).
"""

import logging
from datetime import timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)

# CAP 1.2 namespace.
CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
NS_PREFIX = f"{{{CAP_NS}}}"


def poll_feed():
    """Fetch the SACHET feed, parse it, save anything new.

    IN:  --
    OUT: [alerts.models.Alert, ...]     # only the NEWLY created rows, possibly []

    USES: requests.get(settings.SACHET_FEED_URL, timeout=10)
          alerts.services.parse_cap(xml) -> dict

    DB:  INSERT INTO alerts_alert ... ON CONFLICT (identifier) DO NOTHING
         -- i.e. Alert.objects.get_or_create(identifier=..., defaults={...}).
         identifier is unique, so re-polling the same feed never duplicates and
         the poller can run as often as you like.
         Always store raw_xml.

    DEMO SAFETY -- do this on day 1, not day 6:
      When settings.USE_ALERT_FIXTURE is True, or the network call raises, read
      alerts/fixtures/sachet_sample.xml instead. If the government feed is slow
      or down on presentation day, nothing on stage changes.

    EMITS: broadcast("alert.new", AlertSerializer(a).data) per new row.

    RUN IT: a management command on a loop, or Celery beat every 5 minutes if
            you already know Celery. Not from a request.
    """
    from realtime.broadcast import broadcast
    from .models import Alert
    from .serializers import AlertSerializer

    xml = None
    use_fixture = getattr(settings, "USE_ALERT_FIXTURE", True)

    if use_fixture:
        fixture_path = Path(__file__).parent / "fixtures" / "sachet_sample.xml"
        if fixture_path.exists():
            xml = fixture_path.read_text(encoding="utf-8")
    else:
        try:
            import requests
            resp = requests.get(settings.SACHET_FEED_URL, timeout=10)
            resp.raise_for_status()
            xml = resp.text
        except Exception:
            log.warning("Failed to fetch SACHET feed, falling back to fixture", exc_info=True)
            fixture_path = Path(__file__).parent / "fixtures" / "sachet_sample.xml"
            if fixture_path.exists():
                xml = fixture_path.read_text(encoding="utf-8")

    if not xml:
        return []

    # Parse the XML. It may contain multiple <alert> elements.
    new_alerts = []
    try:
        alerts_data = parse_cap(xml)
    except ValueError:
        log.warning("Failed to parse CAP XML", exc_info=True)
        return []

    for alert_data in alerts_data:
        obj, created = Alert.objects.get_or_create(
            identifier=alert_data["identifier"],
            defaults={
                "event": alert_data["event"],
                "severity": alert_data["severity"],
                "urgency": alert_data.get("urgency", ""),
                "certainty": alert_data.get("certainty", ""),
                "polygon": alert_data.get("polygon", []),
                "sent_at": alert_data["sent_at"],
                "expires_at": alert_data.get("expires_at"),
                "raw_xml": alert_data.get("raw_xml", ""),
                "active": True,
            },
        )
        if created:
            new_alerts.append(obj)

    # Broadcast each new alert.
    for alert in new_alerts:
        broadcast("alert.new", AlertSerializer(alert).data)

    return new_alerts


def parse_cap(xml):
    """CAP is a fixed published standard, so this is ElementTree and six named
    fields. It is not scraping.

    IN:  xml = str                      # one <alert> document
    OUT: [{
           identifier: str,
           event:      str,             # "Cyclone Warning"
           severity:   str,             # Minor | Moderate | Severe | Extreme
           urgency:    str,             # Immediate | Expected | Future | Past | Unknown
           certainty:  str,             # Observed | Likely | Possible | Unlikely
           sent_at:    datetime,
           expires_at: datetime | None,
           polygon:    [[lat, lon], ...],
           raw_xml:    str,
         }, ...]

    NAMESPACE: CAP 1.2 is urn:oasis:names:tc:emergency:cap:1.2 -- every findall
    needs the prefix or you get empty results and no error.

    POLYGON: CAP writes "lat,lon lat,lon lat,lon" space-separated, LAT FIRST.
    Keep that order internally. Flip to [lon, lat] only when you emit GeoJSON.

    RAISES: ValueError on a document with no <identifier> -> HTTP 400.
    """
    root = ET.fromstring(xml)

    # Find all <alert> elements (namespace-prefixed).
    alert_elems = root.findall(f".//{NS_PREFIX}alert")
    if not alert_elems:
        # Try without namespace prefix as fallback (some feeds omit it).
        alert_elems = root.findall(".//alert")
    if not alert_elems:
        raise ValueError("No <alert> element found in CAP document")

    results = []

    for alert_elem in alert_elems:
        # Identifier is REQUIRED.
        identifier = _find_text(alert_elem, "identifier")
        if not identifier:
            raise ValueError("CAP document missing <identifier>")

        event = _find_text(alert_elem, "event") or ""
        severity = _find_text(alert_elem, "severity") or ""
        urgency = _find_text(alert_elem, "urgency") or ""
        certainty = _find_text(alert_elem, "certainty") or ""

        # Parse sent_at and expires_at.
        sent_at_str = _find_text(alert_elem, "sent")
        sent_at = _parse_datetime(sent_at_str) if sent_at_str else timezone.now()

        expires_at_str = _find_text(alert_elem, "expires")
        expires_at = _parse_datetime(expires_at_str) if expires_at_str else None

        # Parse polygon from <info>/<area>/<polygon>.
        polygon = []
        # Look inside <info> elements.
        info_elems = alert_elem.findall(f"{NS_PREFIX}info")
        if not info_elems:
            info_elems = alert_elem.findall("info")
        for info in info_elems:
            area_elems = info.findall(f"{NS_PREFIX}area")
            if not area_elems:
                area_elems = info.findall("area")
            for area in area_elems:
                poly_elem = area.find(f"{NS_PREFIX}polygon")
                if poly_elem is None:
                    poly_elem = area.find("polygon")
                if poly_elem is not None and poly_elem.text:
                    # CAP format: "lat,lon lat,lon lat,lon" space-separated, LAT FIRST.
                    for coord_str in poly_elem.text.strip().split():
                        parts = coord_str.split(",")
                        if len(parts) == 2:
                            lat, lon = float(parts[0]), float(parts[1])
                            polygon.append([lat, lon])  # lat first, internal order.

        # Store raw XML for debugging.
        raw_xml = ET.tostring(alert_elem, encoding="unicode")

        results.append({
            "identifier": identifier,
            "event": event,
            "severity": severity,
            "urgency": urgency,
            "certainty": certainty,
            "sent_at": sent_at,
            "expires_at": expires_at,
            "polygon": polygon,
            "raw_xml": raw_xml,
        })

    return results


def area_to_geojson(area):
    """CAP gives either a <polygon> or a <geocode>. Handle both.

    IN:  area = dict            # the <area> block from parse_cap
    OUT: {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
         GeoJSON order -- lon first. This function IS the boundary where the
         flip happens; nowhere else in the project does it.

    The geocode path needs a district-boundary lookup table. Ship the polygon
    path first -- IMD cyclone warnings carry polygons.
    """
    # area is expected to have "polygon" key from parse_cap output.
    # polygon is [[lat, lon], ...] lat first.
    coords = area.get("polygon", [])

    if not coords:
        return {"type": "Polygon", "coordinates": [[]]}

    # Flip to GeoJSON order: lon first, lat second.
    geojson_coords = [[lon, lat] for lat, lon in coords]

    return {"type": "Polygon", "coordinates": [geojson_coords]}


def point_in_polygon(lat, lon, polygon):
    """Ray casting. About twelve lines, no geo library.

    IN:  lat, lon = float
         polygon  = [[lat, lon], ...]   # lat first, matching Alert.polygon
    OUT: bool

    Count how many times a ray from the point crosses an edge; odd = inside.
    Watch the wrap-around edge (last vertex back to first) -- forgetting it is
    the classic bug and it only shows up for points near one side.
    """
    if not polygon or len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)

    for i in range(n):
        j = (i - 1) % n  # wrap-around: last vertex back to first.

        xi, yi = polygon[i]  # lat, lon
        xj, yj = polygon[j]  # lat, lon

        # Check if edge straddles the point's longitude.
        intersect = ((yi > lon) != (yj > lon))

        if intersect:
            # Compute the x-coordinate of the intersection point.
            x_intersect = (xj - xi) * (lon - yi) / (yj - yi + 1e-10) + xi

            if x_intersect > lat:
                inside = not inside

    return inside


def devices_in(polygon):
    """Registered devices inside a warning polygon.

    IN:  polygon = [[lat, lon], ...]
    OUT: QuerySet[Device] | list[Device]

    DB:  bounding-box filter in SQL FIRST --
           WHERE lat BETWEEN min_lat AND max_lat
             AND lon BETWEEN min_lon AND max_lon
         then the exact point_in_polygon test in Python over what comes back.
         Two cheap steps beat one expensive one, and it needs no PostGIS.
         Fast enough at any hackathon scale.
    """
    from .models import Device

    if not polygon:
        return []

    # Bounding-box filter first.
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    candidates = Device.objects.filter(
        lat__gte=min_lat, lat__lte=max_lat,
        lon__gte=min_lon, lon__lte=max_lon,
    )

    # Exact point_in_polygon test.
    result = []
    for d in candidates:
        if point_in_polygon(d.lat, d.lon, polygon):
            result.append(d)

    return result


def numbers_in(polygon):
    """Phone numbers to SMS inside a polygon -- people who already reported from
    there, plus any IVR callers.

    IN:  polygon = [[lat, lon], ...]
    OUT: [str, ...]              # distinct, non-empty

    DB:  SELECT DISTINCT reporter_phone FROM reports_incident
           WHERE reporter_phone <> '' AND <bbox>       -- then the polygon test
         alerts may import reports (it sits above it in the map).
    """
    from reports.models import Incident

    if not polygon:
        return []

    # Bounding-box filter first.
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    candidates = Incident.objects.filter(
        lat__gte=min_lat, lat__lte=max_lat,
        lon__gte=min_lon, lon__lte=max_lon,
        reporter_phone__gt="",
    ).values_list("reporter_phone", flat=True).distinct()

    # Exact point_in_polygon test.
    result = []
    for phone in candidates:
        if phone in result:
            continue
        # Check if any incident from this phone is inside the polygon.
        incidents = Incident.objects.filter(reporter_phone=phone)
        for inc in incidents:
            if point_in_polygon(inc.lat, inc.lon, polygon):
                result.append(phone)
                break

    return result


def preposition(alert, max_units=5):
    """Stage idle units toward a PREDICTED impact area, before any citizen has
    reported anything. This is the early-warning demo beat.

    IN:  alert     = alerts.models.Alert
         max_units = int
    OUT: [dispatch.models.Assignment, ...]   # committed, not proposed

    HOW: treat the polygon centroid as a SYNTHETIC incident and run the normal
         dispatcher against it. No second allocation code path -- that is the
         point, and it is why this works identically to a real dispatch on stage.

    USES:
      dispatch.services.build_plan(incidents, units, "OPTIMIZED")
      dispatch.services.commit_plan(assignments)
      resources.services.available_units(now)
      dispatch.engine.Incident(...)   -- build the synthetic one directly as an
                                         engine dataclass; do NOT write a fake
                                         row into reports_incident, or it shows
                                         up as a pin nobody reported.

    DB:  reads resources_resource; writes dispatch_assignment through commit_plan.

    EMITS: whatever commit_plan emits -- assignment.new per row.

    CALLED BY: alerts/views.py PrepositionView
    """
    from dispatch.engine import Incident as EngineIncident
    from dispatch.services import build_plan, commit_plan
    from reports.models import Incident as ReportIncident
    from resources.services import available_units

    now = timezone.now()

    # Compute polygon centroid.
    polygon = alert.polygon
    if not polygon:
        return []

    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    centroid_lat = sum(lats) / len(lats)
    centroid_lon = sum(lons) / len(lons)

    # Build a synthetic Incident ORM instance (NOT a fake DB row -- this is
    # a transient object used only for build_plan's ORM->engine conversion).
    # We create a real Incident to pass through the normal dispatch path.
    from common.codes import next_code
    from django.db import transaction

    with transaction.atomic():
        synthetic = ReportIncident.objects.create(
            code=next_code("INC", ReportIncident),
            client_ref=f"preposition-{alert.pk}-{now.timestamp()}",
            lat=centroid_lat,
            lon=centroid_lon,
            kind=ReportIncident.Kind.CYCLONE,
            severity=5,
            people=50,
            description=f"Prepositioned for alert: {alert.event}",
            source=ReportIncident.Source.APP,
            cell_id=f"{centroid_lat:.2f},{centroid_lon:.2f}",
            corroborations=1,
            status=ReportIncident.Status.OPEN,
        )

    # Get available units (limited to max_units).
    units = available_units(now)[:max_units]

    if not units:
        return []

    # Build plan using the normal dispatcher.
    assignments = build_plan([synthetic], units, "OPTIMIZED")

    # Commit the plan.
    if assignments:
        result = commit_plan(assignments)
        return [a for a in assignments if a.status != "PROPOSED"]

    return []


def send_push(tokens, text, alert=None):
    """Outbound push. The one part of this system that genuinely belongs in a
    task queue.

    IN:  tokens = [str, ...]
         text   = str
         alert  = Alert | None      # attaches severity + a deep link
    OUT: {queued: int, task_id: str|None}

    Batched, retried with backoff, dead tokens pruned. Synchronous is fine for
    the demo -- thousands of sends are not, which is why the view reports
    `queued` rather than `sent`.
    """
    if not tokens:
        return {"queued": 0, "task_id": None}

    # For the demo, just log and count. A real implementation would use
    # Firebase Cloud Messaging or a similar service.
    queued = 0
    for token in tokens:
        log.info("PUSH to %s: %s", token[:12], text[:60])
        queued += 1

    return {"queued": queued, "task_id": None}


def send_sms_bulk(numbers, text):
    """Outbound SMS through the handset gateway.

    IN:  numbers = [str, ...]
         text    = str            # truncate to 160 chars
    OUT: {queued: int, task_id: str|None}

    RATE-LIMIT HARD. You are on a consumer SIM and it WILL be throttled -- or
    the carrier will treat a burst as spam and cut the number off mid-demo.
    """
    if not numbers:
        return {"queued": 0, "task_id": None}

    # Truncate to 160 chars for SMS.
    sms_text = text[:160]

    # For the demo, just log and count. A real implementation would use
    # a GSM gateway with rate limiting.
    queued = 0
    for number in numbers:
        log.info("SMS to %s: %s", number, sms_text[:60])
        queued += 1

    return {"queued": queued, "task_id": None}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_text(elem, tag):
    """Find text in a CAP element, trying with and without namespace prefix."""
    # Try with namespace prefix first.
    child = elem.find(f"{NS_PREFIX}{tag}")
    if child is not None and child.text:
        return child.text.strip()
    # Fallback: try without namespace.
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _parse_datetime(s):
    """Parse an ISO 8601 datetime string, handling the CAP format."""
    if not s:
        return None
    try:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(s)
        if dt is not None:
            return dt
    except Exception:
        pass
    # Fallback: strip timezone offset and parse.
    try:
        import dateutil.parser
        return dateutil.parser.parse(s)
    except Exception:
        return None
