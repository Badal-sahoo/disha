"""S5 -- the dispatch orchestrator. The only thing in this project that decides
anything. Everything else moves data around.

Debounced, synchronous, and deliberately NOT a Celery task: the solve takes
under a millisecond, so a queue would add latency and a whole failure mode for
nothing.

IMPORT MAP (blueprint 01): dispatch imports reports, resources and accounts, and
calls realtime.broadcast(). Nothing imports dispatch except the views above it
and alerts (which sits higher). engine.py imports NOTHING from Django -- that is
what keeps the allocator unit-testable with no database.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.codes import next_code
from common.geo import bbox_filter
from realtime.broadcast import broadcast, notify_unit

from .models import Assignment, Zone

_last_run_at = None   # module-level debounce timestamp
_zone_cache = None    # module-level zone cache


def run_cycle(trigger):
    """Execute one full dispatch cycle: release due units, fetch open incidents,
    build an assignment plan, commit it, and broadcast updated KPIs.

    Args:
        trigger: "report" | "unit_freed" | "zone" | "alert" | "manual"

    Returns:
        dict with keys: made (int), skipped (bool), reason (str)
    """
    global _last_run_at
    now = timezone.now()

    if _last_run_at and (now - _last_run_at).total_seconds() < settings.DISPATCH_MIN_INTERVAL_SEC:
        return {"made": 0, "skipped": True, "reason": "debounced"}
    _last_run_at = now

    from resources.services import release_due
    release_due(now)

    incidents, units = open_set(now)

    if not incidents:
        return {"made": 0, "skipped": False, "reason": "no_open_incidents"}
    if not units:
        return {"made": 0, "skipped": False, "reason": "no_units"}

    policy = "OPTIMIZED"
    assignments = build_plan(incidents, units, policy)
    result = commit_plan(assignments)

    kpi = compute_kpi(policy)
    broadcast("kpi.update", kpi)

    return {"made": result["committed"], "skipped": False, "reason": ""}


def open_incidents():
    """Return all incidents with status OPEN."""
    from reports.models import Incident
    return Incident.objects.filter(status=Incident.Status.OPEN)


def open_set(now):
    """Fetch both open incidents and available units for the dispatch solver.

    Returns:
        (incidents, units) where incidents is a list of Incident and units is
        a list of Resource (IDLE and free).
    """
    from resources.services import available_units
    incidents = list(open_incidents())
    units = list(available_units(now))
    return (incidents, units)


def build_plan(incidents, units, policy="OPTIMIZED"):
    """Convert ORM rows to engine dataclasses, run the solver, and build
    unsaved Assignment rows with status PROPOSED.

    Args:
        incidents: list of reports.models.Incident
        units: list of resources.models.Resource
        policy: "OPTIMIZED" | "GREEDY" | "GREEDY_SEVERITY"

    Returns:
        list of dispatch.models.Assignment (unsaved, status PROPOSED)
    """
    from dispatch.engine import (
        Incident as EngineIncident,
        Resource as EngineResource,
        Shelter as EngineShelter,
        BlockedZone as EngineBlockedZone,
        optimize,
        greedy_nearest,
        choose_shelter,
    )
    from resources.models import Shelter

    engine_incidents = []
    inc_lookup = {}
    for inc in incidents:
        engine_incidents.append(EngineIncident(
            id=str(inc.pk),
            lat=inc.lat,
            lon=inc.lon,
            kind=inc.kind,
            severity=inc.severity,
            people_affected=inc.people,
            reported_at=inc.reported_at.timestamp(),
            corroborations=inc.corroborations,
            needs_evacuation=True,
        ))
        inc_lookup[str(inc.pk)] = inc

    engine_resources = []
    unit_lookup = {}
    for res in units:
        engine_resources.append(EngineResource(
            id=str(res.pk),
            lat=res.lat,
            lon=res.lon,
            kind=res.kind,
            capabilities=set(res.capabilities or []),
            capacity=res.capacity,
            speed_kmph=res.speed_kmph or 35.0,
            status=res.status,
            free_at=res.free_at.timestamp() if res.free_at else 0.0,
        ))
        unit_lookup[str(res.pk)] = res

    zones = active_zones()
    blocked = [
        EngineBlockedZone(lat=z.lat, lon=z.lon, radius_km=z.radius_km, severity=z.severity)
        for z in zones
    ]

    now_ts = timezone.now().timestamp()
    if policy == "OPTIMIZED":
        raw_assignments = optimize(engine_incidents, engine_resources, now_ts, blocked)
    elif policy == "GREEDY_SEVERITY":
        raw_assignments = greedy_nearest(engine_incidents, engine_resources, now_ts, blocked, severity_first=True)
    else:
        raw_assignments = greedy_nearest(engine_incidents, engine_resources, now_ts, blocked, severity_first=False)

    orm_shelters = list(Shelter.objects.filter(status=Shelter.Status.OPEN))
    engine_shelters = [
        EngineShelter(id=str(s.pk), lat=s.lat, lon=s.lon,
                      capacity=s.capacity, occupancy=s.occupancy, status=s.status)
        for s in orm_shelters
    ]
    shelter_lookup = {str(s.pk): s for s in orm_shelters}

    dispatch_assignments = []
    for a in raw_assignments:
        inc = inc_lookup.get(a.incident_id)
        res = unit_lookup.get(a.resource_id)
        if inc is None or res is None:
            continue

        shelter_orm = None
        if inc.people > 0:
            chosen = choose_shelter(inc.lat, inc.lon, inc.people, engine_shelters, blocked)
            if chosen:
                shelter_orm = shelter_lookup.get(chosen.id)

        da = Assignment(
            code=next_code("ASG", Assignment),
            incident=inc,
            resource=res,
            shelter=shelter_orm,
            eta_min=a.eta_min,
            gain=a.gain,
            policy=policy,
            status=Assignment.Status.PROPOSED,
        )
        dispatch_assignments.append(da)

    return dispatch_assignments


def commit_plan(assignments):
    """Commit a dispatch plan: save rows, reserve shelters, mark units busy,
    and flip incidents to ASSIGNED, all in one transaction.

    Args:
        assignments: list of unsaved dispatch.models.Assignment

    Returns:
        dict with keys: committed (int), rejected (list of {code, reason})
    """
    from resources.models import Resource
    from reports.models import Incident
    from resources.services import reserve_shelter
    from .serializers import AssignmentSerializer

    if not assignments:
        return {"committed": 0, "rejected": []}

    now = timezone.now()
    committed = 0
    rejected = []
    committed_assignments = []
    incidents_to_assign = []
    shelters_touched = []

    with transaction.atomic():
        unit_pks = [a.resource_id for a in assignments]
        locked_resources = {
            str(r.pk): r for r in
            Resource.objects.select_for_update().filter(pk__in=unit_pks)
        }

        for a in assignments:
            resource = locked_resources.get(str(a.resource_id))
            if resource is None or resource.status != Resource.Status.IDLE:
                rejected.append({"code": a.code, "reason": "unit_taken"})
                continue

            inc = a.incident
            if inc.status != Incident.Status.OPEN:
                rejected.append({"code": a.code, "reason": "incident_closed"})
                continue

            if a.shelter is not None:
                if not reserve_shelter(a.shelter, inc.people):
                    rejected.append({"code": a.code, "reason": "shelter_full"})
                    continue
                shelters_touched.append(a.shelter)

            a.status = Assignment.Status.DISPATCHED
            a.dispatched_at = now
            a.save()

            inc.status = Incident.Status.ASSIGNED
            inc.save(update_fields=["status"])
            incidents_to_assign.append(inc)

            eta_td = timedelta(minutes=a.eta_min)
            until = now + eta_td
            dest_lat = a.shelter.lat if a.shelter else inc.lat
            dest_lon = a.shelter.lon if a.shelter else inc.lon
            resource.status = Resource.Status.ENROUTE
            resource.free_at = until
            resource.lat = dest_lat
            resource.lon = dest_lon
            resource.save(update_fields=["status", "free_at", "lat", "lon"])

            committed += 1
            committed_assignments.append(a)

    for a in committed_assignments:
        data = AssignmentSerializer(a).data
        broadcast("assignment.new", data)
        notify_unit(a.resource.code, "assignment.new", data)

    for inc in incidents_to_assign:
        broadcast("incident.update", {"id": inc.pk, "status": "ASSIGNED"})

    from resources.serializers import ShelterSerializer
    for s in shelters_touched:
        broadcast("shelter.update", ShelterSerializer(s).data)

    return {"committed": committed, "rejected": rejected}


def active_zones():
    """Return active zones, cached in a module-level variable."""
    global _zone_cache
    if _zone_cache is not None:
        return _zone_cache
    _zone_cache = list(Zone.objects.filter(active=True))
    return _zone_cache


def invalidate_zone_cache():
    """Clear the active_zones cache."""
    global _zone_cache
    _zone_cache = None


def compute_kpi(policy="OPTIMIZED"):
    """Compute the five dashboard KPI numbers for a given policy.

    Returns:
        dict with keys: crit_mean, crit_p90, crit_sla_pct, unreached, awaiting
    """
    import numpy as np
    from reports.models import Incident

    horizon_min = getattr(settings, "DISPATCH_HORIZON_MIN", 120)

    assignments = Assignment.objects.filter(
        policy=policy,
    ).exclude(status=Assignment.Status.PROPOSED).select_related("incident")

    response_times = []
    assigned_incident_pks = set()
    for a in assignments:
        inc = a.incident
        assigned_incident_pks.add(inc.pk)
        if inc.severity >= 4 and inc.first_response_at is not None:
            minutes = (inc.first_response_at - inc.reported_at).total_seconds() / 60.0
            response_times.append(minutes)

    if response_times:
        crit_mean = float(np.mean(response_times))
        crit_p90 = float(np.percentile(response_times, 90))
        crit_sla_pct = float(sum(1 for t in response_times if t <= horizon_min) / len(response_times) * 100)
    else:
        crit_mean = 0.0
        crit_p90 = 0.0
        crit_sla_pct = 0.0

    unreached = Incident.objects.filter(
        status=Incident.Status.OPEN,
        severity__gte=4,
    ).exclude(pk__in=assigned_incident_pks).count()

    awaiting = Incident.objects.filter(
        status=Incident.Status.OPEN,
    ).exclude(pk__in=assigned_incident_pks).count()

    return {
        "crit_mean": round(crit_mean, 2),
        "crit_p90": round(crit_p90, 2),
        "crit_sla_pct": round(crit_sla_pct, 2),
        "unreached": unreached,
        "awaiting": awaiting,
    }


def explain(assignment):
    """Recompute the four priority terms behind one dispatch and list alternatives.

    Returns:
        dict with keys: w, eta_min, gain, terms, alternatives
    """
    from django.conf import settings as dj_settings
    from dispatch.engine import (
        W_SEVERITY, W_PEOPLE, W_AGE, W_CORROB,
        PEOPLE_SATURATION, AGE_SATURATION_MIN, CORROB_SATURATION,
        travel_minutes,
        Incident as EngineIncident,
        Resource as EngineResource,
        BlockedZone as EngineBlockedZone,
        is_capable,
    )
    from resources.models import Resource

    a = Assignment.objects.select_related("incident", "resource").get(pk=assignment.pk)
    inc = a.incident
    res = a.resource

    zones = active_zones()
    blocked = [
        EngineBlockedZone(lat=z.lat, lon=z.lon, radius_km=z.radius_km, severity=z.severity)
        for z in zones
    ]

    now_ts = timezone.now().timestamp()
    reported_at_ts = inc.reported_at.timestamp()
    engine_inc = EngineIncident(
        id=str(inc.pk),
        lat=inc.lat,
        lon=inc.lon,
        kind=inc.kind,
        severity=inc.severity,
        people_affected=inc.people,
        reported_at=reported_at_ts,
        corroborations=inc.corroborations,
        needs_evacuation=True,
    )
    w = engine_inc.priority(now_ts)

    sev = (inc.severity - 1) / 4.0
    ppl = min(inc.people / PEOPLE_SATURATION, 1.0)
    age = min(max(now_ts - reported_at_ts, 0.0) / AGE_SATURATION_MIN, 1.0)
    cor = min((inc.corroborations - 1) / (CORROB_SATURATION - 1), 1.0) if CORROB_SATURATION > 1 else 0.0

    terms = {
        "severity": W_SEVERITY * sev,
        "people": W_PEOPLE * ppl,
        "age": W_AGE * age,
        "corroboration": W_CORROB * cor,
    }

    eta_min = travel_minutes(
        EngineResource(
            id=str(res.pk), lat=res.lat, lon=res.lon, kind=res.kind,
            capabilities=set(res.capabilities or []), capacity=res.capacity,
            speed_kmph=res.speed_kmph or 35.0, status=res.status,
            free_at=res.free_at.timestamp() if res.free_at else 0.0,
        ),
        inc.lat, inc.lon, blocked
    )
    gain = w * (dj_settings.DISPATCH_HORIZON_MIN - eta_min)

    alternatives = []
    idle_units = Resource.objects.filter(status=Resource.Status.IDLE)
    for u in idle_units:
        if u.pk == res.pk:
            continue
        engine_u = EngineResource(
            id=str(u.pk), lat=u.lat, lon=u.lon, kind=u.kind,
            capabilities=set(u.capabilities or []), capacity=u.capacity,
            speed_kmph=u.speed_kmph or 35.0, status=u.status,
            free_at=u.free_at.timestamp() if u.free_at else 0.0,
        )
        if not is_capable(engine_u, engine_inc):
            reason = "insufficient capabilities"
        else:
            alt_eta = travel_minutes(engine_u, inc.lat, inc.lon, blocked)
            if alt_eta == float("inf"):
                reason = "route blocked"
            else:
                alt_gain = w * (dj_settings.DISPATCH_HORIZON_MIN - alt_eta)
                alternatives.append({
                    "resource_code": u.code,
                    "eta_min": round(alt_eta, 2),
                    "gain": round(alt_gain, 2),
                    "reason": "lower gain",
                })
                continue
        alternatives.append({
            "resource_code": u.code,
            "eta_min": None,
            "gain": None,
            "reason": reason,
        })

    return {
        "w": round(w, 4),
        "eta_min": round(eta_min, 2),
        "gain": round(gain, 2),
        "terms": {k: round(v, 4) for k, v in terms.items()},
        "alternatives": alternatives,
    }


def apply_status(assignment, new_status, note="", rescued=None):
    """Walk an assignment through its lifecycle with all side effects.

    Args:
        assignment: dispatch.models.Assignment
        new_status: ACCEPTED|EN_ROUTE|ON_SCENE|TRANSPORTING|COMPLETE
        note: optional note string
        rescued: int or None, only meaningful with COMPLETE

    Returns:
        dict with keys: ok (bool), next (str or None)

    Raises:
        ValueError on illegal status transitions.
    """
    from resources.models import Resource
    from reports.models import Incident
    from .serializers import AssignmentSerializer
    from resources.serializers import ResourceSerializer

    VALID_TRANSITIONS = {
        Assignment.Status.DISPATCHED:  [Assignment.Status.ACCEPTED],
        Assignment.Status.ACCEPTED:    [Assignment.Status.EN_ROUTE],
        Assignment.Status.EN_ROUTE:    [Assignment.Status.ON_SCENE],
        Assignment.Status.ON_SCENE:    [Assignment.Status.TRANSPORTING, Assignment.Status.COMPLETE],
        Assignment.Status.TRANSPORTING: [Assignment.Status.COMPLETE],
    }

    allowed = VALID_TRANSITIONS.get(assignment.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Illegal status transition: {assignment.status} -> {new_status}. "
            f"Allowed: {allowed}"
        )

    now = timezone.now()

    with transaction.atomic():
        assignment.status = new_status

        if new_status == Assignment.Status.ACCEPTED:
            pass

        elif new_status == Assignment.Status.EN_ROUTE:
            Resource.objects.filter(pk=assignment.resource_id).update(
                status=Resource.Status.ENROUTE
            )

        elif new_status == Assignment.Status.ON_SCENE:
            assignment.arrived_at = now
            Resource.objects.filter(pk=assignment.resource_id).update(
                status=Resource.Status.ONSCENE
            )
            from reports.services import mark_first_response
            mark_first_response(assignment.incident, now)

        elif new_status == Assignment.Status.TRANSPORTING:
            Resource.objects.filter(pk=assignment.resource_id).update(
                status=Resource.Status.TRANSPORTING
            )

        elif new_status == Assignment.Status.COMPLETE:
            assignment.completed_at = now
            if rescued is not None:
                assignment.rescued_count = rescued
            Incident.objects.filter(pk=assignment.incident_id).update(
                status=Incident.Status.RESOLVED
            )
            Resource.objects.filter(pk=assignment.resource_id).update(
                status=Resource.Status.IDLE,
                free_at=now,
            )

        assignment.save(update_fields=["status", "arrived_at", "completed_at",
                                       "rescued_count"])

    next_map = {
        Assignment.Status.DISPATCHED: Assignment.Status.ACCEPTED,
        Assignment.Status.ACCEPTED: Assignment.Status.EN_ROUTE,
        Assignment.Status.EN_ROUTE: Assignment.Status.ON_SCENE,
        Assignment.Status.ON_SCENE: Assignment.Status.TRANSPORTING,
        Assignment.Status.TRANSPORTING: Assignment.Status.COMPLETE,
        Assignment.Status.COMPLETE: None,
    }
    next_status = next_map.get(new_status)

    ts_iso = now.isoformat()
    broadcast("assignment.update", {
        "id": assignment.pk, "code": assignment.code,
        "status": new_status, "ts": ts_iso,
    })
    notify_unit(assignment.resource.code, "assignment.update", {
        "id": assignment.pk, "code": assignment.code,
        "status": new_status, "ts": ts_iso,
    })

    res = Resource.objects.get(pk=assignment.resource_id)
    broadcast("resource.update", ResourceSerializer(res).data)

    if new_status == Assignment.Status.COMPLETE:
        broadcast("incident.update", {
            "id": assignment.incident_id, "status": "RESOLVED"
        })
        run_cycle("unit_freed")

    return {"ok": True, "next": next_status}


def update_unit_location(resource, lat, lon, ts=None):
    """Update a unit's GPS position from the 20-second beacon ping."""
    ts = ts or timezone.now()

    resource.lat = lat
    resource.lon = lon
    resource.save(update_fields=["lat", "lon"])

    broadcast("resource.update", {
        "id": resource.pk,
        "lat": lat,
        "lon": lon,
        "status": resource.status,
        "free_at": resource.free_at.isoformat() if resource.free_at else None,
    })


def route_polyline(from_lat, from_lon, to_lat, to_lon, vclass="TRUCK"):
    """Return a flood-aware route polyline and travel time.

    Returns:
        dict with keys: polyline (list of [lat, lon]), minutes (float)
    """
    from dispatch.engine import Resource as EngineResource, travel_minutes

    polyline = [[from_lat, from_lon], [to_lat, to_lon]]

    speed_map = {"TRUCK": 35.0, "BOAT": 15.0, "TEAM": 5.0, "AMBULANCE": 40.0}
    speed = speed_map.get(vclass, 35.0)

    dummy_res = EngineResource(
        id="route",
        lat=from_lat,
        lon=from_lon,
        kind=vclass,
        capabilities=set(),
        capacity=10,
        speed_kmph=speed,
        status="IDLE",
        free_at=0.0,
    )

    zones = active_zones()
    from dispatch.engine import BlockedZone as EngineBlockedZone
    blocked = [
        EngineBlockedZone(lat=z.lat, lon=z.lon, radius_km=z.radius_km, severity=z.severity)
        for z in zones
    ]

    minutes = travel_minutes(dummy_res, to_lat, to_lon, blocked)

    return {"polyline": polyline, "minutes": round(minutes, 2)}


def build_state(bbox=None):
    """Build the full dashboard snapshot for page load or WebSocket reconnect.

    Returns:
        dict with keys: t, incidents, resources, shelters, zones, assignments,
        alerts, kpi
    """
    from alerts.models import Alert
    from alerts.serializers import AlertSerializer as AlertSer
    from reports.models import Incident
    from reports.serializers import IncidentSerializer
    from resources.models import Resource, Shelter
    from resources.serializers import ResourceSerializer, ShelterSerializer
    from .serializers import AssignmentSerializer, ZoneSerializer

    incidents_qs = Incident.objects.exclude(status=Incident.Status.RESOLVED)
    if bbox:
        incidents_qs = bbox_filter(incidents_qs, bbox, "lat", "lon")

    resources_qs = Resource.objects.all()
    if bbox:
        resources_qs = bbox_filter(resources_qs, bbox, "lat", "lon")

    shelters_qs = Shelter.objects.filter(status=Shelter.Status.OPEN)
    if bbox:
        shelters_qs = bbox_filter(shelters_qs, bbox, "lat", "lon")

    zones_qs = active_zones()

    assignments_qs = Assignment.objects.exclude(
        status__in=[Assignment.Status.COMPLETE, Assignment.Status.PROPOSED]
    ).select_related("incident", "resource", "shelter")

    alerts_qs = Alert.objects.filter(active=True)
    if bbox:
        alerts_qs = bbox_filter(alerts_qs, bbox, "lat", "lon")

    kpi = compute_kpi("OPTIMIZED")

    return {
        "t": timezone.now().isoformat(),
        "incidents": IncidentSerializer(incidents_qs, many=True).data,
        "resources": ResourceSerializer(resources_qs, many=True).data,
        "shelters": ShelterSerializer(shelters_qs, many=True).data,
        "zones": ZoneSerializer(zones_qs, many=True).data,
        "assignments": AssignmentSerializer(assignments_qs, many=True).data,
        "alerts": AlertSer(alerts_qs, many=True).data,
        "kpi": kpi,
    }


def timeline_events(start, end):
    """Return every state-changing event in order for the timeline view.

    Returns:
        list of dicts with keys: t, type, data
    """
    from reports.models import Incident
    from reports.serializers import IncidentSerializer
    from .serializers import AssignmentSerializer

    events = []

    incidents = Incident.objects.filter(reported_at__gte=start, reported_at__lte=end)
    for inc in incidents:
        events.append({
            "t": inc.reported_at,
            "type": "incident.new",
            "data": IncidentSerializer(inc).data,
        })
        if inc.first_response_at is not None:
            events.append({
                "t": inc.first_response_at,
                "type": "incident.update",
                "data": {"id": inc.pk, "first_response_at": inc.first_response_at.isoformat()},
            })

    assignments = Assignment.objects.filter(
        Q(dispatched_at__gte=start, dispatched_at__lte=end) |
        Q(arrived_at__gte=start, arrived_at__lte=end) |
        Q(completed_at__gte=start, completed_at__lte=end)
    ).select_related("incident", "resource", "shelter")

    for a in assignments:
        if a.dispatched_at and a.dispatched_at >= start and a.dispatched_at <= end:
            events.append({
                "t": a.dispatched_at,
                "type": "assignment.new",
                "data": AssignmentSerializer(a).data,
            })
        if a.arrived_at and a.arrived_at >= start and a.arrived_at <= end:
            events.append({
                "t": a.arrived_at,
                "type": "assignment.update",
                "data": {"id": a.pk, "code": a.code, "status": "ON_SCENE"},
            })
        if a.completed_at and a.completed_at >= start and a.completed_at <= end:
            events.append({
                "t": a.completed_at,
                "type": "assignment.update",
                "data": {"id": a.pk, "code": a.code, "status": "COMPLETE"},
            })

    events.sort(key=lambda e: e["t"])
    return events


def after_action_report(start, end, fmt="csv"):
    """Generate an after-action report as CSV or PDF.

    Returns:
        (bytes, content_type, filename)
    """
    import csv
    from io import StringIO

    assignments = Assignment.objects.filter(
        dispatched_at__gte=start, dispatched_at__lte=end
    ).select_related("incident", "resource", "shelter")

    if fmt == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Assignment Code", "Incident Code", "Severity", "People",
            "Resource Code", "Resource Kind", "Shelter Code",
            "Status", "ETA (min)", "Gain", "Dispatched", "Arrived", "Completed",
            "Response Time (min)",
        ])
        for a in assignments:
            inc = a.incident
            resp_time = ""
            if a.arrived_at and inc.reported_at:
                resp_time = round((a.arrived_at - inc.reported_at).total_seconds() / 60.0, 2)
            writer.writerow([
                a.code,
                inc.code,
                inc.severity,
                inc.people,
                a.resource.code,
                a.resource.kind,
                a.shelter.code if a.shelter else "",
                a.status,
                round(a.eta_min, 2),
                round(a.gain, 4),
                a.dispatched_at.isoformat() if a.dispatched_at else "",
                a.arrived_at.isoformat() if a.arrived_at else "",
                a.completed_at.isoformat() if a.completed_at else "",
                resp_time,
            ])
        content = output.getvalue().encode("utf-8")
        content_type = "text/csv"
        filename = f"ps05-after-action-{timezone.now().strftime('%Y-%m-%d')}.csv"
        return (content, content_type, filename)

    return after_action_report(start, end, fmt="csv")
