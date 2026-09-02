"""
PS-05 Allocation Engine
=======================
Pure-Python, framework-free. Drop into a Django app as `allocation/engine.py`.
No Django imports here on purpose: it stays unit-testable and you can run the
simulator against it without spinning up the ORM.

Core idea
---------
Dispatch is modelled as a RECTANGULAR LINEAR ASSIGNMENT PROBLEM solved to
global optimality with the Hungarian / Jonker-Volgenant algorithm
(scipy.optimize.linear_sum_assignment).

Objective:  maximise  SUM over assigned (incident, resource) of
                w_i * (T_HORIZON - eta_ir)
            i.e. total PRIORITY-WEIGHTED RESPONSE TIME SAVED.

Written as a minimisation (what scipy wants):
            cost_ir = w_i * (eta_ir - T_HORIZON)

Why this shape and not the obvious `cost = distance`:
  * A plain distance matrix on a rectangular problem is a TRAP. scipy assigns
    exactly min(n_incidents, n_resources) pairs and picks the set with lowest
    total cost -- so when incidents outnumber resources it happily serves the
    CHEAP (close, low-severity) ones and starves the critical ones. Weighting a
    distance cost makes that worse, not better.
  * The (eta - T_HORIZON) form makes every worthwhile assignment NEGATIVE, and
    scales the size of that negative number with priority. A severity-5 call
    30 min away beats a severity-1 call 5 min away, which is what an ops room
    actually wants.
  * Anything that comes back with cost >= 0 is discarded after the solve. That
    single rule cleanly handles three cases at once: capability mismatch
    (cost = +INF_PENALTY), resource further away than the planning horizon, and
    "not worth sending anyone".
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

# --------------------------------------------------------------------------
# Tunables -- expose these in Django settings so you can defend each number.
# --------------------------------------------------------------------------
T_HORIZON_MIN = 120.0     # planning horizon. Beyond this, a dispatch scores ~0.
INF_PENALTY = 1e6         # marker cost for a hard-infeasible pair
ROAD_FACTOR = 1.35        # straight-line km -> road km (Indian district roads)
BLOCKED_DETOUR = 1.75     # travel-time multiplier when route clips a cut zone
BLOCKED_HARD_SEV = 5      # zones at this severity are impassable, not slow

# Priority weights -- must sum to 1.0
W_SEVERITY = 0.45
W_PEOPLE = 0.25
W_AGE = 0.20
W_CORROB = 0.10

AGE_SATURATION_MIN = 45.0     # a report at this age has maxed its age boost
PEOPLE_SATURATION = 50.0      # people_affected at which the people term maxes
CORROB_SATURATION = 5         # independent reports at which corroboration maxes

MARGINAL_SLOT_DECAY = 0.6     # value of the 2nd unit sent to one scene, 3rd, ...
MAX_SLOTS_PER_INCIDENT = 4

# Minutes a crew spends working a scene before it can leave for the next one.
# Only used when chaining a SECOND job onto a unit that already has one: leg 1's
# ETA is leg 0 + this + the travel between the two. Sending a boat "straight on"
# with no working time is the sort of number that looks great in a demo and gets
# a crew blamed on the night.
ON_SCENE_MIN = 20.0

# --------------------------------------------------------------------------
# Domain model
# --------------------------------------------------------------------------
FLOOD, CYCLONE, LANDSLIDE = "FLOOD", "CYCLONE", "LANDSLIDE"

# Capability tags a resource can carry, and what each disaster type demands.
CAP_BOAT = "BOAT"
CAP_HIGH_CLEARANCE = "HIGH_CLEARANCE"
CAP_MEDICAL = "MEDICAL"
CAP_EXCAVATION = "EXCAVATION"
CAP_ROPE_RESCUE = "ROPE_RESCUE"

REQUIRED_CAPS: Dict[str, Set[str]] = {
    # A resource must carry AT LEAST ONE of these to be dispatchable to the type.
    FLOOD:     {CAP_BOAT, CAP_HIGH_CLEARANCE},
    CYCLONE:   {CAP_HIGH_CLEARANCE, CAP_MEDICAL, CAP_ROPE_RESCUE},
    LANDSLIDE: {CAP_EXCAVATION, CAP_ROPE_RESCUE},
}


@dataclass
class Incident:
    id: str
    lat: float
    lon: float
    kind: str                       # FLOOD | CYCLONE | LANDSLIDE
    severity: int                   # 1..5
    people_affected: int
    reported_at: float              # simulation minutes (or epoch seconds)
    corroborations: int = 1         # count of independent reports in this cell
    needs_evacuation: bool = True
    assigned_to: List[str] = field(default_factory=list)
    first_response_at: Optional[float] = None

    def priority(self, now: float) -> float:
        """Normalised 0..1 urgency. Monotone in severity, size, age, corroboration."""
        sev = (self.severity - 1) / 4.0
        ppl = min(self.people_affected / PEOPLE_SATURATION, 1.0)
        age = min(max(now - self.reported_at, 0.0) / AGE_SATURATION_MIN, 1.0)
        cor = min((self.corroborations - 1) / (CORROB_SATURATION - 1), 1.0)
        return W_SEVERITY * sev + W_PEOPLE * ppl + W_AGE * age + W_CORROB * cor


@dataclass
class Resource:
    id: str
    lat: float
    lon: float
    kind: str                       # TEAM | BOAT | AMBULANCE | TRUCK
    capabilities: Set[str]
    capacity: int                   # people it can move per trip
    speed_kmph: float
    status: str = "IDLE"            # IDLE | ENROUTE | ONSCENE | TRANSPORTING
    free_at: float = 0.0
    home_lat: float = 0.0
    home_lon: float = 0.0

    def is_available(self, now: float) -> bool:
        return self.status == "IDLE" and self.free_at <= now


SHELTER, HOSPITAL = "SHELTER", "HOSPITAL"


@dataclass
class Shelter:
    """Somewhere people can be taken. `kind` decides WHO may be taken there."""
    id: str
    lat: float
    lon: float
    capacity: int
    occupancy: int = 0
    status: str = "OPEN"            # OPEN | FULL | INACCESSIBLE
    kind: str = SHELTER             # SHELTER | HOSPITAL

    @property
    def remaining(self) -> int:
        if self.status != "OPEN":
            return 0
        return max(self.capacity - self.occupancy, 0)


@dataclass
class BlockedZone:
    """A flooded / landslid / storm-surge area that degrades or cuts roads."""
    lat: float
    lon: float
    radius_km: float
    severity: int                   # 5 == impassable


# --------------------------------------------------------------------------
# Geometry & travel time
# --------------------------------------------------------------------------
EARTH_R_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def _point_seg_dist_km(px, py, ax, ay, bx, by) -> float:
    """Distance from point P to segment AB, in km, using a local flat-earth
    projection. Good to <1% at district scale, and ~200x faster than doing it
    properly -- which matters because this runs inside the cost-matrix loop."""
    latf = 111.32
    lonf = 111.32 * math.cos(math.radians((ay + by) / 2.0))
    ax_, ay_ = ax * lonf, ay * latf
    bx_, by_ = bx * lonf, by * latf
    px_, py_ = px * lonf, py * latf
    dx, dy = bx_ - ax_, by_ - ay_
    if dx == 0 and dy == 0:
        return math.hypot(px_ - ax_, py_ - ay_)
    t = ((px_ - ax_) * dx + (py_ - ay_) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px_ - (ax_ + t * dx), py_ - (ay_ + t * dy))


def travel_minutes(res: Resource, lat: float, lon: float,
                   blocked: Sequence[BlockedZone] = ()) -> float:
    """ETA in minutes. Straight-line * road factor, then penalised or blocked
    where the route clips a cut zone.

    In production swap the first two lines for an OSRM /route call and keep the
    blocked-zone pass exactly as-is -- OSRM gives you a polyline, you test the
    polyline against the zones instead of the single segment."""
    km = haversine_km(res.lat, res.lon, lat, lon) * ROAD_FACTOR
    minutes = (km / max(res.speed_kmph, 1.0)) * 60.0

    penalty = 1.0
    for z in blocked:
        d = _point_seg_dist_km(z.lon, z.lat, res.lon, res.lat, lon, lat)
        if d < z.radius_km:
            if z.severity >= BLOCKED_HARD_SEV and CAP_BOAT not in res.capabilities:
                return math.inf          # road is gone; only boats get through
            penalty = max(penalty, BLOCKED_DETOUR)
    return minutes * penalty


# --------------------------------------------------------------------------
# Feasibility
# --------------------------------------------------------------------------
def is_capable(res: Resource, inc: Incident) -> bool:
    return bool(res.capabilities & REQUIRED_CAPS.get(inc.kind, set()))


# --------------------------------------------------------------------------
# The optimiser
# --------------------------------------------------------------------------
@dataclass
class Assignment:
    incident_id: str
    resource_id: str
    eta_min: float
    slot: int
    gain: float          # priority-weighted minutes saved; bigger is better


def build_demand_slots(incidents: Sequence[Incident], now: float
                       ) -> List[Tuple[Incident, int, float]]:
    """One scene may need more than one unit. Rather than jump to a min-cost
    flow, we replicate the incident into `k` slots and let the assignment
    problem fill as many as are worth filling.

    Slot value decays geometrically: the FIRST boat at a scene is worth far more
    than the third. That decay is what stops the optimiser from dogpiling one
    big incident while a neighbouring one gets nobody."""
    slots: List[Tuple[Incident, int, float]] = []
    for inc in incidents:
        base = inc.priority(now)
        already = len(inc.assigned_to)
        need = 1
        if inc.needs_evacuation:
            need = max(1, math.ceil(inc.people_affected / 12.0))
        need = min(need, MAX_SLOTS_PER_INCIDENT) - already
        for k in range(max(need, 0)):
            slots.append((inc, already + k, base * (MARGINAL_SLOT_DECAY ** (already + k))))
    return slots


def optimize(incidents: Sequence[Incident],
             resources: Sequence[Resource],
             now: float,
             blocked: Sequence[BlockedZone] = (),
             eta_fn=None) -> List[Assignment]:
    """Globally optimal dispatch for the current open set.

    eta_fn(resource, lat, lon) -> minutes, defaulting to the straight-line
    estimate in travel_minutes(). The caller injects a road-graph version, which
    is what makes the DECISION and the ETA the operator reads the same number.
    They used to disagree by up to 16 minutes on a real seeded plan: the solver
    chose units on haversine * 1.35 while the dashboard drew the routed path.
    Keeping the default means this module still runs with no Django and no graph.

    Only UNSERVED incidents and AVAILABLE resources should be passed in. Units
    already rolling stay rolling -- you cannot recall a boat that is 80% of the
    way there, and an optimiser that keeps re-deciding produces chaos on the
    radio, which is the single most common way this kind of system fails in
    the field."""
    if eta_fn is None:
        def eta_fn(res, lat, lon):
            return travel_minutes(res, lat, lon, blocked)

    slots = build_demand_slots(incidents, now)
    avail = [r for r in resources if r.is_available(now)]
    if not slots or not avail:
        return []

    n, m = len(slots), len(avail)
    cost = np.full((n, m), INF_PENALTY, dtype=float)
    etas = np.full((n, m), math.inf, dtype=float)

    for i, (inc, slot_idx, w) in enumerate(slots):
        for j, res in enumerate(avail):
            if not is_capable(res, inc):
                continue
            eta = eta_fn(res, inc.lat, inc.lon)
            if not math.isfinite(eta):
                continue
            etas[i, j] = eta
            # capacity waste: a 40-seat truck sent to 2 people is a small sin,
            # not a crime -- so it is a soft term, never a constraint.
            waste = 0.0
            if inc.needs_evacuation and inc.people_affected > 0:
                over = max(res.capacity - inc.people_affected, 0)
                waste = 0.15 * min(over / max(res.capacity, 1), 1.0)
            # Urgent work is worth going further for. A flat 120-minute horizon
            # made a severity-5 incident 130 minutes away score positive, so it
            # was dropped while trivial nearby ones were served.
            horizon = T_HORIZON_MIN * (1.0 + w)
            cost[i, j] = w * (1.0 - waste) * (eta - horizon)

    rows, cols = linear_sum_assignment(cost)

    out: List[Assignment] = []
    for i, j in zip(rows, cols):
        c = cost[i, j]
        if c >= 0:            # infeasible, over-horizon, or simply not worth it
            continue
        inc, slot_idx, w = slots[i]
        out.append(Assignment(incident_id=inc.id, resource_id=avail[j].id,
                              eta_min=float(etas[i, j]), slot=slot_idx, gain=float(-c)))
    out.sort(key=lambda a: -a.gain)
    return out


# --------------------------------------------------------------------------
# Stage 2 -- shelter assignment (capacity-constrained, reserved atomically)
# --------------------------------------------------------------------------
def choose_shelter(lat: float, lon: float, people: int,
                   shelters: Sequence[Shelter],
                   blocked: Sequence[BlockedZone] = (),
                   kind: str = SHELTER,
                   fallback: bool = True) -> Optional[Shelter]:
    """Nearest place of the RIGHT KIND that can actually take the group.

    kind=HOSPITAL is what an ambulance gets. Without it every casualty was
    routed to whichever building happened to be nearest, which in the seeded
    district meant carrying an unconscious man to a community hall.

    fallback=True lets a hospital search fall back to a plain shelter when no
    hospital has room -- somewhere staffed is better than nowhere. It never
    falls the other way: an evacuated village is not sent to occupy a hospital.

    Capacity is decremented by the caller at reservation time, not at arrival --
    otherwise two boats get routed to the same 30 free beds.
    """
    def nearest(want_kind):
        best, best_km = None, math.inf
        for s in shelters:
            if s.kind != want_kind or s.remaining < people:
                continue
            km = haversine_km(lat, lon, s.lat, s.lon)
            for z in blocked:
                if z.severity >= BLOCKED_HARD_SEV and \
                   _point_seg_dist_km(z.lon, z.lat, lon, lat, s.lon, s.lat) < z.radius_km:
                    km = math.inf
            if km < best_km:
                best, best_km = s, km
        return best

    found = nearest(kind)
    if found is None and kind == HOSPITAL and fallback:
        found = nearest(SHELTER)
    return found
