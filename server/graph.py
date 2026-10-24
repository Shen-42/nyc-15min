"""The walking graph the server keeps in memory.

Nodes are street intersections and points along paths. Edges are walkable
segments between them, with a length in meters. Walking works both ways, so
every edge is added in both directions.
"""

import heapq  # priority queue for Dijkstra
import json
import math
from collections import defaultdict
from pathlib import Path

EARTH_RADIUS_M = 6_371_000

# Average walking pace: 80 meters per minute is about 3 mph or 4.8 km/h.
WALK_SPEED_M_PER_MIN = 80

# Size of one grid cell for the nearest-node index, in degrees.
# 0.002 degrees is about 220 m north-south and 170 m east-west in Manhattan.
GRID_DEG = 0.002


def distance_m(lat1, lng1, lat2, lng2):
    """Straight-line distance between two points in meters (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class WalkGraph:
    def __init__(self, nodes, edges):
        """nodes: list of [id, lat, lng].
        edges: list of [node_a, node_b, length_m], optionally followed by the
        [lat, lng] points along a curved path from node_a to node_b.
        """
        self.coords = {node_id: (lat, lng) for node_id, lat, lng in nodes}
        # Adjacency list: node id -> list of (neighbor id, length in meters).
        self.adj = {node_id: [] for node_id in self.coords}
        # Points along curved paths, only used for drawing: (a, b) -> [[lat, lng], ...]
        self.shapes = {}
        for a, b, length, *between in edges:
            self.adj[a].append((b, length))
            self.adj[b].append((a, length))
            if between:
                self.shapes[(a, b)] = between[0]
        self.edge_count = len(edges)
        self.meta = {}

        # Spatial index: the map is cut into GRID_DEG squares, and each square
        # lists the nodes inside it. nearest_node then only checks the squares
        # around a point instead of all ~37,000 nodes.
        self.grid = defaultdict(list)
        for node_id, (lat, lng) in self.coords.items():
            self.grid[self._cell(lat, lng)].append(node_id)

    @classmethod
    def from_file(cls, path):
        data = json.loads(Path(path).read_text())
        graph = cls(data["nodes"], data["edges"])
        graph.meta = data.get("meta", {})
        return graph

    def __len__(self):
        return len(self.coords)

    def neighbors(self, node_id):
        """List of (neighbor id, length in meters). Card 4's Dijkstra uses this."""
        return self.adj[node_id]

    def edge_points(self, a, b):
        """The path from node a to node b as (lat, lng) points, both ends included."""
        if (a, b) in self.shapes:
            between = self.shapes[(a, b)]
        elif (b, a) in self.shapes:
            between = self.shapes[(b, a)][::-1]
        else:
            between = []
        return [self.coords[a], *(tuple(p) for p in between), self.coords[b]]

    @staticmethod
    def _cell(lat, lng):
        return (math.floor(lat / GRID_DEG), math.floor(lng / GRID_DEG))

    def nearest_node(self, lat, lng):
        """Return (node id, distance in meters) of the node closest to a point.

        Searches the grid in growing square rings around the point's cell:
        first the cell itself, then the 8 around it, then the 16 around those.
        Any node outside ring r is at least r cells away, so once the best
        node found is closer than r cells, no farther ring can beat it.
        """
        ci, cj = self._cell(lat, lng)
        # Meters per cell in the narrower direction (east-west), so the
        # stopping rule never stops too early.
        cell_m = GRID_DEG * 111_320 * math.cos(math.radians(lat))
        best_id, best_dist = None, math.inf
        max_ring = 200  # about 35 km: farther than anything in Manhattan

        for r in range(max_ring + 1):
            for i in range(ci - r, ci + r + 1):
                for j in range(cj - r, cj + r + 1):
                    if max(abs(i - ci), abs(j - cj)) != r:
                        continue  # inner rings were already checked
                    for node_id in self.grid.get((i, j), ()):
                        node_lat, node_lng = self.coords[node_id]
                        d = distance_m(lat, lng, node_lat, node_lng)
                        if d < best_dist:
                            best_id, best_dist = node_id, d
            if best_id is not None and best_dist <= r * cell_m:
                break
        return best_id, best_dist

    def reachable_within(self, start, max_minutes):
        """Every node you can walk to from `start` within `max_minutes`.

        Returns a dict {node_id: minutes to walk there}, including the start
        node at 0. Nodes farther than max_minutes are left out.

        This is Dijkstra's algorithm with a cutoff. One way to write it:

        1. Make a priority queue as a plain list and push (0, start) onto it.
           heapq.heappush(queue, item) adds an item and heapq.heappop(queue)
           removes the item with the smallest first value. Tuples compare by
           their first value, so (minutes, node) pops the closest node first.
        2. Make a dict `best` that holds the shortest time found so far for
           each node. Set best[start] = 0.
        3. While the queue isn't empty:
             a. Pop (minutes, node).
             b. If minutes > best[node], skip this entry. It's an old one,
                pushed before a shorter route to the same node was found.
             c. For each (neighbor, length_m) in self.neighbors(node):
                  new_minutes = minutes + length_m / WALK_SPEED_M_PER_MIN
                  If new_minutes > max_minutes, skip it: too far.
                  If neighbor isn't in best, or new_minutes < best[neighbor],
                  set best[neighbor] = new_minutes and push it onto the queue.
        4. Return best.

        Run `pytest test_reachable.py` to check it.
        """
        queue = [(0, start)]  # (minutes, node), closest first
        best = {start: 0}  # shortest known time to each node

        while queue:
            minutes, node = heapq.heappop(queue)

            # A shorter route to this node was found after this entry was pushed.
            if minutes > best[node]:
                continue

            for neighbor, length_m in self.neighbors(node):
                new_minutes = minutes + length_m / WALK_SPEED_M_PER_MIN
                if new_minutes > max_minutes:
                    continue  # too far
                if neighbor not in best or new_minutes < best[neighbor]:
                    best[neighbor] = new_minutes
                    heapq.heappush(queue, (new_minutes, neighbor))

        return best
