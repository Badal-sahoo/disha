"""A unit accepting a job, arriving, and finishing it."""
from django.db import transaction
from django.utils import timezone

from apps.realtime.ws import broadcast

from ..models import Assignment
from .assign import run_cycle


# The assignment lifecycle in one table: what each status is allowed to become.
# The first entry is the normal next step, and that is what gets returned as
# "next" -- the responder app shows it as the button to press.
Status = Assignment.Status
ALLOWED = {
    Status.DISPATCHED:   [Status.ACCEPTED],
    Status.ACCEPTED:     [Status.EN_ROUTE],
    Status.EN_ROUTE:     [Status.ON_SCENE],
    Status.ON_SCENE:     [Status.TRANSPORTING, Status.COMPLETE],
    Status.TRANSPORTING: [Status.COMPLETE],
    Status.COMPLETE:     [],
}
# What reaching a status does to the vehicle. ACCEPTED does not move it.
UNIT_STATUS = {
    Status.EN_ROUTE: "ENROUTE",
    Status.ON_SCENE: "ONSCENE",
    Status.TRANSPORTING: "TRANSPORTING",
    Status.COMPLETE: "IDLE",
}


def apply_status(assignment, new_status, rescued=None):
    """Walk an assignment through its lifecycle with all side effects.

    Returns {ok: True, next: <the status that may follow>}.
    Raises ValueError on an illegal transition.
    """
    from apps.reports.models import Incident
    from apps.resources.models import Resource
    from apps.resources.serializers import ResourceSerializer

    allowed = ALLOWED.get(assignment.status, [])
    if new_status not in allowed:
        raise ValueError(f"Illegal status transition: {assignment.status} -> {new_status}. "
                         f"Allowed: {allowed}")

    now = timezone.now()
    resolved_ids = []

    with transaction.atomic():
        assignment.status = new_status

        if new_status == Status.ON_SCENE:
            assignment.arrived_at = now
            from apps.reports.services.make_incident import mark_first_response
            mark_first_response(assignment.incident, now)
        elif new_status == Status.COMPLETE:
            assignment.completed_at = now
            if rescued is not None:
                assignment.rescued_count = rescued
            resolved_ids = _resolve_scene_if_done(assignment, now)

        unit_status = UNIT_STATUS.get(new_status)
        if unit_status:
            fields = {"status": unit_status}
            if new_status == Status.COMPLETE:
                # Only actually free if this crew has nowhere else to be.
                #
                # A unit can carry a follow-up leg -- "this scene, then that
                # one". Marking it IDLE the moment leg 0 finishes handed it back
                # to the optimiser, which cheerfully sent it somewhere else and
                # orphaned the second stop the crew had already been told about.
                next_leg = (Assignment.objects
                            .filter(resource_id=assignment.resource_id)
                            .exclude(pk=assignment.pk)
                            .exclude(status__in=[Status.PROPOSED, Status.COMPLETE])
                            .order_by("leg")
                            .first())
                if next_leg is not None:
                    fields["status"] = "ENROUTE"
                else:
                    fields["free_at"] = now
            Resource.objects.filter(pk=assignment.resource_id).update(**fields)

        assignment.save(update_fields=["status", "arrived_at", "completed_at", "rescued_count"])

    broadcast("assignment.update", {"id": assignment.pk, "code": assignment.code,
                                    "status": new_status, "ts": now.isoformat()})
    res = Resource.objects.get(pk=assignment.resource_id)
    broadcast("resource.update", ResourceSerializer(res).data)

    if new_status == Status.COMPLETE:
        for incident_id in resolved_ids:
            broadcast("incident.update", {"id": incident_id, "status": "RESOLVED"})
        run_cycle("unit_freed")

    return {"ok": True, "next": (ALLOWED.get(new_status) or [None])[0]}


def _resolve_scene_if_done(assignment, now):
    """Close the whole scene, but ONLY when the last unit on it has finished.

    Two things were wrong before, and both showed up the moment a scene could
    take more than one unit:

      * The FIRST unit to finish marked the incident RESOLVED, while three other
        crews were still working the same village. The board said the job was
        done and the optimiser stopped counting it.
      * Only the primary report was closed. The other four callers stayed
        ASSIGNED for ever, so a scene never fully cleared.

    Returns the incident ids actually resolved, for broadcasting.
    """
    from apps.reports.models import Incident

    incident = assignment.incident

    # Every report in the same cell and of the same kind is the same emergency,
    # the way services/clustering.py groups them for the solver.
    scene = Incident.objects.filter(cell_id=incident.cell_id, kind=incident.kind)
    scene_ids = list(scene.values_list("pk", flat=True))

    still_working = (Assignment.objects
                     .filter(incident_id__in=scene_ids)
                     .exclude(pk=assignment.pk)
                     .exclude(status__in=[Status.PROPOSED, Status.COMPLETE])
                     .exists())
    if still_working:
        return []

    to_resolve = list(scene.exclude(status=Incident.Status.RESOLVED)
                           .values_list("pk", flat=True))
    if to_resolve:
        Incident.objects.filter(pk__in=to_resolve).update(
            status=Incident.Status.RESOLVED)
    return to_resolve


def update_unit_location(resource, lat, lon):
    """The 20-second beacon: move the unit and tell every dashboard."""
    resource.lat, resource.lon = lat, lon
    resource.save(update_fields=["lat", "lon"])
    broadcast("resource.update", {
        "id": resource.pk, "lat": lat, "lon": lon, "status": resource.status,
        "free_at": resource.free_at.isoformat() if resource.free_at else None,
    })
