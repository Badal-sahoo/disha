"""S1 -- Ingest. Every report from every channel lands here.

Written once so the parser, the deduplication and the corroboration logic are
not reimplemented four times. The app path, the SMS path and the IVR path all
call create_incident() and nothing else.

IMPORT RULE (blueprint 01): reports must NEVER import dispatch. If a new report
should trigger a dispatch, the caller above does both steps in order -- and
reports/views.py and ingest/views.py already do exactly that.
"""
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.codes import next_code
from common.geo import cell_for as _grid_cell
from realtime.broadcast import broadcast

from .models import Incident


def create_incident(data, source):
    """The one door in.

    IN:
      data = {
        client_ref:     str,        # UUID from the phone. Dedupe key.
        lat:            float,      # 19.8135
        lon:            float,      # 85.8312
        kind:           str,        # "FLOOD" | "CYCLONE" | "LANDSLIDE"
        severity:       int,        # 1..5
        people:         int,        # >= 1
        description:    str,        # may be ""
        photo:          File|None,  # optional, <= 500 KB
        reporter_phone: str,        # may be ""
      }
      source = str                  # "APP" | "SMS" | "IVR"

    OUT:
      reports.models.Incident       # the model instance, NOT a dict.
      The view serialises it with IncidentSerializer. Returns the EXISTING row
      unchanged when client_ref was already seen -- never a second row.

    USES:
      from reports.services import find_duplicate, cell_for, count_corroborations
          find_duplicate(client_ref: str)     -> Incident | None
          cell_for(lat: float, lon: float)    -> str            # "19.81,85.83"
          count_corroborations(cell_id: str)  -> int
      from common.codes import next_code
          next_code("INC", Incident)          -> str            # "INC0142"
      from realtime.broadcast import broadcast
          broadcast(event_type: str, data: dict) -> None        # plain dicts only
      from reports.serializers import IncidentSerializer        # to build the ws payload

    DB:
      reports_incident
        1. SELECT ... WHERE client_ref = %s              -- unique+indexed; hit -> return early
        2. SELECT COUNT(DISTINCT reporter_phone)
             WHERE cell_id = %s AND reported_at >= now() - INTERVAL '60 minutes'
                                                         -- uses the cell_id index
        3. INSERT one row: code, client_ref, lat, lon, kind, severity, people,
             description, photo, source, reporter_phone, cell_id,
             corroborations=<step 2>, status="OPEN"
        4. UPDATE reports_incident SET corroborations = <step 2>
             WHERE cell_id = %s AND status = 'OPEN'      -- bump the neighbours too,
                                                            or the first report in a
                                                            cell stays stuck at 1
      Wrap 1-4 in transaction.atomic(). Catch IntegrityError on client_ref and
      re-SELECT: two SMS arriving in the same millisecond both pass step 1.

    EMITS:
      broadcast("incident.new", IncidentSerializer(inc).data)
      broadcast("incident.update", {"id": n, "corroborations": k})  # per neighbour bumped

    RAISES:
      ValueError -> the DRF handler in common/exceptions.py returns HTTP 400

    CALLED BY:
      reports/views.py  ReportListCreateView.post   source="APP"
      ingest/views.py   SmsIntakeView.post          source="SMS"
      ingest/views.py   IvrView.post                source="IVR"
      -- each of those calls dispatch.services.run_cycle() straight afterwards.
         Do NOT call it from in here.
    """
    client_ref = str(data.get("client_ref") or "").strip()
    if not client_ref:
        raise ValueError("client_ref is required")

    existing = find_duplicate(client_ref)
    if existing is not None:
        return existing          # a retried POST is a no-op, not a second pin

    severity = data.get("severity")
    if severity is None:
        severity = infer_severity(data)          # IVR and terse SMS only

    cell = cell_for(data["lat"], data["lon"])

    try:
        with transaction.atomic():
            incident = Incident.objects.create(
                code=next_code("INC", Incident),
                client_ref=client_ref,
                lat=data["lat"],
                lon=data["lon"],
                kind=data["kind"],
                severity=severity,
                people=data.get("people") or 1,
                description=data.get("description") or "",
                photo=data.get("photo") or None,
                source=source,
                reporter_phone=data.get("reporter_phone") or "",
                cell_id=cell,
                corroborations=1,
            )
            # Count AFTER the insert so this reporter is included, then level the
            # whole cell up -- otherwise the first report in a cell stays at 1
            # forever while later ones climb.
            count = count_corroborations(cell)
            neighbours = list(Incident.objects
                              .filter(cell_id=cell, status=Incident.Status.OPEN)
                              .exclude(pk=incident.pk)
                              .values_list("id", flat=True))
            (Incident.objects
             .filter(cell_id=cell, status=Incident.Status.OPEN)
             .update(corroborations=count))
            incident.corroborations = count
    except IntegrityError:
        # Two SMS in the same millisecond both cleared find_duplicate. The unique
        # constraint on client_ref is the real guard; re-read and hand back the winner.
        duplicate = find_duplicate(client_ref)
        if duplicate is not None:
            return duplicate
        raise

    from .serializers import IncidentSerializer          # local: avoids an import cycle
    broadcast("incident.new", IncidentSerializer(incident).data)
    for nid in neighbours:
        broadcast("incident.update", {"id": nid, "corroborations": count})

    return incident
def find_duplicate(client_ref):
    """Return the existing row so a retried POST is a no-op.

    IN:  client_ref = str       # the phone's UUID
    OUT: Incident | None

    DB:  SELECT ... FROM reports_incident WHERE client_ref = %s
         client_ref is unique + db_index -- this is a single index lookup.

    Why it exists: the mobile app's offline queue drains in FIFO order and is
    safe to call repeatedly, and the SMS gateway redelivers. Both rely on this.
    """
    if not client_ref:
        return None
    return Incident.objects.filter(client_ref=client_ref).first()
def cell_for(lat, lon):
    """The entire spatial grid, in one line.

    IN:  lat, lon = float
    OUT: str                    # f"{lat:.2f},{lon:.2f}" -> "19.81,85.83"
                                # 2 decimal places ~ 1.1 km

    USES: common.geo.cell_for -- delegate to it rather than duplicating the
          format string. If the two ever disagree, corroboration silently stops
          matching and nothing errors.
    """
    # Delegate. If this ever disagrees with common.geo.cell_for, corroboration
    # silently stops matching and nothing raises.
    return _grid_cell(lat, lon)
def count_corroborations(cell_id):
    """Distinct REPORTERS in a cell in the last hour -- not raw report count,
    or one person pressing send five times looks like five witnesses.

    IN:  cell_id = str          # "19.81,85.83"
    OUT: int                    # >= 1

    DB:  SELECT COUNT(DISTINCT reporter_phone) FROM reports_incident
           WHERE cell_id = %s
             AND reported_at >= now() - INTERVAL '60 minutes'
         Window length is settings.CORROBORATION_WINDOW_MIN.
         Rows with reporter_phone = '' (an APP report with no phone) each count
         as one distinct reporter -- fall back to client_ref for those, or every
         anonymous app report in a cell collapses into a single witness.

    FEEDS: engine.Incident.priority() weights corroboration at 0.10, saturating
           at 5 independent reports (engine.CORROB_SATURATION).
    """
    window_min = getattr(settings, "CORROBORATION_WINDOW_MIN", 60)
    since = timezone.now() - timedelta(minutes=window_min)

    rows = (Incident.objects
            .filter(cell_id=cell_id, reported_at__gte=since)
            .values_list("reporter_phone", "client_ref"))

    # Distinct REPORTERS, not rows -- one person pressing send five times is one
    # witness. An APP report carries no phone, so fall back to its client_ref,
    # otherwise every anonymous report in the cell collapses into a single person.
    reporters = {(phone or f"ref:{ref}") for phone, ref in rows}
    return max(len(reporters), 1)
def heatmap_cells(bbox=None):
    """One query, no Python loop.

    IN:  bbox = {min_lon, min_lat, max_lon, max_lat} | None   # from common.geo.parse_bbox

    OUT: [
           {cell_id: str, lat: float, lon: float, weight: float, count: int},
           ...
         ]
         lat/lon are the cell centre -- parse them straight back out of cell_id.
         weight = SUM(severity * corroborations) across the cell.

    DB:  Incident.objects.filter(status="OPEN")
           .values("cell_id")
           .annotate(weight=Sum(F("severity") * F("corroborations")), count=Count("id"))
         Apply common.geo.bbox_filter() BEFORE .values() when bbox is not None.

    CALLED BY: reports/views.py HeatmapView (GET /api/reports/heatmap)
    CONSUMED BY: frontend features/heatmap -- toHeatGeoJSON() turns each row into
                 one GeoJSON point with `weight` as the heat intensity property.
    """
    raise NotImplementedError("reports.services.heatmap_cells -- Track 1 - Day 2")


def mark_first_response(incident, ts):
    """Stamp the moment help actually arrived. Every benchmark number in the
    after-action report derives from this column.

    IN:  incident = Incident      # the model instance
         ts       = datetime      # timezone-aware, when the unit hit ON_SCENE
    OUT: None

    DB:  UPDATE reports_incident SET first_response_at = %s
           WHERE id = %s AND first_response_at IS NULL
         The NULL guard in the WHERE clause is the whole point -- write once,
         on the FIRST arrival. A second boat reaching the same scene must not
         overwrite it, or your response-time numbers quietly improve.

    CALLED BY: dispatch/services.py, when an assignment transitions to ON_SCENE.
    """
    # The NULL guard lives in the WHERE clause: write once, on the FIRST arrival.
    # A second boat reaching the same scene must not overwrite it, or every
    # response-time number quietly improves.
    written = (Incident.objects
               .filter(pk=incident.pk, first_response_at__isnull=True)
               .update(first_response_at=ts))
    if written:
        incident.first_response_at = ts
def infer_severity(payload):
    """Used ONLY when the channel could not carry a severity -- an IVR call
    where the caller hung up early, or a terse SMS.

    IN:  payload = {kind: str, people: int, description: str, ...}  # partial
    OUT: int                     # 1..5

    RULE: never overrides a severity the citizen actually chose. The caller
          checks `if payload.get("severity") is None` before calling this.

    Suggested shape (keyword + headcount, explainable on stage):
      base 2; +1 if people >= 10; +1 if people >= 30;
      +1 for any of "trapped/stuck/drowning/fasa/atkigala" in description;
      clamp to 1..5.

    CALLED BY: ingest/parsers.py parse_sms and ivr_next.
    """
    people = int(payload.get("people") or 1)
    text = " ".join(str(payload.get(k) or "") for k in ("description", "note", "body")).lower()

    score = 2
    if people >= 10:
        score += 1
    if people >= 30:
        score += 1

    # English, Hindi and Odia words that signal someone cannot get out themselves.
    URGENT = ("trapped", "stuck", "drowning", "injured", "roof", "collapsed",
              "fasa", "phasa", "atkigala", "atka", "dubi", "bachao", "madad")
    if any(w in text for w in URGENT):
        score += 1
    if payload.get("kind") == Incident.Kind.LANDSLIDE:
        score += 1

    return max(1, min(score, 5))