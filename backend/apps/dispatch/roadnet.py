"""Road network: map -> graph -> routing.

Three stages, and only the first one is slow:

  1. BUILD   (once, offline)   OpenStreetMap -> arrays -> a file on disk
  2. LOAD    (once, at boot)   file -> memory
  3. QUERY   (every dispatch)  Dijkstra, cached -> ETA lookups

Stage 1 does NOT run when an alert fires. The roads do not move because a
cyclone was announced -- only the cost of using them changes, and that is
apply_zones() in stage 3. Refetching the map per alert would take minutes and
hand back the same roads.

No new dependencies: the OSM data comes from Overpass over plain HTTP, and the
routing is the numpy/scipy that scipy.optimize already pulls in.
"""
import heapq
import http.client
import io
import json
import math
from collections import OrderedDict
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .engine import haversine_km

# --------------------------------------------------------------------------
# Speeds. OSM's `maxspeed` tag is missing on most Indian rural roads, so these
# defaults do most of the work. Deliberately low -- these are cyclone
# conditions, not a clear day.
# --------------------------------------------------------------------------
SPEED_KMPH = {
    "motorway": 70, "motorway_link": 45,
    "trunk": 60, "trunk_link": 40,
    "primary": 50, "primary_link": 35,
    "secondary": 40, "secondary_link": 30,
    "tertiary": 35, "tertiary_link": 25,
    "unclassified": 25, "residential": 20,
    "living_street": 12, "service": 15, "road": 25,
    # Unpaved village access. In rural Odisha a `track` IS the road to the
    # village -- leaving these out put whole hamlets off the graph, so a unit
    # could be told "no route" to somewhere a jeep reaches every day.
    "track": 15, "path": 8,
}

# Deliberately NOT included: footway, pedestrian, steps, bridleway.
#
# "Every edge" sounds right until an ambulance is routed down a staircase.
# There is one wheeled vehicle class in this graph, so anything added here is
# something a vehicle may be sent along. Tracks and paths are rough but
# driveable; footways and steps are not, and a graph that is wrong is worse
# than one that is small. Add a PEDESTRIAN class first if teams on foot ever
# need their own routing.
FALLBACK_SPEED_KMPH = 25.0

WHEELED, BOAT, HEAVY = "WHEELED", "BOAT", "HEAVY"

# Roads a heavy truck should not be sent down.
HEAVY_BANNED = {"living_street", "service", "track", "path", "footway"}   # a 30-seat truck fits none of these
HEAVY_SPEED_FACTOR = 0.8

# What a rescue unit's kind means for routing.
VEHICLE_CLASS = {"BOAT": BOAT, "TRUCK": HEAVY, "AMBULANCE": WHEELED, "TEAM": WHEELED}

# Finished (origin, target) routes kept in memory.
#
# This used to cache a full Dijkstra solve PER ORIGIN: two arrays the length of
# the graph, about 5 MB each at 420k nodes and 7 MB at 600k. Sixty-four of those
# is 460 MB, which does not fit in Render's 512 MB free tier and was going to be
# an out-of-memory kill rather than a slow page. A* stores one path -- a few
# hundred node ids -- so the same cache size now costs kilobytes.
ROUTE_CACHE_SIZE = 512

# Full origin-to-everywhere solves kept in memory, for the cost matrix.
#
# One per available unit is all a single plan needs. At 600k nodes a float32
# costs array is 2.4 MB, so 32 of them is ~77 MB -- comfortable inside a 512 MB
# instance. This was 64 solves WITH predecessors at 7.2 MB each: 460 MB, and an
# out-of-memory kill rather than a slow page.
COST_CACHE_SIZE = 32

KM_PER_DEGREE_LAT = 111.32

# The public Overpass instances rate-limit hard and return 429/504 under load,
# so try them in turn rather than giving up on the first one.
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)


# ==========================================================================
# STAGE 1 -- BUILD
# ==========================================================================
def fetch_osm_roads(min_lat, min_lon, max_lat, max_lon, timeout=300, on_status=None):
    """Ask Overpass for every drivable way in the box, with its node positions.

    Returns the raw Overpass JSON. This is the slow part -- a district takes
    tens of seconds -- which is why it runs from a management command and never
    from a web request, and why the command saves what comes back.

    on_status is an optional callback for progress messages.
    """
    highways = "|".join(SPEED_KMPH)
    query = f"""
    [out:json][timeout:{timeout}];
    way["highway"~"^({highways})$"]({min_lat},{min_lon},{max_lat},{max_lon});
    (._;>;);
    out body;
    """
    body = urllib.parse.urlencode({"data": query}).encode()
    say = on_status or (lambda message: None)

    last_error = None
    for mirror in OVERPASS_MIRRORS:
        say(f"trying {urllib.parse.urlparse(mirror).netloc} ...")
        request = urllib.request.Request(
            mirror, data=body,
            headers={"User-Agent": "ps05-disaster-response/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                http.client.HTTPException, OSError) as exc:
            # 429 and 504 mean "busy, come back later", not "wrong query".
            #
            # OSError and HTTPException are in this list because Overpass does
            # not always answer with a status code -- under load it simply drops
            # the socket, and http.client raises RemoteDisconnected straight
            # through urlopen. That is not a URLError, so it used to escape this
            # loop entirely, skip every remaining mirror, and kill a 36-tile
            # download on tile 2 with a traceback instead of a retry.
            say(f"  {type(exc).__name__}: {exc}")
            last_error = exc

    raise RuntimeError(
        "every Overpass mirror refused the request. They rate-limit hard -- wait a "
        f"minute and run it again, or pass --cache to reuse an earlier download. "
        f"Last error: {last_error}"
    )


def build_network(osm):
    """Turn Overpass JSON into the arrays we route on.

    Every OSM node becomes a graph node, including the shape points that just
    bend a road. That makes the graph bigger than it strictly needs to be, but
    it means a reconstructed path IS the real road geometry, with no extra work.

    # ponytail: keeping shape points costs memory linear in road length. If a
    # whole state ever has to fit in RAM, contract each run of degree-2 nodes
    # into one edge and store its geometry alongside.
    """
    positions = {}
    for element in osm["elements"]:
        if element["type"] == "node":
            positions[element["id"]] = (element["lat"], element["lon"])

    used_ids = []
    index_of = {}

    def index_for(osm_id):
        """Graph index for an OSM node id, assigned on first sight."""
        if osm_id not in index_of:
            index_of[osm_id] = len(used_ids)
            used_ids.append(osm_id)
        return index_of[osm_id]

    rows, cols, minutes, heavy_ok = [], [], [], []

    for element in osm["elements"]:
        if element["type"] != "way":
            continue

        tags = element.get("tags", {})
        highway = tags.get("highway", "road")
        speed = _tagged_speed(tags) or SPEED_KMPH.get(highway, FALLBACK_SPEED_KMPH)
        one_way = tags.get("oneway") in ("yes", "true", "1")
        allows_heavy = highway not in HEAVY_BANNED

        node_ids = [n for n in element.get("nodes", []) if n in positions]
        for start_id, end_id in zip(node_ids, node_ids[1:]):
            start_lat, start_lon = positions[start_id]
            end_lat, end_lon = positions[end_id]
            km = haversine_km(start_lat, start_lon, end_lat, end_lon)
            if km <= 0:
                continue

            travel_minutes = km / speed * 60.0
            start = index_for(start_id)
            end = index_for(end_id)

            rows.append(start)
            cols.append(end)
            minutes.append(travel_minutes)
            heavy_ok.append(allows_heavy)

            # A two-way road is two edges. Overpass gives us the way once.
            if not one_way:
                rows.append(end)
                cols.append(start)
                minutes.append(travel_minutes)
                heavy_ok.append(allows_heavy)

    if not rows:
        raise ValueError("no drivable roads found in that bounding box")

    lat = np.array([positions[i][0] for i in used_ids], dtype=np.float64)
    lon = np.array([positions[i][1] for i in used_ids], dtype=np.float64)

    return RoadNetwork(
        lat=lat, lon=lon,
        row=np.asarray(rows, dtype=np.int32),
        col=np.asarray(cols, dtype=np.int32),
        base_min=np.asarray(minutes, dtype=np.float64),
        heavy_ok=np.asarray(heavy_ok, dtype=bool),
    )


def _tagged_speed(tags):
    """The road's own maxspeed, in km/h, when OSM happens to carry one."""
    raw = tags.get("maxspeed")
    if not raw:
        return None
    text = str(raw).lower().strip()
    is_mph = "mph" in text
    digits = "".join(c for c in text if c.isdigit())
    if not digits:
        return None
    speed = float(digits)
    return speed * 1.609 if is_mph else speed


# ==========================================================================
# STAGES 2 and 3 -- LOAD and QUERY
# ==========================================================================
class RoadNetwork:
    """The compiled road graph, plus the routing on top of it."""

    def __init__(self, lat, lon, row, col, base_min, heavy_ok):
        self.lat = lat
        self.lon = lon
        self.row = row
        self.col = col
        self.base_min = base_min
        self.heavy_ok = heavy_ok

        self._tree = None
        self._projection = None
        self._graphs = {}        # vehicle class -> scipy CSR matrix
        self._routes = OrderedDict()   # (origin, target, class) -> (minutes, path)  [A*]
        self._costs = OrderedDict()    # (origin, class) -> float32 costs   [Dijkstra]
        self._max_kmph = None    # for the A* heuristic; see _heuristic_scale()
        self._zones = []

        self.rebuild()

    # ---------------- persistence ----------------
    FIELDS = ("lat", "lon", "row", "col", "base_min", "heavy_ok")

    def to_bytes(self):
        """Compressed .npz bytes, ready to store in a database column."""
        buffer = io.BytesIO()
        np.savez_compressed(buffer, **{name: getattr(self, name) for name in self.FIELDS})
        return buffer.getvalue()

    @classmethod
    def from_bytes(cls, blob):
        """Rebuild from to_bytes(). allow_pickle stays off: this must never run code."""
        with np.load(io.BytesIO(blob), allow_pickle=False) as arrays:
            return cls(**{name: arrays[name] for name in cls.FIELDS})

    @property
    def node_count(self):
        return self.lat.size

    @property
    def edge_count(self):
        return self.row.size

    # ---------------- finding the nearest road ----------------
    def _build_tree(self):
        """A KD-tree over roughly-flat kilometres, not degrees.

        A degree of longitude is about 6% shorter than a degree of latitude at
        20 N. Searching in raw degrees would bias every snap eastward.
        """
        if self._tree is not None:
            return
        km_per_lon = KM_PER_DEGREE_LAT * math.cos(math.radians(float(np.mean(self.lat))))
        self._projection = (km_per_lon, KM_PER_DEGREE_LAT)
        self._tree = cKDTree(np.column_stack([self.lon * km_per_lon,
                                              self.lat * KM_PER_DEGREE_LAT]))

    def snap(self, lats, lons):
        """lat/lon -> index of the nearest node on the road network."""
        self._build_tree()
        km_per_lon, km_per_lat = self._projection
        points = np.column_stack([np.asarray(lons, float) * km_per_lon,
                                  np.asarray(lats, float) * km_per_lat])
        _, indices = self._tree.query(points)
        return np.atleast_1d(indices)

    # ---------------- the flood picture ----------------
    def apply_zones(self, zones):
        """Reweight the graph for the current cut roads.

        zones is a list of anything with .lat, .lon, .radius_km and .severity --
        the Zone model rows work directly.

        This is the only expensive thing that happens at run time, and it
        happens when a road is cut, not when a report arrives.
        """
        self._zones = list(zones)
        self.rebuild()

    def rebuild(self):
        """Recompute the per-vehicle weights and throw away cached routes."""
        self._routes.clear()
        self._costs.clear()
        self._graphs.clear()

        # Test each edge by its midpoint. Good enough at these edge lengths.
        mid_lat = 0.5 * (self.lat[self.row] + self.lat[self.col])
        mid_lon = 0.5 * (self.lon[self.row] + self.lon[self.col])

        slowdown = np.ones(self.edge_count)          # wheeled multiplier
        is_cut = np.zeros(self.edge_count, dtype=bool)
        is_flooded = np.zeros(self.edge_count, dtype=bool)

        for zone in self._zones:
            km_per_lon = KM_PER_DEGREE_LAT * math.cos(math.radians(zone.lat))
            distance = np.hypot((mid_lon - zone.lon) * km_per_lon,
                                (mid_lat - zone.lat) * KM_PER_DEGREE_LAT)
            inside = distance < zone.radius_km
            if not inside.any():
                continue

            is_flooded |= inside
            if zone.severity >= 5:
                is_cut |= inside          # the road is gone, not just slow
            else:
                slowdown = np.maximum(slowdown,
                                      np.where(inside, 1.0 + 0.25 * zone.severity, 1.0))

        # Wheeled: slowed in soft zones, stopped by a severity-5 one.
        wheeled = np.where(is_cut, np.inf, self.base_min * slowdown)
        self._graphs[WHEELED] = self._to_matrix(wheeled)

        # Heavy: the same, plus banned road types and a blanket speed penalty.
        heavy = self.base_min * slowdown / HEAVY_SPEED_FACTOR
        heavy = np.where(is_cut | ~self.heavy_ok, np.inf, heavy)
        self._graphs[HEAVY] = self._to_matrix(heavy)

        # Boat: the opposite relationship to water. A flooded road becomes a
        # navigable channel -- slower than a dry road, but passable, and often
        # the only way in. Dry roads stay usable but heavily penalised, because
        # the boat is on a trailer.
        boat = np.where(is_flooded, self.base_min * 1.6, self.base_min * 2.2)
        self._graphs[BOAT] = self._to_matrix(boat)

    def _to_matrix(self, weights):
        reachable = np.isfinite(weights)
        return sp.csr_matrix(
            (weights[reachable], (self.row[reachable], self.col[reachable])),
            shape=(self.node_count, self.node_count),
        )

    # ---------------- routing ----------------
    def _heuristic_scale(self):
        """Minutes-per-km of the FASTEST edge in the graph.

        This is what makes the A* heuristic admissible. h(n) is the straight-line
        distance to the goal divided by the quickest any edge could cover it, so
        it can never overestimate the true remaining cost -- which is the whole
        condition for A* returning the same answer as Dijkstra rather than
        merely a good one.

        Computed once from the edge weights themselves rather than from a
        hardcoded speed limit: a constant that turns out to be lower than some
        road in the data would quietly make the heuristic inadmissible and the
        routes subtly wrong.
        """
        if self._max_kmph is None:
            lengths = _haversine_km(self.lat[self.row], self.lon[self.row],
                                    self.lat[self.col], self.lon[self.col])
            usable = self.base_min > 0
            speeds = np.zeros_like(self.base_min)
            speeds[usable] = lengths[usable] / (self.base_min[usable] / 60.0)
            fastest = float(speeds.max()) if speeds.size else 0.0
            # A floor, so a degenerate graph cannot divide by ~zero and produce
            # an enormous heuristic that breaks admissibility.
            self._max_kmph = max(fastest, 5.0)
        return 60.0 / self._max_kmph

    def _astar(self, origin, target, vehicle_class):
        """Shortest path by travel time, A* with a great-circle heuristic.

        WHY A* AND NOT DIJKSTRA. Dijkstra spreads outwards in every direction
        until it happens to reach the goal; on a district graph that means
        settling most of the district to answer one question. A* is pulled
        towards the goal by h(n), so it settles a fraction of the same nodes for
        an identical answer.

        The previous implementation hid that cost by solving one origin to EVERY
        node and caching the result, which made the second query from the same
        unit free -- but cost 5-7 MB of memory per cached origin and blew the
        deployment's memory budget as the district grew. A* trades that for a
        per-pair search and a cache measured in kilobytes.

        OUT: (minutes, [node, ...]) or (inf, []) when the flooding has cut every
             route between the two.
        """
        key = (int(origin), int(target), vehicle_class)
        cached = self._routes.get(key)
        if cached is not None:
            self._routes.move_to_end(key)
            return cached

        graph = self._graphs[vehicle_class]
        indptr, indices, weights = graph.indptr, graph.indices, graph.data
        lat, lon = self.lat, self.lon
        scale = self._heuristic_scale()
        goal_lat, goal_lon = float(lat[target]), float(lon[target])

        def h(node):
            return _haversine_km_scalar(float(lat[node]), float(lon[node]),
                                        goal_lat, goal_lon) * scale

        origin, target = int(origin), int(target)
        best = {origin: 0.0}
        came_from = {}
        settled = set()
        # (f, g, node). f = g + h is the priority; g is carried so a stale heap
        # entry can be recognised and skipped without a second dict lookup.
        frontier = [(h(origin), 0.0, origin)]

        found = False
        while frontier:
            _, cost, node = heapq.heappop(frontier)
            if node == target:
                found = True
                break
            if node in settled:
                continue          # a better path to this node was already taken
            settled.add(node)

            for edge in range(indptr[node], indptr[node + 1]):
                neighbour = int(indices[edge])
                if neighbour in settled:
                    continue
                step = cost + float(weights[edge])
                if step < best.get(neighbour, math.inf):
                    best[neighbour] = step
                    came_from[neighbour] = node
                    heapq.heappush(frontier, (step + h(neighbour), step, neighbour))

        if not found:
            result = (math.inf, [])
        else:
            path = [target]
            while path[-1] != origin:
                path.append(came_from[path[-1]])
            path.reverse()
            result = (best[target], path)

        self._routes[key] = result
        while len(self._routes) > ROUTE_CACHE_SIZE:
            self._routes.popitem(last=False)
        return result

    def _costs_from(self, origin, vehicle_class):
        """Travel time from one origin to EVERY node. Cached, costs only.

        This is the right tool for the cost matrix, and A* is not.

        The dispatcher asks "how far is this unit from each of 26 scenes?" --
        one origin, many targets. scipy settles the whole graph in one C-level
        sweep and every target is then an array lookup. A* has to run a separate
        search per pair, in Python. Measured on the real workload, 19 units x 12
        scenes: Dijkstra 1.74 s, A* 38.75 s. Same answers to the last decimal;
        22x the wall clock. A 40-second plan endpoint is not a dispatcher.

        Predecessors are NOT requested and costs are stored as float32. The
        matrix only needs distances, and that halves what a cached origin costs
        -- 2.4 MB instead of 7.2 MB at 600k nodes, which is the difference
        between fitting in a 512 MB instance and being killed by it.
        """
        key = (int(origin), vehicle_class)
        cached = self._costs.get(key)
        if cached is not None:
            self._costs.move_to_end(key)
            return cached

        costs = dijkstra(self._graphs[vehicle_class], indices=int(origin),
                         directed=True, return_predecessors=False)
        costs = costs.astype(np.float32)

        self._costs[key] = costs
        while len(self._costs) > COST_CACHE_SIZE:
            self._costs.popitem(last=False)
        return costs

    def travel_minutes(self, from_lat, from_lon, to_lat, to_lon, vehicle_class=WHEELED):
        """Minutes by road, or inf when the flooding has cut every route."""
        origin, target = self.snap([from_lat, to_lat], [from_lon, to_lon])
        return float(self._costs_from(origin, vehicle_class)[target])

    def route(self, from_lat, from_lon, to_lat, to_lon, vehicle_class=WHEELED):
        """The actual road path, by A*.

        THIS is where A* belongs: one origin, one target, and a path rather than
        a distance. Dijkstra would settle most of the district to draw one line,
        and would have to keep a predecessor array the length of the graph to do
        it. A* is pulled towards the goal and keeps only the path it found.

        OUT: {"polyline": [[lat, lon], ...], "minutes": float}
             The polyline is [] when there is no way through.
        """
        origin, target = self.snap([from_lat, to_lat], [from_lon, to_lon])
        minutes, path = self._astar(origin, target, vehicle_class)
        if not path:
            return {"polyline": [], "minutes": float("inf")}
        return {
            "polyline": [[float(self.lat[i]), float(self.lon[i])] for i in path],
            "minutes": float(minutes),
        }


def _haversine_km(lat1, lon1, lat2, lon2):
    """Vectorised great-circle distance, for whole edge arrays at once."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _haversine_km_scalar(lat1, lon1, lat2, lon2):
    """The same, for one pair. Called once per node A* touches, so it avoids
    numpy's per-call overhead -- which dominates at this call count."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def simplify(polyline, max_points=48):
    """Thin a road path down for drawing.

    A real route can be hundreds of shape points. The map only needs the shape,
    and sending every point for every assignment would bloat GET /api/state.
    Keeps the first and last point so the line still starts and ends where it
    should.
    """
    if len(polyline) <= max_points:
        return polyline
    step = len(polyline) / (max_points - 1)
    thinned = [polyline[int(i * step)] for i in range(max_points - 1)]
    thinned.append(polyline[-1])
    return thinned


def merge_osm(chunks):
    """Combine several Overpass responses, dropping the elements that repeat.

    Tiles overlap at their seams, so the same node or way comes back more than
    once. Keeping both would double those edges.
    """
    seen = set()
    elements = []
    for chunk in chunks:
        for element in chunk["elements"]:
            key = (element["type"], element["id"])
            if key not in seen:
                seen.add(key)
                elements.append(element)
    return {"elements": elements}


def tiles(min_lat, min_lon, max_lat, max_lon, grid=3):
    """Split a box into grid x grid smaller boxes.

    Overpass refuses a district-sized query in one go, so it is asked for a
    piece at a time.
    """
    lat_step = (max_lat - min_lat) / grid
    lon_step = (max_lon - min_lon) / grid
    for row in range(grid):
        for col in range(grid):
            yield (min_lat + row * lat_step, min_lon + col * lon_step,
                   min_lat + (row + 1) * lat_step, min_lon + (col + 1) * lon_step)
