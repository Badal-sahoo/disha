"""Who goes where: run a cycle, build a plan, commit it."""
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.codes import next_code
from apps.realtime.ws import broadcast

from ..adapters import engine_job, engine_resource, engine_zones
from ..models import Assignment
from .clustering import cluster_incidents
from .routing import active_zones, road_network

log = logging.getLogger(__name__)

_last_run_at = None


def run_cycle(trigger):
    """One cycle: release due units, re-plan, and broadcast updated KPIs.

    WHETHER IT COMMITS depends on settings.AUTO_DISPATCH, which defaults to
    False. With it off this recomputes the picture and tells every dashboard,
    but sends nobody anywhere -- an operator presses Dispatch. With it on, every
    report immediately commits the best plan, which is how this used to behave
    unconditionally: the whole district was dispatched the instant it was seeded,
    so there was nothing left for a human to decide.

    trigger is "report" | "unit_freed" | "zone" | "alert" | "manual".
    Returns {made: int, skipped: bool, reason: str}.
    """
    global _last_run_at
    now = timezone.now()
    log.info("dispatch cycle (%s)", trigger)

    if _last_run_at and (now - _last_run_at).total_seconds() < settings.DISPATCH_MIN_INTERVAL_SEC:
        return {"made": 0, "skipped": True, "reason": "debounced"}
    _last_run_at = now

    from apps.resources.services import release_due
    release_due(now)

    incidents, units = open_set(now)
    if not incidents:
        return {"made": 0, "skipped": False, "reason": "no_open_incidents"}
    if not units:
        return {"made": 0, "skipped": False, "reason": "no_units"}

    from .reporting import compute_kpi   # local: reporting reads what we just wrote

    if not settings.AUTO_DISPATCH:
        # Re-plan so the dashboard's proposal is current, and refresh the strip,
        # but commit nothing. The operator decides.
        broadcast("kpi.update", compute_kpi())
        return {"made": 0, "skipped": False, "reason": "manual_dispatch"}

    result = commit_plan(build_plan(incidents, units))
    broadcast("kpi.update", compute_kpi())
    return {"made": result["committed"], "skipped": False, "reason": ""}


def open_incidents():
    from apps.reports.models import Incident
    return Incident.objects.filter(status=Incident.Status.OPEN)


def open_set(now):
    """(open incidents, available units) -- the solver's whole input."""
    from apps.resources.services import available_units
    return list(open_incidents()), list(available_units(now))


def road_eta_fn(blocked_zones):
    """An ETA function for the solver that follows real roads.

    Why this matters: the optimiser used to decide on haversine * 1.35 while the
    dashboard drew the ROUTED path, so the number an operator read was not the
    number the choice was made on. On the seeded scenario the two disagreed by up
    to 16 minutes -- enough to pick the wrong unit and then justify it with a
    figure that came from somewhere else.

    Cost is fine. RoadNetwork caches one Dijkstra per ORIGIN, so a full
    units x scenes matrix costs one solve per unit: measured at 0.7 s cold for
    25 units over a 251k-node graph, and effectively free once warm.

    Falls back to the straight-line estimate when there is no graph, or when the
    graph says a pair is unreachable -- engine.travel_minutes has its own view of
    what the cut zones block, and it is better to hand the solver a pessimistic
    number than to silently drop every pairing in a district with sparse mapping.
    """
    from ..engine import travel_minutes
    from ..roadnet import VEHICLE_CLASS, WHEELED

    network = road_network()

    def eta(res, lat, lon):
        straight = travel_minutes(res, lat, lon, blocked_zones)
        if network is None:
            return straight
        by_road = network.travel_minutes(res.lat, res.lon, lat, lon,
                                         VEHICLE_CLASS.get(res.kind, WHEELED))
        return by_road if math.isfinite(by_road) else straight

    return eta


def build_plan(incidents, units):
    """Run the solver and return UNSAVED Assignment rows with status PROPOSED.

    There is ONE policy. An earlier build carried a nearest-available baseline
    beside the optimiser as a live A/B toggle; it is gone, along with the policy
    parameter that selected it.

    Three things happen here that the raw engine does not do on its own:

      1. CLUSTERING. Reports are grouped into scenes before the solve, so five
         neighbours reporting one embankment breach ask for one job of 42 people
         (4 boats, decayed) instead of five jobs of 8 (5 boats, undecayed).
      2. ROAD ETAs. The solver decides on the same routed minutes the dashboard
         draws, not on a straight-line approximation of them.
      3. FOLLOW-UP LEGS. The assignment problem can only give a unit one job, so
         a second pass chains leftover scenes onto units that will be free.

    Codes are allocated sequentially from the current table maximum. They are
    stable for a given open set, which is what lets POST /api/dispatch/commit
    name them: it re-solves and picks the codes the operator ticked.
    """
    from ..engine import HOSPITAL, SHELTER, choose_shelter, optimize
    from ..engine import Shelter as EngineShelter
    from apps.resources.models import Shelter

    # One job per scene, not one per report. This is what re-arms the engine's
    # marginal-slot decay; see services/clustering.py for the full story.
    jobs = cluster_incidents(incidents)
    job_by_key = {job.key: job for job in jobs}
    unit_by_id = {str(unit.pk): unit for unit in units}

    engine_jobs = [engine_job(job) for job in jobs]
    engine_units = [engine_resource(unit) for unit in units]
    unit_engine_by_id = {u.id: u for u in engine_units}
    blocked_zones = engine_zones(active_zones())
    now_timestamp = timezone.now().timestamp()

    eta_fn = road_eta_fn(blocked_zones)

    solved = optimize(engine_jobs, engine_units, now_timestamp, blocked_zones, eta_fn=eta_fn)

    # Hospitals are in this table too, so the destination search can pick the
    # right KIND of building rather than just the nearest one.
    open_places = list(Shelter.objects.filter(status=Shelter.Status.OPEN))
    engine_places = [
        EngineShelter(id=str(place.pk), lat=place.lat, lon=place.lon,
                      capacity=place.capacity, occupancy=place.occupancy,
                      status=place.status, kind=place.kind)
        for place in open_places
    ]
    place_by_id = {str(place.pk): place for place in open_places}

    # Reserved as we go, so two units in the SAME plan are not both sent to the
    # last 30 beds. commit_plan re-checks against the database.
    planned_intake = {}

    def destination_for(unit, job):
        """Where this unit takes people. An ambulance goes to a hospital.

        The rule is the UNIT, not the incident: an ambulance is the vehicle that
        carries a casualty to definitive care, and a boat evacuating a village
        is not, whatever the severity says. Crisp enough to explain on stage and
        it matches what the crews actually do.
        """
        if job.people <= 0:
            return None
        want = HOSPITAL if unit.kind == "AMBULANCE" else SHELTER
        free = [
            EngineShelter(id=p.id, lat=p.lat, lon=p.lon, capacity=p.capacity,
                          occupancy=p.occupancy + planned_intake.get(p.id, 0),
                          status=p.status, kind=p.kind)
            for p in engine_places
        ]
        best = choose_shelter(job.lat, job.lon, job.people, free, blocked_zones, kind=want)
        if best is None:
            return None
        planned_intake[best.id] = planned_intake.get(best.id, 0) + job.people
        return place_by_id.get(best.id)

    # These rows are never saved, so calling next_code() once per row would hand
    # every one of them the same string. Take one number and count up from it.
    first_number = int(next_code("ASG", Assignment)[len("ASG"):])

    plan = []
    served_keys = set()
    # Where each unit ends up, and when, so a follow-up leg starts from the
    # right place at the right time rather than from where the unit is now.
    unit_after = {}

    for solution in solved:
        job = job_by_key.get(solution.incident_id)
        unit = unit_by_id.get(solution.resource_id)
        if job is None or unit is None:
            continue

        destination = destination_for(unit, job)
        served_keys.add(job.key)

        plan.append(Assignment(
            code=f"ASG{first_number + len(plan):04d}",
            # The FK points at the job's primary report -- the oldest one, which
            # is also the code the dashboard labels the group with.
            incident=job.primary,
            resource=unit,
            shelter=destination,
            # Where the unit is standing NOW. commit_plan moves it to its
            # destination, so this is the only surviving record of the start
            # of the journey -- and the only thing the map can draw a route from.
            origin_lat=unit.lat,
            origin_lon=unit.lon,
            eta_min=solution.eta_min,
            gain=solution.gain,
            leg=0,
            status=Assignment.Status.PROPOSED,
        ))

        end = destination if destination is not None else job
        unit_after[str(unit.pk)] = (end.lat, end.lon, solution.eta_min)

    # --- second pass: give the leftovers to units that will be free ----------
    plan += _chain_followups(
        jobs=[j for j in jobs if j.key not in served_keys],
        unit_after=unit_after, unit_by_id=unit_by_id,
        unit_engine_by_id=unit_engine_by_id,
        eta_fn=eta_fn, now_timestamp=now_timestamp,
        destination_for=destination_for,
        first_code=first_number + len(plan),
    )

    return plan


def _chain_followups(jobs, unit_after, unit_by_id, unit_engine_by_id, eta_fn,
                     now_timestamp, destination_for, first_code):
    """Give each still-unserved scene to the best unit that already has a run.

    The optimiser is a 1:1 assignment problem: one unit, one job, full stop.
    With more scenes than units the remainder got NOBODY -- not even a boat that
    was about to finish two kilometres away. This pass answers the question the
    optimiser structurally cannot: "you are already going out, where do you go
    after that, and in what order?"

    Deliberately greedy rather than a second global solve. It runs over what is
    left after the optimal first legs are fixed, the candidate set is small, and
    a crew needs a run they can read off a radio -- not a plan that reshuffles
    both stops every time a new report lands.
    """
    from ..engine import ON_SCENE_MIN, T_HORIZON_MIN, is_capable

    out = []
    if not jobs or not unit_after:
        return out

    busy = dict(unit_after)          # unit pk -> (lat, lon, minutes_until_free)
    for job in sorted(jobs, key=lambda j: (-j.severity, j.reported_at)):
        engine_view = engine_job(job)
        weight = engine_view.priority(now_timestamp)

        best = None
        for unit_pk, (lat, lon, busy_min) in busy.items():
            unit = unit_by_id[unit_pk]
            engine_unit = unit_engine_by_id[unit_pk]
            if not is_capable(engine_unit, engine_view):
                continue

            # Measure the second leg from where the unit ENDS the first one.
            hop = engine_unit.__class__(
                id=engine_unit.id, lat=lat, lon=lon, kind=engine_unit.kind,
                capabilities=engine_unit.capabilities, capacity=engine_unit.capacity,
                speed_kmph=engine_unit.speed_kmph,
            )
            leg = eta_fn(hop, job.lat, job.lon)
            if not math.isfinite(leg):
                continue

            arrival = busy_min + ON_SCENE_MIN + leg
            # Same shape as the optimiser's cost, so a follow-up is only offered
            # when it would have been worth assigning in the first place.
            horizon = T_HORIZON_MIN * (1.0 + weight)
            gain = weight * (horizon - arrival)
            if gain <= 0:
                continue
            if best is None or gain > best[0]:
                best = (gain, unit_pk, arrival)

        if best is None:
            continue

        gain, unit_pk, arrival = best
        unit = unit_by_id[unit_pk]
        destination = destination_for(unit, job)

        out.append(Assignment(
            code=f"ASG{first_code + len(out):04d}",
            incident=job.primary,
            resource=unit,
            shelter=destination,
            origin_lat=unit.lat,
            origin_lon=unit.lon,
            eta_min=arrival,
            gain=gain,
            leg=1,
            status=Assignment.Status.PROPOSED,
        ))
        # One follow-up per unit per plan. A three-stop run planned off a
        # forecast is fiction; the next cycle will chain the third stop once
        # the first is actually done.
        busy.pop(unit_pk)
        if not busy:
            break

    return out


def commit_plan(assignments):
    """Save rows, reserve destinations, mark units busy and close every report
    behind each scene, all in one transaction.

    Returns {committed: int, rejected: [{code, reason}, ...]}. Anything whose
    unit was taken since the plan was built is rejected -- the human is in the
    loop, and the world moved while they were deciding.

    THREE THINGS THIS HAS TO GET RIGHT, all of which it used to get wrong once
    scenes could carry more than one unit and units more than one stop:

      * A scene needing four boats produces four rows against the SAME primary
        incident. Flipping it to ASSIGNED on the first row made the other three
        look like they were for a closed incident, so three of the four boats
        were silently rejected.
      * A unit with a follow-up leg appears twice. After leg 0 it is ENROUTE, so
        leg 1 read as "unit_taken" -- by itself.
      * Serving a scene has to close EVERY report in it. Leaving the other four
        callers OPEN meant the next cycle saw them as fresh work and sent more
        boats to a village that already had four on the way. That was the whole
        dogpile bug, re-entering through the back door.
    """
    from apps.reports.models import Incident
    from apps.resources.models import Resource
    from apps.resources.serializers import ShelterSerializer
    from apps.resources.services import reserve_shelter
    from ..serializers import AssignmentSerializer

    if not assignments:
        return {"committed": 0, "rejected": []}

    now = timezone.now()
    saved_assignments = []
    rejected = []
    assigned_incidents = []
    changed_shelters = []

    # Run each unit's legs in order, so leg 0 is committed before its follow-up.
    ordered = sorted(assignments, key=lambda a: (getattr(a, "leg", 0) or 0))

    with transaction.atomic():
        # Lock every unit in the plan up front, so two operators committing at
        # the same moment cannot both claim the same boat.
        unit_ids = [assignment.resource_id for assignment in assignments]
        locked_units = {
            unit.pk: unit
            for unit in Resource.objects.select_for_update().filter(pk__in=unit_ids)
        }

        # Snapshot BEFORE anything moves. Every later "is this still available?"
        # question is asked against the world as it was when the plan was built,
        # not against the half-applied state this loop is creating.
        was_idle = {pk: u.status == Resource.Status.IDLE for pk, u in locked_units.items()}
        claimed_units = {}      # unit pk -> minutes until it is free again
        served_incidents = {}   # incident pk -> the Incident row we already closed

        for assignment in ordered:
            unit = locked_units.get(assignment.resource_id)
            if unit is None or not was_idle.get(assignment.resource_id):
                rejected.append({"code": assignment.code, "reason": "unit_taken"})
                continue

            incident = assignment.incident
            already_ours = incident.pk in served_incidents
            if not already_ours and incident.status != Incident.Status.OPEN:
                rejected.append({"code": assignment.code, "reason": "incident_closed"})
                continue

            if assignment.shelter is not None:
                if not reserve_shelter(assignment.shelter, incident.people):
                    rejected.append({"code": assignment.code, "reason": "shelter_full"})
                    continue
                changed_shelters.append(assignment.shelter)

            assignment.status = Assignment.Status.DISPATCHED
            assignment.dispatched_at = now
            # Re-read it here rather than trusting the plan: the unit may have
            # moved between the solve and the operator pressing commit. A
            # follow-up leg keeps the origin its first leg was planned from.
            if (getattr(assignment, "leg", 0) or 0) == 0:
                assignment.origin_lat = unit.lat
                assignment.origin_lon = unit.lon
            assignment.save()

            if not already_ours:
                incident.status = Incident.Status.ASSIGNED
                incident.save(update_fields=["status"])
                assigned_incidents.append(incident)
                served_incidents[incident.pk] = incident

                # Close the rest of the scene with it. Every other report in the
                # same cell and of the same kind is the same emergency.
                siblings = list(Incident.objects.filter(
                    cell_id=incident.cell_id, kind=incident.kind,
                    status=Incident.Status.OPEN,
                ).exclude(pk=incident.pk))
                if siblings:
                    Incident.objects.filter(pk__in=[s.pk for s in siblings]).update(
                        status=Incident.Status.ASSIGNED)
                    for sibling in siblings:
                        sibling.status = Incident.Status.ASSIGNED
                        assigned_incidents.append(sibling)
                        served_incidents[sibling.pk] = sibling

            # Move the unit to where it will END UP -- the destination, not the
            # incident -- or its next job gets planned from the wrong origin.
            destination = assignment.shelter or incident
            claimed_units[unit.pk] = max(claimed_units.get(unit.pk, 0.0),
                                         assignment.eta_min or 0.0)
            unit.status = Resource.Status.ENROUTE
            unit.free_at = now + timedelta(minutes=claimed_units[unit.pk])
            unit.lat = destination.lat
            unit.lon = destination.lon
            unit.save(update_fields=["status", "free_at", "lat", "lon"])

            saved_assignments.append(assignment)

    # Broadcast after the transaction commits, never inside it.
    for assignment in saved_assignments:
        broadcast("assignment.new", AssignmentSerializer(assignment).data)
    for incident in assigned_incidents:
        broadcast("incident.update", {"id": incident.pk, "status": "ASSIGNED"})
    for shelter in changed_shelters:
        broadcast("shelter.update", ShelterSerializer(shelter).data)

    return {"committed": len(saved_assignments), "rejected": rejected}
