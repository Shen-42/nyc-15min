"""The walking graph the server keeps in memory.

Nodes are street intersections and points along paths. Edges are walkable
segments between them, with a length in meters. Walking works both ways, so
every edge is added in both directions.
"""

import json
import math
from pathlib import Path

EARTH_RADIUS_M = 6_371_000


def distance_m(lat1, lng1, lat2, lng2):
    """Straight-line distance between two points in meters (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class WalkGraph:
    def __init__(self, nodes, edges):
        """nodes: list of [id, lat, lng]. edges: list of [node_a, node_b, length_m]."""
        self.coords = {node_id: (lat, lng) for node_id, lat, lng in nodes}
        # Adjacency list: node id -> list of (neighbor id, length in meters).
        self.adj = {node_id: [] for node_id in self.coords}
        for a, b, length in edges:
            self.adj[a].append((b, length))
            self.adj[b].append((a, length))
        self.edge_count = len(edges)

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

    def nearest_node(self, lat, lng):
        """Return (node id, distance in meters) of the node closest to a point.

        Checks every node, which takes a few milliseconds for Manhattan.
        A grid or k-d tree would be faster if it ever matters.
        """
        best_id, best_dist = None, math.inf
        for node_id, (node_lat, node_lng) in self.coords.items():
            d = distance_m(lat, lng, node_lat, node_lng)
            if d < best_dist:
                best_id, best_dist = node_id, d
        return best_id, best_dist
