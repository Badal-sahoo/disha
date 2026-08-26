"""resources services -- pure CRUD lives in the views; these are the queries the
dispatcher depends on, plus the supply transportation problem.

IMPORT RULE: resources may import accounts. It must NOT import dispatch or
reports. dispatch imports THIS module, not the other way round.
"""
from .serializers import ResourceSerializer, ShelterSerializer
from .models import Resource, Shelter
from realtime.broadcast import broadcast
from django.db.models import Q
from django.db import transaction


def available_units(now):
    """The dispatcher's input. Everything else stays frozen.

    IN:  now = datetime          # timezone-aware
    OUT: QuerySet[Resource]      # evaluate it or not; dispatch.build_plan() iterates once

    DB:  SELECT * FROM resources_resource
           WHERE status = 'IDLE'
             AND (free_at IS NULL OR free_at <= %s)
         status is db_index'd. Do NOT include ENROUTE/ONSCENE/TRANSPORTING --
         you cannot recall a boat that is 80% of the way there, and an optimiser
         that keeps re-deciding produces chaos on the radio.

    CALLED BY: dispatch/services.py open_set() and run_cycle()
    """
    return (Resource.objects
            .filter(status=Resource.Status.IDLE)
            .filter(Q(free_at__isnull=True) | Q(free_at__lte=now)))
def release_due(now):
    """Flip units back to IDLE once their free_at has passed. Called at the top
    of every dispatch cycle, before anything is read.

    IN:  now = datetime
    OUT: int                     # how many rows were flipped

    DB:  UPDATE resources_resource SET status = 'IDLE'
           WHERE free_at <= %s AND status <> 'OUT_OF_SERVICE'
         Never touch OUT_OF_SERVICE -- that is an operator's manual override and
         a timer must not undo it.

    EMITS: for each flipped unit,
           realtime.broadcast("resource.update", {id, lat, lon, status, free_at})

    CALLED BY: dispatch/services.py run_cycle(), first statement.
    """
    due = list(Resource.objects
               .filter(free_at__lte=now)
               .exclude(status=Resource.Status.OUT_OF_SERVICE)
               .exclude(status=Resource.Status.IDLE))
    if not due:
        return 0

    # OUT_OF_SERVICE is an operator's manual override -- a timer must never undo it.
    Resource.objects.filter(pk__in=[r.pk for r in due]).update(status=Resource.Status.IDLE)
    for r in due:
        r.status = Resource.Status.IDLE
        broadcast("resource.update", ResourceSerializer(r).data)
    return len(due)
def set_busy(resource, until, lat, lon):
    """Mark a unit busy and move it to where it will END UP -- the shelter, not
    the incident. Otherwise its next job is planned from the wrong origin.

    IN:  resource = Resource
         until    = datetime      # free_at
         lat, lon = float         # destination, i.e. the shelter (or the
                                  # incident when no evacuation is involved)
    OUT: None

    DB:  UPDATE resources_resource
           SET status='ENROUTE', free_at=%s, lat=%s, lon=%s WHERE id=%s
         Call it inside the same transaction.atomic() as commit_plan().

    EMITS: broadcast("resource.update", {id, lat, lon, status, free_at})

    CALLED BY: dispatch/services.py commit_plan()
    """
    resource.status = Resource.Status.ENROUTE
    resource.free_at = until
    # Move it to where it will END UP, not where the incident is -- otherwise its
    # next job gets planned from the wrong origin.
    if lat is not None:
        resource.lat = lat
    if lon is not None:
        resource.lon = lon
    resource.save(update_fields=["status", "free_at", "lat", "lon"])
    broadcast("resource.update", ResourceSerializer(resource).data)
def nearest_shelter(lat, lon, n=1, people=1):
    """Nearest shelter that can actually take the group.

    IN:  lat, lon = float
         n        = int    how many to return; 1 -> the single best
         people   = int    group size; a shelter with fewer beds than this is
                           not a candidate at all
    OUT: [Shelter, ...]    ordered nearest-first, length <= n. [] when none fit.

    DB:  SELECT * FROM resources_shelter WHERE status = 'OPEN'
         Then rank in Python with dispatch.engine.haversine_km (or common.geo).
         A district has tens of shelters -- a Python sort is fine and avoids
         PostGIS entirely.

    USES: dispatch.engine.choose_shelter() already implements exactly this and
          also handles blocked zones. Prefer delegating to it from dispatch;
          this function exists for /api/shelters/nearest, which has no zone
          context and must not import dispatch.

    CALLED BY: resources/views.py NearestShelterView (GET /api/shelters/nearest)
    """
    raise NotImplementedError("resources.services.nearest_shelter -- Track 1 - Day 2")


def reserve_shelter(shelter, people):
    """Reserve beds AT DISPATCH TIME, not on arrival.

    IN:  shelter = Shelter
         people  = int
    OUT: bool                    # True if reserved, False if it no longer fits

    DB:  with transaction.atomic():
             s = Shelter.objects.select_for_update().get(pk=shelter.pk)
             if s.remaining < people: return False
             s.occupancy += people
             if s.remaining == 0: s.status = 'FULL'
             s.save(update_fields=["occupancy", "status"])
         The select_for_update() is not optional. Read-then-write without the
         row lock is how two boats get routed to the same thirty free beds --
         it is the bug this function exists to prevent.

    EMITS: broadcast("shelter.update", {id, occupancy, remaining, status})

    CALLED BY: dispatch/services.py commit_plan(), inside its transaction.
    """
    if people <= 0:
        return True

    with transaction.atomic():
        # The row lock is the whole point. Read-then-write without it is how two
        # boats get routed to the same thirty free beds.
        locked = Shelter.objects.select_for_update().get(pk=shelter.pk)
        if locked.status != Shelter.Status.OPEN or locked.remaining < people:
            return False
        locked.occupancy += people
        if locked.remaining == 0:
            locked.status = Shelter.Status.FULL
        locked.save(update_fields=["occupancy", "status"])

    # Broadcast AFTER the transaction commits, never inside it.
    broadcast("shelter.update", ShelterSerializer(locked).data)
    shelter.occupancy, shelter.status = locked.occupancy, locked.status
    return True
def adjust_occupancy(shelter, delta):
    """Walk-ins arrive without a rescue team. Occupancy must be editable or it
    drifts from reality within the hour.

    IN:  shelter = Shelter
         delta   = int            # signed; +12 arriving, -12 leaving
    OUT: Shelter                  # refreshed instance

    DB:  same select_for_update() pattern as reserve_shelter.
         Clamp: occupancy never below 0, never above capacity.
         Recompute status: FULL when remaining hits 0, back to OPEN when it
         rises above 0 -- but never overwrite INACCESSIBLE, which only an
         operator clears.

    EMITS: broadcast("shelter.update", {id, occupancy, remaining, status})

    CALLED BY: resources/views.py ShelterDetailView.patch
    """
    raise NotImplementedError("resources.services.adjust_occupancy -- Track 1 - Day 2")


def compute_supply_plan():
    """F14 -- a transportation problem, not an assignment problem.

    IN:  --
    OUT: [
           {depot: str, shelter: str, item: str, quantity: int, cost: float},
           ...
         ]
         depot/shelter are CODES, not PKs -- the map layer labels arrows with them.

    DB:  SELECT depot, item, quantity FROM resources_supplystock JOIN depot
         SELECT code, lat, lon, occupancy FROM resources_shelter WHERE status='OPEN'
         Read-only. Nothing is written until commit_supply_plan().

    USES: networkx.min_cost_flow -- about fifteen lines.
          supply  = stock quantity at each depot
          demand  = shelter.occupancy * KIT_PER_PERSON (1 kit, 3 L water, ...)
          edge cost = haversine_km(depot, shelter)
          Run it once per item type; four small graphs beat one multi-commodity.

    CALLED BY: resources/views.py SupplyPlanView (GET /api/supply/plan)
    NOTE: first thing to cut if a track slips. Runs on a 15-minute batch, never
          on every report.
    """
    raise NotImplementedError("resources.services.compute_supply_plan -- Track 5 - Day 3")


def commit_supply_plan(flows):
    """Decrement depot stock and create the delivery tasks.

    IN:  flows = [{depot: str, shelter: str, item: str, quantity: int}, ...]
                 # depot/shelter are codes, straight back from compute_supply_plan
    OUT: {committed: int, rejected: [{depot, shelter, item, reason: str}, ...]}
         reason is "insufficient_stock" | "shelter_closed" | "unknown_code"

    DB:  one transaction.atomic() for the whole batch:
           SELECT ... FROM resources_supplystock
             WHERE depot_id=%s AND item=%s FOR UPDATE
           UPDATE quantity = quantity - %s      -- reject, do not go negative
         unique_together ("depot","item") means one row per pair; no ambiguity.

    CALLED BY: resources/views.py SupplyCommitView (POST /api/supply/commit)
    """
    raise NotImplementedError("resources.services.commit_supply_plan -- Track 5 - Day 3")
