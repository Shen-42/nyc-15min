"""The walking graph the server keeps in memory.

Nodes are street intersections and points along paths. Edges are walkable
segments between them, with a length in meters. Walking works both ways, so
every edge can be walked in both directions.

The graph is kept as NumPy arrays rather than Python dicts and lists
(card 15). For all five boroughs that's 62 MB instead of 366 MB, and the
file loads in 0.2 s instead of 8. The search itself is scipy's Dijkstra.
Node ids are OpenStreetMap ids everywhere outside this file, as before.
"""

import json
import math
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

EARTH_RADIUS_M = 6_371_000

# Average walking pace: 80 meters per minute is about 3 mph or 4.8 km/h.
WALK_SPEED_M_PER_MIN = 80

# nearest_node checks this many of the closest nodes on a flat map, then
# picks the closest by true distance, so flattening never picks wrong.
NEAREST_CANDIDATES = 8

# Copies of the graph in minutes to keep: walking, and one per wheelchair
# setup (card 11). Each is about 8 MB for all five boroughs.
MAX_SEARCH_GRAPHS = 4


def distance_m(lat1, lng1, lat2, lng2):
    """Straight-line distance between two points in meters (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class Coords(Mapping):
    """node id -> (lat, lng). Reads the arrays, and works like the dict it replaced."""

    def __init__(self, graph):
        self._graph = graph

    def __getitem__(self, node_id):
        i = self._graph._index(node_id)
        return (float(self._graph.lat[i]), float(self._graph.lng[i]))

    def __iter__(self):
        return iter(self._graph.ids.tolist())

    def __len__(self):
        return len(self._graph.ids)

    def __contains__(self, node_id):
        try:
            self._graph._index(node_id)
        except KeyError:
            return False
        return True

    def values(self):
        return list(zip(self._graph.lat.tolist(), self._graph.lng.tolist()))

    def items(self):
        return list(zip(self._graph.ids.tolist(), self.values()))


class WalkGraph:
    def __init__(self, nodes, edges, meta=None, curb_nodes=(), streets=None):
        """nodes: list of [id, lat, lng].
        edges: list of [node_a, node_b, length_m], optionally followed by the
        [lat, lng] points along a curved path from node_a to node_b.
        """
        ids = np.array([n[0] for n in nodes], dtype=np.int64)
        order = np.argsort(ids, kind="stable")
        ids = ids[order]
        lat = np.array([n[1] for n in nodes], dtype=np.float64)[order]
        lng = np.array([n[2] for n in nodes], dtype=np.float64)[order]

        def index(node_ids):
            return np.searchsorted(ids, np.array(node_ids, dtype=np.int64)).astype(np.int32)

        counts = [len(e[3]) if len(e) > 3 else 0 for e in edges]
        points = [p for e in edges if len(e) > 3 for p in e[3]]
        self._setup(
            ids=ids,
            lat=lat,
            lng=lng,
            edge_a=index([e[0] for e in edges]),
            edge_b=index([e[1] for e in edges]),
            edge_length=np.array([e[2] for e in edges], dtype=np.float64),
            shape_start=np.concatenate([[0], np.cumsum(counts, dtype=np.int64)]).astype(np.int64),
            shape_points=np.array(points, dtype=np.float64).reshape(-1, 2),
            meta=meta or {},
            curb_nodes=list(curb_nodes),
            streets=streets or {},
        )

    def _setup(self, ids, lat, lng, edge_a, edge_b, edge_length, shape_start, shape_points, meta, curb_nodes, streets):
        self.ids, self.lat, self.lng = ids, lat, lng
        # Edges by position in `ids`. Edge k's curve points (from a to b, ends
        # left out) are shape_points[shape_start[k]:shape_start[k + 1]].
        self.edge_a, self.edge_b, self.edge_length = edge_a, edge_b, edge_length
        self.shape_start, self.shape_points = shape_start, shape_points
        self.meta = meta
        self.curb_nodes = curb_nodes  # where you step off a curb (card 11)
        self.streets = streets  # {node id: street names} at intersections (card 12)
        self.coords = Coords(self)

        # Both directions of every edge, grouped by start node (CSR): node i's
        # neighbors are col[indptr[i]:indptr[i + 1]], at lengths weight[...].
        n = len(ids)
        src = np.concatenate([edge_a, edge_b])
        dst = np.concatenate([edge_b, edge_a])
        order = np.argsort(src, kind="stable")
        self.indptr = np.concatenate([[0], np.cumsum(np.bincount(src, minlength=n))]).astype(np.int32)
        self.col = dst[order].astype(np.int32)
        # 64-bit on purpose: given 32-bit, scipy copies the whole graph to
        # 64-bit on every search, which made each one about 10x slower.
        self.weight = np.concatenate([edge_length, edge_length])[order]
        self.edge_of = np.concatenate([np.arange(len(edge_a)), np.arange(len(edge_a))])[order].astype(np.int32)
        # The search runs on copies of the graph in minutes, one per speed
        # (and wheelchair penalty table), made when first needed.
        self._minute_graphs = {}
        self._in_minutes(WALK_SPEED_M_PER_MIN, None)

        # Nearest-node index on a flat map in meters. Fine at city scale; the
        # final pick uses the true distance.
        self._lat0 = float(lat.mean()) if n else 40.75
        self._x_scale = 111_320 * math.cos(math.radians(self._lat0))
        self._tree = cKDTree(np.column_stack([lng * self._x_scale, lat * 111_320])) if n else None

    @classmethod
    def from_file(cls, path):
        """Load a graph saved by save() (.npz), or the older JSON format."""
        path = Path(path)
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            return cls(data["nodes"], data["edges"], data.get("meta"), data.get("curb_nodes", ()), data.get("streets"))
        with np.load(path, allow_pickle=False) as d:
            graph = cls.__new__(cls)
            graph._setup(
                ids=d["ids"],
                lat=d["lat"],
                lng=d["lng"],
                edge_a=d["edge_a"],
                edge_b=d["edge_b"],
                edge_length=d["edge_length"],
                shape_start=d["shape_start"],
                shape_points=d["shape_points"],
                meta=json.loads(str(d["meta"])),
                curb_nodes=d["curb_nodes"].tolist(),
                streets=json.loads(str(d["streets"])),
            )
        return graph

    def save(self, path):
        """Write the graph as one .npz file that from_file() reads."""
        np.savez(
            path,
            ids=self.ids,
            lat=self.lat,
            lng=self.lng,
            edge_a=self.edge_a,
            edge_b=self.edge_b,
            edge_length=self.edge_length,
            shape_start=self.shape_start,
            shape_points=self.shape_points,
            meta=np.array(json.dumps(self.meta)),
            curb_nodes=np.array(self.curb_nodes, dtype=np.int64),
            streets=np.array(json.dumps(self.streets, separators=(",", ":"))),
        )

    def __len__(self):
        return len(self.ids)

    @property
    def edge_count(self):
        return len(self.edge_a)

    @property
    def curved_edge_count(self):
        """How many edges keep the points along a curved path."""
        return int(np.count_nonzero(np.diff(self.shape_start)))

    def _index(self, node_id):
        """Position of an OpenStreetMap node id in the arrays. KeyError if absent."""
        i = int(np.searchsorted(self.ids, node_id))
        if i < len(self.ids) and self.ids[i] == node_id:
            return i
        raise KeyError(node_id)

    def neighbors(self, node_id):
        """List of (neighbor id, length in meters)."""
        i = self._index(node_id)
        lo, hi = self.indptr[i], self.indptr[i + 1]
        return list(zip(self.ids[self.col[lo:hi]].tolist(), self.weight[lo:hi].tolist()))

    def edge_points(self, a, b):
        """The path from node a to node b as (lat, lng) points, both ends included."""
        i, j = self._index(a), self._index(b)
        lo, hi = self.indptr[i], self.indptr[i + 1]
        found = np.flatnonzero(self.col[lo:hi] == j)
        between = []
        if len(found):
            k = self.edge_of[lo + found[0]]
            between = [tuple(p) for p in self.shape_points[self.shape_start[k]:self.shape_start[k + 1]].tolist()]
            if self.edge_a[k] != i:
                between.reverse()
        return [self.coords[a], *between, self.coords[b]]

    def nearest_node(self, lat, lng):
        """Return (node id, distance in meters) of the node closest to a point."""
        k = min(NEAREST_CANDIDATES, len(self.ids))
        _, found = self._tree.query([lng * self._x_scale, lat * 111_320], k=k)
        best_i, best_dist = None, math.inf
        for i in np.atleast_1d(found).tolist():
            d = distance_m(lat, lng, self.lat[i], self.lng[i])
            if d < best_dist:
                best_i, best_dist = i, d
        return int(self.ids[best_i]), best_dist

    def nearby_nodes(self, lat, lng, k):
        """The k nodes nearest a point, nearest first, as [(node id, lat, lng, meters)]."""
        k = min(k, len(self.ids))
        _, found = self._tree.query([lng * self._x_scale, lat * 111_320], k=k)
        near = [
            (int(self.ids[i]), float(self.lat[i]), float(self.lng[i]), distance_m(lat, lng, self.lat[i], self.lng[i]))
            for i in np.atleast_1d(found).tolist()
        ]
        return sorted(near, key=lambda n: n[3])

    def reachable_within(self, start, max_minutes, speed_m_per_min=WALK_SPEED_M_PER_MIN, node_penalty=None):
        """Every node you can walk to from `start` within `max_minutes`.

        Returns a dict {node_id: minutes to walk there}, including the start
        node at 0. Nodes farther than max_minutes are left out.

        speed_m_per_min: walking pace by default; slower for a wheelchair (card 11).
        node_penalty: optional {node_id: extra minutes} added when passing
        through a node, such as a corner with no curb ramp (card 11).

        This is Dijkstra's algorithm with a cutoff, run by scipy in compiled
        code. Its `limit` stops the search at the time budget, so it only
        visits the ~1,600 nodes within reach, not the whole city. Edges are
        in minutes, so the sums are the same, to the last digit, as adding
        up minutes in Python the way this method used to.
        """
        i = self._index(start)
        if max_minutes < 0:
            return {start: 0}
        dist = dijkstra(self._in_minutes(speed_m_per_min, node_penalty), directed=True, indices=i, limit=max_minutes)
        hit = np.flatnonzero(dist <= max_minutes)
        return dict(zip(self.ids[hit].tolist(), dist[hit].tolist()))

    def _in_minutes(self, speed_m_per_min, node_penalty):
        """The graph with each edge in minutes at this speed, plus the penalty
        for entering a node, if any. Made once per speed and penalty table."""
        penalty = node_penalty or None
        key = (speed_m_per_min, id(penalty), len(penalty or ()))
        cached = self._minute_graphs.get(key)
        if cached is not None and cached[0] is penalty:
            return cached[1]
        minutes = self.weight / speed_m_per_min
        if penalty:
            extra = np.zeros(len(self.ids))
            nodes = np.fromiter(penalty.keys(), dtype=np.int64, count=len(penalty))
            added = np.fromiter(penalty.values(), dtype=np.float64, count=len(penalty))
            at = np.minimum(np.searchsorted(self.ids, nodes), len(self.ids) - 1)
            known = self.ids[at] == nodes
            extra[at[known]] = added[known]
            minutes = minutes + extra[self.col]
        n = len(self.ids)
        matrix = csr_matrix((minutes, self.col, self.indptr), shape=(n, n))
        if len(self._minute_graphs) >= MAX_SEARCH_GRAPHS:
            # Start over, keeping walking at the usual pace.
            self._minute_graphs = {k: v for k, v in self._minute_graphs.items() if k[0] == WALK_SPEED_M_PER_MIN and k[1] == id(None)}
        # The table itself is kept too, so its id can't be reused by another.
        self._minute_graphs[key] = (penalty, matrix)
        return matrix
