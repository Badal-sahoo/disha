"""Turn database rows into the plain dataclasses engine.py works with.

engine.py imports nothing from Django, which is what keeps the optimiser
testable without a database. This is the boundary.
"""
from .engine import BlockedZone, Incident as EngineIncident, Resource as EngineResource


def engine_resource(res):
    """Resource row -> engine Resource."""
    return EngineResource(
        id=str(res.pk), lat=res.lat, lon=res.lon, kind=res.kind,
        capabilities=set(res.capabilities or []), capacity=res.capacity,
        speed_kmph=res.speed_kmph or 35.0, status=res.status,
        free_at=res.free_at.timestamp() if res.free_at else 0.0,
    )


def engine_incident(inc):
    """Incident row -> engine Incident."""
    return EngineIncident(
        id=str(inc.pk), lat=inc.lat, lon=inc.lon, kind=inc.kind,
        severity=inc.severity, people_affected=inc.people,
        reported_at=inc.reported_at.timestamp(),
        corroborations=inc.corroborations, needs_evacuation=True,
    )


def engine_job(job):
    """Clustered Job -> engine Incident.

    The id is the CLUSTER KEY, not a primary key, because the solver is being
    asked about a scene rather than about a report. build_plan maps it back.
    """
    return EngineIncident(
        id=job.key, lat=job.lat, lon=job.lon, kind=job.kind,
        severity=job.severity, people_affected=job.people,
        reported_at=job.reported_at.timestamp(),
        corroborations=job.corroborations, needs_evacuation=True,
    )


def engine_zones(zones):
    """Zone rows -> engine BlockedZones."""
    return [BlockedZone(lat=z.lat, lon=z.lon, radius_km=z.radius_km, severity=z.severity)
            for z in zones]
