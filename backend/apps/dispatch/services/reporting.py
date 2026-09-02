"""Read-only views of the current picture: KPIs, why-this-unit, full state."""
from django.conf import settings
from django.utils import timezone

from apps.common.geo import bbox_filter

from ..adapters import engine_incident, engine_resource, engine_zones
from ..models import Assignment
from .routing import active_zones


def compute_kpi():
    """The five numbers on the dashboard strip.

    "Critical" means severity 4 or 5. Response time is measured from when the
    citizen reported to when a unit actually arrived, so only incidents that
    have a first_response_at count towards the averages.
    """
    from apps.reports.models import Incident

    sla_minutes = settings.DISPATCH_HORIZON_MIN

    real_assignments = (Assignment.objects
                        .exclude(status=Assignment.Status.PROPOSED)
                        .select_related("incident"))

    response_minutes = []
    assigned_incident_ids = set()

    for assignment in real_assignments:
        incident = assignment.incident
        assigned_incident_ids.add(incident.pk)

        is_critical = incident.severity >= 4
        has_arrived = incident.first_response_at is not None
        if is_critical and has_arrived:
            waited = incident.first_response_at - incident.reported_at
            response_minutes.append(waited.total_seconds() / 60.0)

    if response_minutes:
        # numpy is already installed (scipy needs it), and its p90 interpolation
        # is the one these dashboard numbers were tuned against.
        import numpy as np
        mean_minutes = float(np.mean(response_minutes))
        p90_minutes = float(np.percentile(response_minutes, 90))
        met_sla = sum(1 for minutes in response_minutes if minutes <= sla_minutes)
        sla_percent = met_sla / len(response_minutes) * 100
    else:
        # None, not 0.0.
        #
        # Nothing has ARRIVED yet, which is not the same as arriving instantly.
        # Returning zero made a fresh shift show "Avg response 0.0 min" in the
        # dashboard's good-news green, i.e. a perfect score for having done
        # nothing. The frontend already renders null as "--".
        mean_minutes = None
        p90_minutes = None
        sla_percent = None

    waiting = (Incident.objects
               .filter(status=Incident.Status.OPEN)
               .exclude(pk__in=assigned_incident_ids))

    # Counted as SCENES, not as reports.
    #
    # Five neighbours calling in one embankment breach is one thing waiting for
    # a boat, not five. The strip said "Waiting 18" while the dispatch page
    # showed ten cards, and the two disagreed because they were counting
    # different objects. Group the same way the solver and the cards do:
    # one cell_id, one kind, one job.
    def scenes(queryset):
        return len({(row.cell_id, row.kind) for row in queryset})

    def maybe(value):
        return None if value is None else round(value, 2)

    return {
        "crit_mean": maybe(mean_minutes),
        "crit_p90": maybe(p90_minutes),
        "crit_sla_pct": maybe(sla_percent),
        "unreached": scenes(waiting.filter(severity__gte=4)),
        "awaiting": scenes(waiting),
    }


def explain(assignment):
    """Recompute the four priority terms behind one dispatch, and list what else
    could have gone instead. Turns the black box into a decision anyone can check.

    IT MUST EXPLAIN THE DECISION THAT WAS ACTUALLY MADE. Two things would
    otherwise quietly make this panel lie:

      * The solver reasons about a SCENE, not a report. Sakhigopal is one job of
        42 people; the primary report on its own says 8. Explaining the report
        would show a priority the optimiser never used, and an operator checking
        our working would find numbers that do not add up.
      * The solver decides on ROAD minutes. Explaining with the straight-line
        estimate would print a different ETA from the one on the card.
    """
    from ..engine import (AGE_SATURATION_MIN, CORROB_SATURATION, PEOPLE_SATURATION,
                         W_AGE, W_CORROB, W_PEOPLE, W_SEVERITY, is_capable)
    from ..adapters import engine_job
    from .assign import road_eta_fn
    from .clustering import cluster_incidents
    from apps.resources.models import Resource

    # Use the row we were handed, rather than re-reading it by pk.
    #
    # A PROPOSED assignment is never written to the database -- build_plan()
    # returns unsaved rows -- so it has pk=None, and re-fetching threw
    # DoesNotExist. That made "Why this unit?" fail on exactly the assignments
    # it exists to justify: the ones the operator has not committed yet.
    # Both callers already hand over incident and resource populated.
    incident = assignment.incident
    chosen_unit = assignment.resource

    blocked_zones = engine_zones(active_zones())
    sla_minutes = settings.DISPATCH_HORIZON_MIN
    now_timestamp = timezone.now().timestamp()

    # Rebuild the scene this report belongs to, exactly as build_plan saw it.
    from apps.reports.models import Incident as IncidentModel
    scene_rows = list(IncidentModel.objects.filter(
        cell_id=incident.cell_id, kind=incident.kind,
    ).exclude(status=IncidentModel.Status.RESOLVED))
    if incident.pk is not None and not any(r.pk == incident.pk for r in scene_rows):
        scene_rows.append(incident)
    jobs = cluster_incidents(scene_rows or [incident])
    job = jobs[0] if jobs else None

    if job is not None:
        solver_incident = engine_job(job)
        people, severity, corroborations = job.people, job.severity, job.corroborations
        reported_at = job.reported_at
        target_lat, target_lon = job.lat, job.lon
    else:
        solver_incident = engine_incident(incident)
        people, severity = incident.people, incident.severity
        corroborations, reported_at = incident.corroborations, incident.reported_at
        target_lat, target_lon = incident.lat, incident.lon

    priority = solver_incident.priority(now_timestamp)
    eta_fn = road_eta_fn(blocked_zones)

    # The four things that add up to the priority. Each is scaled 0..1 first,
    # then weighted, so the four weights always sum to the priority.
    age_minutes = max(now_timestamp - reported_at.timestamp(), 0.0)
    terms = {
        "severity": W_SEVERITY * ((severity - 1) / 4.0),
        "people": W_PEOPLE * min(people / PEOPLE_SATURATION, 1.0),
        "age": W_AGE * min(age_minutes / AGE_SATURATION_MIN, 1.0),
        "corroboration": W_CORROB * min(
            (corroborations - 1) / (CORROB_SATURATION - 1), 1.0),
    }

    chosen_eta = eta_fn(engine_resource(chosen_unit), target_lat, target_lon)

    # Every other idle unit, and why it did not go.
    alternatives = []
    other_units = Resource.objects.filter(status=Resource.Status.IDLE).exclude(pk=chosen_unit.pk)

    for unit in other_units:
        engine_unit = engine_resource(unit)

        if not is_capable(engine_unit, solver_incident):
            eta = float("inf")
            reason = "insufficient capabilities"
        else:
            eta = eta_fn(engine_unit, target_lat, target_lon)
            reason = "route blocked" if eta == float("inf") else "lower gain"

        reachable = eta != float("inf")
        alternatives.append({
            "resource_code": unit.code,
            "eta_min": round(eta, 2) if reachable else None,
            "gain": round(priority * (sla_minutes - eta), 2) if reachable else None,
            "reason": reason,
        })

    return {
        "w": round(priority, 4),
        "eta_min": round(chosen_eta, 2),
        "gain": round(priority * (sla_minutes - chosen_eta), 2),
        "terms": {name: round(value, 4) for name, value in terms.items()},
        "alternatives": alternatives,
        # What the solver was actually looking at, so the panel can say
        # "3 reports, 42 people" instead of quoting one caller's line.
        "scene": {
            "reports": len(job.members) if job else 1,
            "people": people,
            "severity": severity,
            "corroborations": corroborations,
        },
    }


def build_state(bbox=None):
    """The full dashboard snapshot, for page load and for WebSocket reconnect."""
    from apps.alerts.models import Alert
    from apps.alerts.serializers import AlertSerializer
    from apps.reports.models import Incident
    from apps.reports.serializers import IncidentSerializer
    from apps.resources.models import Resource, Shelter
    from apps.resources.serializers import ResourceSerializer, ShelterSerializer
    from ..serializers import AssignmentSerializer, ZoneSerializer

    def within(qs):
        return bbox_filter(qs, bbox, "lat", "lon") if bbox else qs

    assignments = (Assignment.objects
                   .exclude(status__in=[Assignment.Status.COMPLETE, Assignment.Status.PROPOSED])
                   .select_related("incident", "resource", "shelter"))

    return {
        "t": timezone.now().isoformat(),
        "incidents": IncidentSerializer(
            within(Incident.objects.exclude(status=Incident.Status.RESOLVED)), many=True).data,
        "resources": ResourceSerializer(within(Resource.objects.all()), many=True).data,
        # Every shelter and hospital, not just the usable ones.
        #
        # This filtered on status=OPEN, which hid exactly the row the scenario
        # exists to show: the cyclone shelter stranded behind the severity-5
        # flood zone. The operator could not see why the village next to it was
        # being evacuated somewhere further away, and the frontend's
        # INACCESSIBLE colour was unreachable code. Routing still refuses a
        # closed destination -- that filter lives in build_plan, where it belongs.
        "shelters": ShelterSerializer(within(Shelter.objects.all()), many=True).data,
        "zones": ZoneSerializer(active_zones(), many=True).data,
        "assignments": AssignmentSerializer(assignments, many=True).data,
        "alerts": AlertSerializer(within(Alert.objects.filter(active=True)), many=True).data,
        "kpi": compute_kpi(),
    }
