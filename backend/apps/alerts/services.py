"""CAP alerts: fetch the government warning feed, save it, put it on the map."""
import logging
from pathlib import Path
from xml.etree import ElementTree as ET

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

log = logging.getLogger(__name__)

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
NS_PREFIX = f"{{{CAP_NS}}}"
FIXTURE = Path(__file__).parent / "fixtures" / "sachet_sample.xml"


def poll_feed():
    """Fetch the SACHET feed, parse it, save anything new. Returns the new rows.

    identifier is unique and this uses get_or_create, so re-polling never
    duplicates and the poller can run as often as you like.

    DEMO SAFETY: with USE_ALERT_FIXTURE on -- or when the network call fails --
    it reads the bundled fixture instead, so a slow government feed on
    presentation day changes nothing on stage.

    Run it with `manage.py poll_alerts`, not from a request.
    """
    from apps.realtime.ws import broadcast
    from .models import Alert
    from .serializers import AlertSerializer

    xml = None
    if not settings.USE_ALERT_FIXTURE:
        try:
            import requests
            resp = requests.get(settings.SACHET_FEED_URL, timeout=10)
            resp.raise_for_status()
            xml = resp.text
        except Exception:
            log.warning("SACHET feed unreachable, falling back to fixture", exc_info=True)
    if xml is None and FIXTURE.exists():
        xml = FIXTURE.read_text(encoding="utf-8")
    if not xml:
        return []

    try:
        parsed = parse_cap(xml)
    except ValueError:
        log.warning("Failed to parse CAP XML", exc_info=True)
        return []

    new = []
    for data in parsed:
        obj, created = Alert.objects.get_or_create(
            identifier=data["identifier"],
            defaults={
                "event": data["event"],
                "severity": data["severity"],
                "urgency": data.get("urgency", ""),
                "certainty": data.get("certainty", ""),
                "polygon": data.get("polygon", []),
                "sent_at": data["sent_at"],
                "expires_at": data.get("expires_at"),
                "raw_xml": data.get("raw_xml", ""),
                "active": True,
            },
        )
        if created:
            new.append(obj)

    for alert in new:
        broadcast("alert.new", AlertSerializer(alert).data)
    return new


def parse_cap(xml):
    """CAP 1.2 is a fixed published standard, so this is ElementTree and six
    named fields -- it is not scraping.

    Polygons come out LAT FIRST, as CAP writes them ("lat,lon lat,lon ..."), and
    stay that way internally. They flip to [lon, lat] only at the GeoJSON edge.

    Raises ValueError on a document with no <alert>.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"malformed CAP document: {exc}") from exc

    # A single-alert document has <alert> as the root; .// only finds
    # descendants, so check the root itself before searching below it.
    if root.tag in (f"{NS_PREFIX}alert", "alert"):
        elems = [root]
    else:
        # Some feeds omit the namespace.
        elems = root.findall(f".//{NS_PREFIX}alert") or root.findall(".//alert")
    if not elems:
        raise ValueError("No <alert> element found in CAP document")
    return [_parse_alert(element) for element in elems]


# ---------------------------------------------------------------------------
# CAP parsing internals
# ---------------------------------------------------------------------------
def _parse_alert(elem):
    identifier = _find_text(elem, "identifier")
    if not identifier:
        raise ValueError("CAP <alert> without an <identifier>")

    info = _child(elem, "info")
    area = _child(info, "area") if info is not None else None

    polygon = []
    raw_polygon = _find_text(area, "polygon") if area is not None else None
    if raw_polygon:
        # CAP writes "lat,lon lat,lon ...", lat first. Keep that order internally.
        for pair in raw_polygon.split():
            corner_lat, corner_lon = pair.split(",")[:2]
            polygon.append([float(corner_lat), float(corner_lon)])

    def from_info(tag):
        """A text field off <info>, or "" when the alert has no <info> block."""
        if info is None:
            return ""
        return _find_text(info, tag) or ""

    return {
        "identifier": identifier,
        "event": from_info("event"),
        "severity": from_info("severity"),
        "urgency": from_info("urgency"),
        "certainty": from_info("certainty"),
        "sent_at": parse_datetime(_find_text(elem, "sent") or "") or timezone.now(),
        "expires_at": parse_datetime(from_info("expires")) or None,
        "polygon": polygon,
        "raw_xml": ET.tostring(elem, encoding="unicode"),
    }


def _child(elem, tag):
    """A child element, with or without the CAP namespace.

    Written as an explicit None check because an empty XML element is falsey --
    `elem.find(a) or elem.find(b)` looks right and silently skips real elements.
    """
    found = elem.find(f"{NS_PREFIX}{tag}")
    if found is None:
        found = elem.find(tag)
    return found


def _find_text(elem, tag):
    """CAP text, with and without the namespace prefix."""
    for path in (f"{NS_PREFIX}{tag}", tag):
        child = elem.find(path)
        if child is not None and child.text:
            return child.text.strip()
    return None
