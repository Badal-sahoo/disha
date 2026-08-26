"""
PS-05 road network
==================
Map -> graph -> routing, in the shape the dispatcher actually needs.

Three stages, and only the first one is slow:

  1. BUILD    (once, offline)   OSM -> NetworkX -> scipy CSR -> pickle
  2. LOAD     (once, at boot)   pickle -> memory
  3. QUERY    (every dispatch)  cached Dijkstra -> O(1) ETA lookups

Stage 1 never runs on a request path and never runs "when an alert fires".
The road network does not change because a cyclone was announced -- only the
cost of using it does, and that is stage 3's `apply_zones`.
"""

import math
import pickle
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

# --------------------------------------------------------------------------
# Speeds. OSM `maxspeed` is missing on most Indian rural ways, so these
# defaults do most of the work. Deliberately conservative -- these are cyclone
# conditions, not a clear day.
# --------------------------------------------------------------------------
DEFAULT_SPEED_KMPH = {
    "motorway": 70, "motorway_link": 45,
    "trunk": 60, "trunk_link": 40,
    "primary": 50, "primary_link": 35,
    "secondary": 40, "secondary_link": 30,
    "tertiary": 35, "tertiary_link": 25,
    "unclassified": 25, "residential": 20,
    "living_street": 12, "service": 15, "track": 12, "road": 25,
}
FALLBACK_SPEED_KMPH = 25.0

# Vehicle classes. Each gets its own weight vector over the SAME topology.
WHEELED, BOAT, HEAVY = "WHEELED", "BOAT", "HEAVY"
VEHICLE_CLASSES = (WHEELED, BOAT, HEAVY)

# Ways a heavy truck should avoid or cannot use.
HEAVY_BANNED = {"living_street", "track", "service", "path", "footway"}
HEAVY_SPEED_FACTOR = 0.8


# ==========================================================================
# STAGE 1 -- BUILD (offline, minutes, run once)
# ==========================================================================
def download_osm_graph(place_or_bbox, network_type: str = "drive", simplify: bool = True):
    """Fetch a drivable graph from OpenStreetMap via OSMnx.

    Two ways to call it:
        download_osm_graph("Puri, Odisha, India")
        download_osm_graph((85.60, 19.70, 86.15, 20.55))   # (W, S, E, N)

    For a whole district or three, prefer the offline route instead -- Overpass
    will rate-limit or time out on large areas:

        1. grab the regional extract from Geofabrik (India is published as
           sub-region .osm.pbf files; Odisha sits in the eastern zone)
        2. crop it with osmium:
             osmium extract -b 85.60,19.70,86.15,20.55 in.osm.pbf -o puri.osm.pbf
        3. parse with pyrosm, which is far faster than Overpass:
             from pyrosm import OSM
             G = OSM("puri.osm.pbf").to_graph(nodes, edges, graph_type="networkx")
    """
    import osmnx as ox
    ox.settings.use_cache = True
    if isinstance(place_or_bbox, (tuple, list)):
        G = ox.graph.graph_from_bbox(bbox=tuple(place_or_bbox),
                                     network_type=network_type, simplify=simplify)
    else:
        G = ox.graph.graph_from_place(place_or_bbox,
                                      network_type=network_type, simplify=simplify)
    return G


def _first(v, default=None):
    """OSM tags are sometimes a list when ways were merged during simplify."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else default
    return v if v is not None else default


def _parse_maxspeed(v) -> Optional[float]:
    v = _first(v)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    mph = "mph" in s
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    kmph = float(digits) * (1.60934 if mph else 1.0)
    return kmph if 5 <= kmph <= 130 else None


def _edge_speed(data: dict) -> float:
    ms = _parse_maxspeed(data.get("maxspeed"))
    if ms:
        return ms
    hw = _first(data.get("highway"), "road")
    return float(DEFAULT_SPEED_KMPH.get(hw, FALLBACK_SPEED_KMPH))


def compile_graph(G) -> "RoadNetwork":
    """NetworkX MultiDiGraph (OSMnx shape) -> the compact arrays we route on.

    OSMnx nodes carry `x` (lon) and `y` (lat); edges carry `length` in metres
    plus `highway` and sometimes `maxspeed`. Everything else is dropped -- the
    dispatcher never needs street names.
    """
    nodes = list(G.nodes())
    idx: Dict[object, int] = {nid: i for i, nid in enumerate(nodes)}
    n = len(nodes)

    lat = np.empty(n, dtype=np.float64)
    lon = np.empty(n, dtype=np.float64)
    for nid, i in idx.items():
        d = G.nodes[nid]
        lon[i] = float(d["x"])
        lat[i] = float(d["y"])

    rows: List[int] = []
    cols: List[int] = []
    minutes: List[float] = []        # base travel time, wheeled, dry
    hw_ok_heavy: List[bool] = []

    for u, v, data in G.edges(data=True):
        length_m = float(_first(data.get("length"), 0.0) or 0.0)
        if length_m <= 0:
            continue
        spd = _edge_speed(data)
        t = (length_m / 1000.0) / spd * 60.0
        rows.append(idx[u]); cols.append(idx[v]); minutes.append(t)
        hw = _first(data.get("highway"), "road")
        hw_ok_heavy.append(hw not in HEAVY_BANNED)

        # OSMnx gives a directed graph; a two-way street is already two edges.
        # If the source was undirected, mirror it so routing is symmetric.
        if not G.is_directed():
            rows.append(idx[v]); cols.append(idx[u]); minutes.append(t)
            hw_ok_heavy.append(hw not in HEAVY_BANNED)

    return RoadNetwork(
        lat=lat, lon=lon,
        row=np.asarray(rows, dtype=np.int32),
        col=np.asarray(cols, dtype=np.int32),
        base_min=np.asarray(minutes, dtype=np.float64),
        heavy_ok=np.asarray(hw_ok_heavy, dtype=bool),
        node_ids=np.asarray(nodes, dtype=object),
    )


# ==========================================================================
# STAGE 2 & 3 -- LOAD and QUERY
# ==========================================================================
@dataclass
class Zone:
    """A flooded / blocked area. severity 5 == impassable to anything wheeled."""
    lat: float
    lon: float
    radius_km: float
    severity: int


@dataclass
class RoadNetwork:
    lat: np.ndarray
    lon: np.ndarray
    row: np.ndarray
    col: np.ndarray
    base_min: np.ndarray
    heavy_ok: np.ndarray
    node_ids: np.ndarray

    _tree: Optional[cKDTree] = field(default=None, repr=False)
    _csr: Dict[str, sp.csr_matrix] = field(default_factory=dict, repr=False)
    _cache: Dict[Tuple[int, str], np.ndarray] = field(default_factory=dict, repr=False)
    _zones: List[Zone] = field(default_factory=list, repr=False)

    # ---------------- persistence ----------------
    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump({k: getattr(self, k) for k in
                         ("lat", "lon", "row", "col", "base_min", "heavy_ok", "node_ids")},
                        f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str) -> "RoadNetwork":
        with open(path, "rb") as f:
            net = cls(**pickle.load(f))
        net.rebuild()
        return net

    @property
    def n_nodes(self) -> int:
        return self.lat.size

    @property
    def n_edges(self) -> int:
        return self.row.size

    # ---------------- snapping ----------------
    def _ensure_tree(self) -> None:
        if self._tree is None:
            # Project to local flat metres so nearest-node is true distance,
            # not degrees -- a degree of longitude is ~30% shorter than a
            # degree of latitude at 20 N, which matters when snapping.
            latf = 111.32
            lonf = 111.32 * math.cos(math.radians(float(np.mean(self.lat))))
            self._tree = cKDTree(np.column_stack([self.lon * lonf, self.lat * latf]))
            self._proj = (lonf, latf)

    def snap(self, lats, lons) -> np.ndarray:
        """lat/lon -> nearest graph node index. Vectorised; microseconds."""
        self._ensure_tree()
        lonf, latf = self._proj
        pts = np.column_stack([np.asarray(lons, float) * lonf,
                               np.asarray(lats, float) * latf])
        _, idx = self._tree.query(pts)
        return np.atleast_1d(idx)

    # ---------------- dynamic weights ----------------
    def apply_zones(self, zones: Sequence[Zone]) -> None:
        """Reweight for the current flood picture. Rebuilds the CSR matrices
        and drops the Dijkstra cache -- the only expensive thing that happens
        at run time, and it happens when a road is cut, not when a report
        arrives."""
        self._zones = list(zones)
        self.rebuild()

    def rebuild(self) -> None:
        self._cache.clear()
        self._csr.clear()
        n = self.n_nodes

        # Edge midpoints, used to test each edge against each zone.
        mlat = 0.5 * (self.lat[self.row] + self.lat[self.col])
        mlon = 0.5 * (self.lon[self.row] + self.lon[self.col])

        slow = np.ones(self.n_edges, dtype=np.float64)   # wheeled multiplier
        cut = np.zeros(self.n_edges, dtype=bool)         # wheeled impassable
        wet = np.zeros(self.n_edges, dtype=bool)         # boat-navigable

        for z in self._zones:
            latf = 111.32
            lonf = 111.32 * math.cos(math.radians(z.lat))
            d = np.hypot((mlon - z.lon) * lonf, (mlat - z.lat) * latf)
            inside = d < z.radius_km
            if not inside.any():
                continue
            wet |= inside
            if z.severity >= 5:
                cut |= inside
            else:
                slow = np.maximum(slow, np.where(inside, 1.0 + 0.25 * z.severity, 1.0))

        INF = np.inf

        # WHEELED: slowed inside soft zones, gone inside severity-5 zones.
        w = self.base_min * slow
        w = np.where(cut, INF, w)
        self._csr[WHEELED] = self._csr_from(w)

        # HEAVY: same, plus banned way types and a blanket speed penalty.
        h = self.base_min * slow / HEAVY_SPEED_FACTOR
        h = np.where(cut | ~self.heavy_ok, INF, h)
        self._csr[HEAVY] = self._csr_from(h)

        # BOAT: the inverse relationship to water. Flooded roads become
        # navigable channels -- slower than a dry road but passable, and often
        # the only way in. Dry roads are unusable to a boat on a trailer only
        # in the sense that it is being towed, so keep them at a penalty
        # rather than banning them.
        b = np.where(wet, self.base_min * 1.6, self.base_min * 2.2)
        self._csr[BOAT] = self._csr_from(b)

    def _csr_from(self, weights: np.ndarray) -> sp.csr_matrix:
        finite = np.isfinite(weights)
        n = self.n_nodes
        return sp.csr_matrix(
            (weights[finite], (self.row[finite], self.col[finite])), shape=(n, n))

    # ---------------- routing ----------------
    def costs_from(self, origin_node: int, vclass: str = WHEELED) -> np.ndarray:
        """Travel minutes from one origin to EVERY node. Cached.

        This is the whole trick: one Dijkstra per distinct origin, not one per
        (unit, incident) pair. A newly arrived report then costs zero routing
        work -- its ETA from every unit is an array lookup."""
        key = (int(origin_node), vclass)
        hit = self._cache.get(key)
        if hit is None:
            hit = dijkstra(self._csr[vclass], indices=int(origin_node), directed=True)
            self._cache[key] = hit
        return hit

    def warm(self, origin_nodes: Iterable[int],
             vclasses: Sequence[str] = VEHICLE_CLASSES) -> float:
        """Precompute for the depots and shelters. Call at boot and after any
        apply_zones(). Returns seconds spent."""
        t0 = time.perf_counter()
        for vc in vclasses:
            for nd in origin_nodes:
                self.costs_from(nd, vc)
        return time.perf_counter() - t0

    def eta_matrix(self, incident_nodes: Sequence[int],
                   unit_nodes: Sequence[int],
                   unit_classes: Sequence[str]) -> np.ndarray:
        """(n_incidents x n_units) travel minutes. inf where unreachable.

        Feed this straight into the cost matrix in engine.py:
            cost[i][j] = w_i * (eta[i][j] - T_HORIZON)
        """
        inc = np.asarray(incident_nodes, dtype=np.int64)
        out = np.empty((inc.size, len(unit_nodes)), dtype=np.float64)
        for j, (nd, vc) in enumerate(zip(unit_nodes, unit_classes)):
            out[:, j] = self.costs_from(int(nd), vc)[inc]
        return out
