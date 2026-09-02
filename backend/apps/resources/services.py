"""resources services: units and shelters.

IMPORT RULE: resources may import accounts. It must NOT import dispatch or
reports. dispatch imports THIS module, not the other way round.
"""
from django.db import transaction
from django.db.models import Q

from apps.common.geo import haversine_km
from apps.realtime.ws import broadcast

from .models import Resource, Shelter
from .serializers import ResourceSerializer, ShelterSerializer


def available_units(now):
    """IDLE units whose free_at has passed. The dispatcher's input.

    Deliberately excludes ENROUTE/ONSCENE/TRANSPORTING: you cannot recall a boat
    that is 80% of the way there, and an optimiser that keeps re-deciding
    produces chaos on the radio.
    """
    return (Resource.objects
            .filter(status=Resource.Status.IDLE)
            .filter(Q(free_at__isnull=True) | Q(free_at__lte=now)))


def release_due(now):
    """Flip units back to IDLE once free_at has passed. Returns how many moved.

    Never touches OUT_OF_SERVICE -- that is an operator's manual override and a
    timer must not undo it.

    AND never touches a crew that is actually working.

    free_at is only ever an ESTIMATE: dispatch time plus the predicted travel.
    This timer exists so a demo keeps moving when nobody is pressing buttons on a
    responder handset. But it was releasing any unit whose estimate had elapsed,
    including one that had reported ON_SCENE thirty seconds earlier -- so a boat
    in the middle of taking people off a roof went IDLE, re-entered the solve,
    and was dispatched somewhere else. Measured on the seeded scenario: a unit
    at ON_SCENE was pulled off an active rescue by this function.

    A responder who has ACCEPTED has taken control; from then on only the status
    walk in dispatch.services.progress may move that unit. The timer keeps its
    job for units nobody has touched.
    """
    from apps.dispatch.models import Assignment   # local: avoids an import cycle

    driven_by_a_human = set(
        Assignment.objects
        .exclude(status__in=[Assignment.Status.PROPOSED,
                             Assignment.Status.DISPATCHED,
                             Assignment.Status.COMPLETE])
        .values_list("resource_id", flat=True)
    )

    finished_units = [
        unit for unit in Resource.objects
        .filter(free_at__lte=now)
        .exclude(status__in=[Resource.Status.OUT_OF_SERVICE, Resource.Status.IDLE])
        if unit.pk not in driven_by_a_human
    ]
    if not finished_units:
        return 0

    unit_ids = [unit.pk for unit in finished_units]
    Resource.objects.filter(pk__in=unit_ids).update(status=Resource.Status.IDLE)

    for unit in finished_units:
        unit.status = Resource.Status.IDLE
        broadcast("resource.update", ResourceSerializer(unit).data)

    return len(finished_units)


def _change_occupancy(shelter, delta, require_room=False):
    """Add `delta` people to a shelter and tell every dashboard.

    delta is signed: +12 when a group arrives, -12 when they leave. Occupancy is
    kept inside 0..capacity.

    require_room=True means "only do this if it actually fits" -- that is the
    dispatch path, which must not overbook. It returns None when it does not fit.

    The select_for_update() row lock is not optional. Reading and then writing
    without it is how two boats get sent to the same thirty free beds.
    """
    with transaction.atomic():
        locked = Shelter.objects.select_for_update().get(pk=shelter.pk)

        if require_room:
            if locked.status != Shelter.Status.OPEN or locked.remaining < delta:
                return None

        new_occupancy = locked.occupancy + delta
        new_occupancy = max(new_occupancy, 0)
        new_occupancy = min(new_occupancy, locked.capacity)
        locked.occupancy = new_occupancy

        # INACCESSIBLE is an operator's decision; only they clear it.
        if locked.status != Shelter.Status.INACCESSIBLE:
            if locked.remaining == 0:
                locked.status = Shelter.Status.FULL
            else:
                locked.status = Shelter.Status.OPEN

        locked.save(update_fields=["occupancy", "status"])

    # Broadcast after the transaction commits, never inside it.
    broadcast("shelter.update", ShelterSerializer(locked).data)
    shelter.occupancy = locked.occupancy
    shelter.status = locked.status
    return locked


def reserve_shelter(shelter, people):
    """Hold beds AT DISPATCH TIME, not on arrival. False when it no longer fits."""
    if people <= 0:
        return True
    return _change_occupancy(shelter, people, require_room=True) is not None


def adjust_occupancy(shelter, delta):
    """Walk-ins arrive without a rescue team, so an operator has to be able to
    correct the count or it drifts from reality within the hour."""
    return _change_occupancy(shelter, delta)


def nearest_shelter(lat, lon, n=1, people=1, kind=Shelter.Kind.SHELTER):
    """Nearest OPEN places of the given kind with room, nearest-first, at most n.

    `kind` matters now that hospitals live in this table: asking for somewhere to
    evacuate a village and being handed a 30-bed CHC is the same category error
    the dispatcher used to make in reverse.

    A district has tens of these, so a Python sort is fine and avoids PostGIS.
    dispatch.engine.choose_shelter() does the same job with zone awareness; this
    exists for /api/shelters/nearest, which has no zone context and must not
    import apps.dispatch.
    """
    people = max(people, 1)

    big_enough = []
    for shelter in Shelter.objects.filter(status=Shelter.Status.OPEN, kind=kind):
        if shelter.remaining >= people:
            big_enough.append(shelter)

    def distance_from_here(shelter):
        return haversine_km(lat, lon, shelter.lat, shelter.lon)

    big_enough.sort(key=distance_from_here)
    return big_enough[:n]
