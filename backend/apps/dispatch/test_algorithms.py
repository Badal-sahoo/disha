#!/usr/bin/env python
"""End-to-end checks for the four dispatch behaviours that matter on stage.

engine.test_engine.py covers the optimiser in isolation, with no database. This
file covers what the optimiser does once it is wired to real rows, real roads
and the seeded district -- which is where all four of the bugs below actually
lived. Run the seed first:

    python manage.py seed_demo --reset --scenario
    python apps/dispatch/test_algorithms.py

What each check is guarding, and what it caught:

  1 CLUBBING     Five neighbours reporting one embankment breach were solved as
                 five independent jobs and got FIVE separate boats. The engine's
                 anti-dogpile decay could not fire, because every duplicate
                 arrived as a fresh incident at slot 0.
  2 ROADS        The solver chose units on haversine * 1.35 while the dashboard
                 drew the routed path. The two disagreed by up to 16 minutes, so
                 the number the operator read was not the number the decision
                 was made on.
  3 SEQUENCING   A 1:1 assignment problem cannot give one unit two jobs, so
                 leftover scenes got nobody -- not even a boat finishing two
                 kilometres away.
  4 HOSPITALS    Ambulances took casualties to cyclone shelters, because a
                 shelter and a hospital were the same kind of row.
"""
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
django.setup()

from django.utils import timezone  # noqa: E402

from apps.dispatch.services.assign import build_plan, open_set, road_eta_fn  # noqa: E402
from apps.dispatch.services.clustering import cluster_incidents  # noqa: E402
from apps.dispatch.services.routing import active_zones, road_network  # noqa: E402
from apps.dispatch.adapters import engine_resource, engine_zones  # noqa: E402
from apps.resources.models import Shelter  # noqa: E402

fails = 0


def ok(name, condition, detail=""):
    global fails
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + ("" if condition else f"  -- {detail}"))
    if not condition:
        fails += 1


def plan_now():
    incidents, units = open_set(timezone.now())
    if not incidents or not units:
        # The commonest way to run this file is straight after a probe that
        # already committed everything, which leaves nothing open and produces a
        # wall of confusing failures. Say what to do instead.
        sys.exit("nothing to plan (%d open incidents, %d idle units) -- run\n"
                 "    python manage.py seed_demo --reset --scenario\n"
                 "first; these checks need an unserved district."
                 % (len(incidents), len(units)))
    return incidents, units, build_plan(incidents, units)


# ---------------------------------------------------------------------------
# 1. Clubbing: one scene is one job, however many people phoned it in.
# ---------------------------------------------------------------------------
def test_clustering():
    incidents, units, plan = plan_now()
    jobs = cluster_incidents(incidents)

    # Group the way a JOB groups: cell AND kind. A flood and a landslide at the
    # same crossroads share a cell but are two different emergencies needing
    # different capabilities -- clustering.py keeps them apart on purpose.
    reports_per_scene = Counter((i.cell_id, i.kind) for i in incidents)
    multi = {c: n for c, n in reports_per_scene.items() if n > 1}
    ok("scenario actually contains a multi-report scene", bool(multi), reports_per_scene)

    ok("clustering collapses reports into fewer jobs",
       len(jobs) < len(incidents), f"{len(jobs)} jobs from {len(incidents)} reports")

    # The seeded Sakhigopal breach: 5 callers, 42 people, one embankment.
    biggest = max(jobs, key=lambda j: len(j.members))
    ok("the biggest job carries every one of its reports",
       len(biggest.members) == max(reports_per_scene.values()),
       f"{len(biggest.members)} members vs {max(reports_per_scene.values())} reports")
    ok("a clustered job sums its people",
       biggest.people == sum(m.people for m in biggest.members),
       biggest.people)
    ok("a clustered job takes the WORST severity",
       biggest.severity == max(m.severity for m in biggest.members))
    ok("a clustered job takes the OLDEST report time",
       biggest.reported_at == min(m.reported_at for m in biggest.members))

    # The point of all of it: units per scene must now be bounded by need, not
    # by how many people happened to own a phone.
    # Per SCENE, not per cell: Konark carries both a flood and a cyclone, and
    # counting the cell adds two different emergencies together.
    units_per_scene = Counter()
    for a in plan:
        if (a.leg or 0) == 0:      # leg 1 is a follow-up, not a second unit here
            units_per_scene[(a.incident.cell_id, a.incident.kind)] += 1

    job_by_key = {(j.primary.cell_id, j.kind): j for j in jobs}
    worst = None
    for key, count in units_per_scene.items():
        job = job_by_key.get(key)
        if job is None:
            continue
        need = min(math.ceil(job.people / 12.0), 4)
        if worst is None or count - need > worst[0]:
            worst = (count - need, key, count, need, job.people)
    ok("no scene is given more units than it needs",
       worst is not None and worst[0] <= 0,
       worst and f"{worst[1]} got {worst[2]} units for {worst[4]} people (need {worst[3]})")

    biggest_key = (biggest.primary.cell_id, biggest.kind)
    ok("the five-caller breach no longer draws five separate boats",
       units_per_scene[biggest_key] < len(biggest.members),
       f"{units_per_scene[biggest_key]} units vs {len(biggest.members)} reports")


# ---------------------------------------------------------------------------
# 2. Shortest path: the solver decides on the same minutes the map draws.
# ---------------------------------------------------------------------------
def test_road_etas():
    network = road_network()
    ok("road graph is loaded", network is not None)
    if network is None:
        return

    incidents, units, plan = plan_now()
    blocked = engine_zones(active_zones())
    eta = road_eta_fn(blocked)

    # A unit is routed to the SCENE, which is the centroid of every report in
    # the cluster -- not to the primary report's own pin. They differ by a few
    # hundred metres, so comparing against the pin is wrong by design.
    scene = {j.primary.pk: (j.lat, j.lon) for j in cluster_incidents(incidents)}

    worst = 0.0
    worst_row = None
    for a in plan:
        if (a.leg or 0) != 0:
            continue           # a follow-up leg is cumulative, not a single hop
        unit = engine_resource(a.resource)
        unit.lat, unit.lon = a.origin_lat, a.origin_lon
        target = scene.get(a.incident.pk, (a.incident.lat, a.incident.lon))
        expected = eta(unit, *target)
        gap = abs(expected - a.eta_min)
        if gap > worst:
            worst, worst_row = gap, (a.code, a.resource.code, a.eta_min, expected)

    ok("stored ETA equals the routed ETA the solver decided on",
       worst < 0.01, f"worst gap {worst:.2f} min on {worst_row}")

    # And it must genuinely be road distance, not the straight line in disguise.
    from apps.dispatch.engine import travel_minutes
    differs = 0
    for a in plan:
        if (a.leg or 0) != 0:
            continue
        unit = engine_resource(a.resource)
        unit.lat, unit.lon = a.origin_lat, a.origin_lon
        straight = travel_minutes(unit, *scene.get(a.incident.pk,
                                                    (a.incident.lat, a.incident.lon)), blocked)
        if abs(straight - a.eta_min) > 1.0:
            differs += 1
    ok("routed ETAs are not just the straight-line estimate",
       differs > 0, "every ETA matched haversine -- is the graph really being used?")


# ---------------------------------------------------------------------------
# 3. Sequencing: a unit with two stops has an order and a cumulative ETA.
# ---------------------------------------------------------------------------
def test_sequencing():
    incidents, units = open_set(timezone.now())

    # The seeded district has more units than scenes, so nothing would ever be
    # left over to chain. Starve it: hand the planner a handful of units and
    # make it decide what each one does AFTER its first job. This is the state a
    # real cyclone night is in, and the one the follow-up pass exists for.
    #
    # They have to be units that can actually serve what is left. units[:3] sorts
    # to three ambulances, which carry only MEDICAL and are correctly refused
    # every flood in the district -- a scarcity test that proves nothing.
    scarce = [u for u in units if "BOAT" in (u.capabilities or [])][:3]
    ok("scarcity test has capable units", len(scarce) == 3,
       [(u.code, u.capabilities) for u in scarce])
    plan = build_plan(incidents, scarce)
    ok("scarce plan serves more scenes than it has units",
       len(plan) > len(scarce), f"{len(plan)} assignments from {len(scarce)} units")

    by_unit = defaultdict(list)
    for a in plan:
        by_unit[a.resource.code].append(a)

    chained = {u: legs for u, legs in by_unit.items() if len(legs) > 1}
    ok("at least one unit is given a second stop", bool(chained),
       "no follow-up legs were produced -- are there fewer scenes than units?")

    for unit_code, legs in chained.items():
        legs.sort(key=lambda a: a.leg)
        ok(f"{unit_code} legs are numbered 0,1,...",
           [a.leg for a in legs] == list(range(len(legs))), [a.leg for a in legs])
        ok(f"{unit_code} second stop arrives AFTER the first",
           legs[1].eta_min > legs[0].eta_min,
           f"leg0 {legs[0].eta_min:.1f} vs leg1 {legs[1].eta_min:.1f}")

        from apps.dispatch.engine import ON_SCENE_MIN
        ok(f"{unit_code} second ETA includes working time at the first scene",
           legs[1].eta_min >= legs[0].eta_min + ON_SCENE_MIN,
           f"gap {legs[1].eta_min - legs[0].eta_min:.1f} min < {ON_SCENE_MIN}")

    ok("no unit is given more than two stops in one plan",
       all(len(v) <= 2 for v in by_unit.values()),
       {u: len(v) for u, v in by_unit.items() if len(v) > 2})


# ---------------------------------------------------------------------------
# 4. Hospitals: an ambulance takes a casualty somewhere with a doctor in it.
# ---------------------------------------------------------------------------
def test_hospital_routing():
    hospitals = Shelter.objects.filter(kind=Shelter.Kind.HOSPITAL)
    ok("the district has hospitals seeded", hospitals.exists(), hospitals.count())

    incidents, units, plan = plan_now()
    ambulances = [a for a in plan if a.resource.kind == "AMBULANCE" and a.shelter]
    ok("the plan uses at least one ambulance", bool(ambulances))

    for a in ambulances:
        ok(f"{a.resource.code} destination is a hospital",
           a.shelter.kind == Shelter.Kind.HOSPITAL,
           f"went to {a.shelter.name} ({a.shelter.kind})")

    others = [a for a in plan if a.resource.kind != "AMBULANCE" and a.shelter]
    for a in others:
        ok(f"{a.resource.code} (not an ambulance) goes to a shelter",
           a.shelter.kind == Shelter.Kind.SHELTER,
           f"went to {a.shelter.name} ({a.shelter.kind})")

    # Nearest, not merely correct in kind.
    from apps.dispatch.engine import haversine_km
    for a in ambulances[:3]:
        reachable = [h for h in hospitals if h.remaining >= a.incident.people]
        if not reachable:
            continue
        nearest = min(reachable,
                      key=lambda h: haversine_km(a.incident.lat, a.incident.lon, h.lat, h.lon))
        chosen_km = haversine_km(a.incident.lat, a.incident.lon, a.shelter.lat, a.shelter.lon)
        nearest_km = haversine_km(a.incident.lat, a.incident.lon, nearest.lat, nearest.lon)
        ok(f"{a.resource.code} picked the nearest hospital with room",
           abs(chosen_km - nearest_km) < 0.01,
           f"chose {a.shelter.name} at {chosen_km:.1f} km, "
           f"nearest was {nearest.name} at {nearest_km:.1f} km")


# ---------------------------------------------------------------------------
# 5. Lifecycle: a scene closes when the LAST unit finishes, not the first.
# ---------------------------------------------------------------------------
def test_lifecycle():
    from apps.dispatch.models import Assignment
    from apps.dispatch.services.assign import commit_plan
    from apps.dispatch.services.progress import apply_status
    from apps.reports.models import Incident
    from apps.resources.models import Resource
    from apps.resources.services import release_due

    # Commit deliberately. run_cycle() no longer dispatches by itself --
    # settings.AUTO_DISPATCH defaults to False so an operator presses the button
    # -- and a lifecycle test needs assignments on the board to walk.
    incidents, units = open_set(timezone.now())
    commit_plan(build_plan(incidents, units))

    # Find a SCENE (cell AND kind) that actually took more than one unit. Cell
    # alone is not a scene: Konark holds a flood and a cyclone at once.
    multi = None
    seen = {(a.incident.cell_id, a.incident.kind) for a in Assignment.objects.select_related("incident")}
    for cell, kind in seen:
        rows = list(Assignment.objects.filter(incident__cell_id=cell, incident__kind=kind))
        if len(rows) > 1:
            multi = (cell, kind, rows)
            break
    ok("a scene was given more than one unit", multi is not None)
    if multi is None:
        return
    cell, kind, units_on_scene = multi

    def statuses():
        return [i.status for i in Incident.objects.filter(cell_id=cell, kind=kind)]

    first = units_on_scene[0]
    for step in ("ACCEPTED", "EN_ROUTE", "ON_SCENE", "COMPLETE"):
        apply_status(first, step)

    ok("one unit finishing does NOT close a scene others are still working",
       "RESOLVED" not in statuses(), statuses())

    # A crew that has taken control must be safe from the release timer.
    second = (Assignment.objects.filter(incident__cell_id=cell, incident__kind=kind)
              .exclude(status=Assignment.Status.COMPLETE).first())
    for step in ("ACCEPTED", "EN_ROUTE", "ON_SCENE"):
        apply_status(second, step)
    unit = Resource.objects.get(pk=second.resource_id)
    Resource.objects.filter(pk=unit.pk).update(free_at=timezone.now())
    release_due(timezone.now())
    unit.refresh_from_db()
    ok("the release timer never pulls a unit off an active rescue",
       unit.status == "ONSCENE", f"unit went {unit.status}")

    # Now finish every remaining unit -- the scene must close completely.
    for assignment in (Assignment.objects.filter(incident__cell_id=cell, incident__kind=kind)
                       .exclude(status=Assignment.Status.COMPLETE)):
        walk = {"DISPATCHED": ["ACCEPTED", "EN_ROUTE", "ON_SCENE", "COMPLETE"],
                "ACCEPTED": ["EN_ROUTE", "ON_SCENE", "COMPLETE"],
                "EN_ROUTE": ["ON_SCENE", "COMPLETE"],
                "ON_SCENE": ["COMPLETE"]}.get(assignment.status, [])
        for step in walk:
            apply_status(assignment, step)

    final = statuses()
    ok("when the last unit finishes, EVERY report in the scene closes",
       all(s == "RESOLVED" for s in final), final)


if __name__ == "__main__":
    for test in (test_clustering, test_road_etas, test_sequencing, test_hospital_routing,
                 test_lifecycle):
        print(f"\n--- {test.__name__} ---")
        test()
    print("\n" + ("all good" if not fails else f"{fails} FAILED"))
    sys.exit(1 if fails else 0)
