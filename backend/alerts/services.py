"""S6 -- CAP alerts. Warnings from the government in, notifications to citizens out.

IMPORT RULE: alerts sits ABOVE dispatch and resources -- it may import both.
Nothing imports alerts except its own views (and dispatch.build_state, which
imports alerts.models lazily, inside the function).
"""


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
    raise NotImplementedError("alerts.services.poll_feed -- Track 4 - Day 3")


def parse_cap(xml):
    """CAP is a fixed published standard, so this is ElementTree and six named
    fields. It is not scraping.

    IN:  xml = str                      # one <alert> document
    OUT: {
           identifier: str,
           event:      str,             # "Cyclone Warning"
           severity:   str,             # Minor | Moderate | Severe | Extreme
           urgency:    str,             # Immediate | Expected | Future | Past | Unknown
           certainty:  str,             # Observed | Likely | Possible | Unlikely
           sent_at:    datetime,
           expires_at: datetime | None,
           polygon:    [[lat, lon], ...],
           raw_xml:    str,
         }

    NAMESPACE: CAP 1.2 is urn:oasis:names:tc:emergency:cap:1.2 -- every findall
    needs the prefix or you get empty results and no error.

    POLYGON: CAP writes "lat,lon lat,lon lat,lon" space-separated, LAT FIRST.
    Keep that order internally. Flip to [lon, lat] only when you emit GeoJSON.

    RAISES: ValueError on a document with no <identifier> -> HTTP 400.
    """
    raise NotImplementedError("alerts.services.parse_cap -- Track 4 - Day 3")


def area_to_geojson(area):
    """CAP gives either a <polygon> or a <geocode>. Handle both.

    IN:  area = dict            # the <area> block from parse_cap
    OUT: {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
         GeoJSON order -- lon first. This function IS the boundary where the
         flip happens; nowhere else in the project does it.

    The geocode path needs a district-boundary lookup table. Ship the polygon
    path first -- IMD cyclone warnings carry polygons.
    """
    raise NotImplementedError("alerts.services.area_to_geojson -- Track 4 - Day 3")


def point_in_polygon(lat, lon, polygon):
    """Ray casting. About twelve lines, no geo library.

    IN:  lat, lon = float
         polygon  = [[lat, lon], ...]   # lat first, matching Alert.polygon
    OUT: bool

    Count how many times a ray from the point crosses an edge; odd = inside.
    Watch the wrap-around edge (last vertex back to first) -- forgetting it is
    the classic bug and it only shows up for points near one side.
    """
    raise NotImplementedError("alerts.services.point_in_polygon -- Track 4 - Day 3")


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
    raise NotImplementedError("alerts.services.devices_in -- Track 4 - Day 3")


def numbers_in(polygon):
    """Phone numbers to SMS inside a polygon -- people who already reported from
    there, plus any IVR callers.

    IN:  polygon = [[lat, lon], ...]
    OUT: [str, ...]              # distinct, non-empty

    DB:  SELECT DISTINCT reporter_phone FROM reports_incident
           WHERE reporter_phone <> '' AND <bbox>       -- then the polygon test
         alerts may import reports (it sits above it in the map).
    """
    raise NotImplementedError("alerts.services.numbers_in -- Track 4 - Day 3")


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
    raise NotImplementedError("alerts.services.preposition -- Track 4 - Day 5")


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
    raise NotImplementedError("alerts.services.send_push -- Track 4 - Day 6")


def send_sms_bulk(numbers, text):
    """Outbound SMS through the handset gateway.

    IN:  numbers = [str, ...]
         text    = str            # truncate to 160 chars
    OUT: {queued: int, task_id: str|None}

    RATE-LIMIT HARD. You are on a consumer SIM and it WILL be throttled -- or
    the carrier will treat a burst as spam and cut the number off mid-demo.
    """
    raise NotImplementedError("alerts.services.send_sms_bulk -- Track 4 - Day 6")
