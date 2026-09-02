"""The one door in. Every channel -- app or SMS -- ends up here."""
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.codes import next_code
from apps.common.geo import cell_for, coastal_landing, in_district
from apps.realtime.ws import broadcast

from ..models import Incident


def create_incident(data, source):
    """The one door in. Returns the Incident model instance, not a dict.

    data carries client_ref, lat, lon, kind, severity, people, description,
    photo, reporter_phone; source is "APP" or "SMS". A client_ref that has been
    seen before returns the EXISTING row unchanged -- a retried POST is a no-op,
    which is what makes the phone's offline queue and SMS redelivery safe.

    Raises ValueError (-> HTTP 400) when client_ref is missing.
    """
    client_ref = str(data.get("client_ref") or "").strip()
    if not client_ref:
        raise ValueError("client_ref is required")

    existing = find_duplicate(client_ref)
    if existing is not None:
        return existing

    severity = data.get("severity")
    if severity is None:
        severity = infer_severity(data)

    # A report from outside the district still belongs to the district.
    #
    # SMS relayed by a relative in Rourkela, or a handset with a bad fix, used to
    # drop a pin 400 km away: off every map the operator has, unreachable by
    # every unit, and dragging the viewport with it. It now lands on the nearest
    # point of the Puri coastline -- and says so in its own description, because
    # a relocated pin that does not admit it is just a confident lie.
    lat, lon = data["lat"], data["lon"]
    description = data.get("description") or ""
    if not in_district(lat, lon):
        lat, lon = coastal_landing(lat, lon)
        note = (f"[Reported from {data['lat']:.3f}, {data['lon']:.3f} -- outside "
                f"the district. Placed on the nearest coast; confirm the location.]")
        description = f"{note} {description}".strip()

    cell = cell_for(lat, lon)

    try:
        with transaction.atomic():
            incident = Incident.objects.create(
                code=next_code("INC", Incident),
                client_ref=client_ref,
                lat=lat,
                lon=lon,
                kind=data["kind"],
                severity=severity,
                people=data.get("people") or 1,
                description=description,
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
            in_cell = Incident.objects.filter(cell_id=cell, status=Incident.Status.OPEN)
            neighbours = list(in_cell.exclude(pk=incident.pk).values_list("id", flat=True))
            in_cell.update(corroborations=count)
            incident.corroborations = count
    except IntegrityError:
        # Two messages in the same millisecond both cleared find_duplicate. The
        # unique constraint on client_ref is the real guard; hand back the winner.
        duplicate = find_duplicate(client_ref)
        if duplicate is not None:
            return duplicate
        raise

    from ..serializers import IncidentSerializer   # local: avoids an import cycle
    broadcast("incident.new", IncidentSerializer(incident).data)
    for nid in neighbours:
        broadcast("incident.update", {"id": nid, "corroborations": count})

    return incident


def find_duplicate(client_ref):
    """The existing row for this client_ref, so a retried POST is a no-op."""
    if not client_ref:
        return None
    return Incident.objects.filter(client_ref=client_ref).first()


def count_corroborations(cell_id):
    """Distinct REPORTERS in a cell within CORROBORATION_WINDOW_MIN, never raw
    report count -- one person pressing send five times is one witness, not five.

    An APP report carries no phone, so it falls back to its client_ref;
    otherwise every anonymous report in a cell collapses into a single person.
    """
    since = timezone.now() - timedelta(minutes=settings.CORROBORATION_WINDOW_MIN)
    rows = (Incident.objects
            .filter(cell_id=cell_id, reported_at__gte=since)
            .values_list("reporter_phone", "client_ref"))
    return max(len({phone or f"ref:{ref}" for phone, ref in rows}), 1)


def mark_first_response(incident, ts):
    """Stamp the moment help actually arrived. Every benchmark number derives
    from this column.

    The first_response_at__isnull guard in the WHERE clause is the whole point:
    write once, on the FIRST arrival. A second boat reaching the same scene must
    not overwrite it, or your response-time numbers quietly improve.
    """
    written = (Incident.objects
               .filter(pk=incident.pk, first_response_at__isnull=True)
               .update(first_response_at=ts))
    if written:
        incident.first_response_at = ts


# English, Hindi and Odia words that signal someone cannot get out themselves.
URGENT_WORDS = ("trapped", "stuck", "drowning", "injured", "roof", "collapsed",
                "fasa", "phasa", "atkigala", "atka", "dubi", "bachao", "madad")


def infer_severity(payload):
    """1..5, used ONLY when the channel could not carry a severity -- a terse SMS.

    Never overrides a severity the citizen actually chose; the caller checks for
    None first. Keyword plus headcount, so it is explainable on stage.
    """
    people = int(payload.get("people") or 1)
    # The message text can arrive under any of these keys depending on channel.
    parts = [str(payload.get(key) or "") for key in ("description", "note", "body")]
    text = " ".join(parts).lower()

    score = 2
    if people >= 10:
        score += 1
    if people >= 30:
        score += 1
    if any(word in text for word in URGENT_WORDS):
        score += 1
    if payload.get("kind") == Incident.Kind.LANDSLIDE:
        score += 1

    return max(1, min(score, 5))
