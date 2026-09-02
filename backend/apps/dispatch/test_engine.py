#!/usr/bin/env python
"""Checks for the allocation engine. No Django, no database.

    python apps/dispatch/test_engine.py
"""
import sys
from pathlib import Path

# backend/ -- so "apps.dispatch" resolves when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.dispatch.engine import (Incident, Resource,  # noqa: E402
                                  is_capable, optimize, travel_minutes)

NOW = 1000.0


def boats(count, lat=19.80, lon=85.82):
    return [Resource(f"BOAT-{i}", lat + 0.004 * i, lon + 0.004 * i, "BOAT",
                     {"BOAT"}, 12, 18.0) for i in range(count)]


def flood(name, lat, lon, severity, people, age_min=5, corroborations=1):
    return Incident(name, lat, lon, "FLOOD", severity, people,
                    NOW - age_min * 60, corroborations)


def test_far_critical_is_still_dispatched():
    """A severity-5 incident past the old 120-minute horizon must not be dropped."""
    incidents = [
        flood("CRIT-A", 19.95, 86.05, 5, 40, age_min=40, corroborations=4),
        flood("CRIT-B", 19.94, 86.02, 5, 35, age_min=35, corroborations=3),
    ]
    incidents += [flood(f"minor-{i}", 19.81 + 0.005 * i, 85.83 + 0.005 * i, 1, 2)
                  for i in range(8)]

    plan = optimize(incidents, boats(4), NOW)
    served = {a.incident_id for a in plan}

    eta = travel_minutes(boats(1)[0], 19.95, 86.05)
    assert eta > 120, f"scenario is not testing the far case any more (eta {eta:.0f})"
    assert "CRIT-A" in served, f"far critical was abandoned: {sorted(served)}"
    assert "CRIT-B" in served, f"far critical was abandoned: {sorted(served)}"


def test_critical_beats_trivial_when_units_are_scarce():
    """With fewer units than incidents, the serious ones get served first."""
    incidents = [flood("CRIT", 19.86, 85.88, 5, 40, age_min=30, corroborations=4)]
    incidents += [flood(f"minor-{i}", 19.81 + 0.004 * i, 85.83 + 0.004 * i, 1, 1)
                  for i in range(6)]

    plan = optimize(incidents, boats(2), NOW)
    assert "CRIT" in {a.incident_id for a in plan}


def test_capability_is_required():
    """A unit without the right capability is never dispatched."""
    landslide = Incident("SLIDE-1", 19.82, 85.84, "LANDSLIDE", 4, 10, NOW - 300, 1)
    ambulance = Resource("AMB-1", 19.81, 85.83, "AMBULANCE", {"MEDICAL"}, 4, 45.0)
    digger = Resource("TEAM-1", 19.81, 85.83, "TEAM", {"EXCAVATION"}, 6, 25.0)

    assert not is_capable(ambulance, landslide)
    assert is_capable(digger, landslide)
    assert optimize([landslide], [ambulance], NOW) == []
    assert len(optimize([landslide], [digger], NOW)) == 1


def test_severity_five_zone_blocks_wheeled_units():
    """A cut road is impassable to anything without a hull."""
    from apps.dispatch.engine import BlockedZone

    incident = flood("FLOOD-1", 19.86, 85.88, 4, 10)
    truck = Resource("TRUCK-1", 19.80, 85.82, "TRUCK", {"HIGH_CLEARANCE"}, 30, 35.0)
    zone = BlockedZone(lat=19.83, lon=85.85, radius_km=3.0, severity=5)

    assert travel_minutes(truck, incident.lat, incident.lon, [zone]) == float("inf")
    assert travel_minutes(boats(1)[0], incident.lat, incident.lon, [zone]) < float("inf")


def test_no_units_no_plan():
    assert optimize([flood("i-1", 19.82, 85.84, 5, 10)], [], NOW) == []


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            test()
            print(f"PASS  {name}")
        except AssertionError as exc:
            print(f"FAIL  {name}: {exc}")
            failures += 1

    print("\nall good" if not failures else f"\n{failures} FAILED")
    sys.exit(1 if failures else 0)
