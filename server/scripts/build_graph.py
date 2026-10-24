"""Build Manhattan's walking graph from OpenStreetMap (card 3).

Run once from the server folder, with the virtual environment active:
    pip install -r requirements-build.txt
    python scripts/build_graph.py

It writes data/walk_graph.json. The server reads that file when it starts
and does not need OSMnx itself.
"""

import json
import time
from datetime import date
from pathlib import Path

import networkx as nx
import osmnx as ox
from shapely.geometry import Polygon
from shapely.ops import unary_union

import overpass  # scripts/overpass.py: server choice and retries

SERVER_DIR = Path(__file__).resolve().parent.parent
BOUNDARY_FILE = SERVER_DIR.parent / "client" / "src" / "data" / "manhattan-boundary.json"
OUTPUT_FILE = SERVER_DIR / "data" / "walk_graph.json"

# The same land the map lets you click on (see client/src/data/manhattan.js).
LAND = ["main", "roosevelt"]

# Grow the outline by about 50 m so waterfront paths and piers aren't cut off.
BUFFER_DEGREES = 0.0005

# Drop disconnected bits of the graph smaller than this, such as a path on a
# pier or inside a courtyard that doesn't connect to any street.
MIN_COMPONENT_NODES = 50


def load_area():
    boundary = json.loads(BOUNDARY_FILE.read_text())
    # The JSON stores [lat, lng]. Shapely wants (x, y), which is (lng, lat).
    polygons = [Polygon([(lng, lat) for lat, lng in boundary[name]]) for name in LAND]
    return unary_union(polygons).buffer(BUFFER_DEGREES)


def main():
    overpass.configure()

    area = load_area()
    print("Downloading Manhattan's walkable streets. This can take a few minutes...")
    start = time.time()
    G = overpass.download("walking graph", lambda: ox.graph_from_polygon(
        area,
        network_type="walk",
        retain_all=True,  # keep Roosevelt Island, which has no walking link to Manhattan
        truncate_by_edge=True,
    ))
    print(f"Downloaded {len(G.nodes):,} nodes and {len(G.edges):,} edges in {time.time() - start:.0f}s")

    keep = set()
    for component in nx.weakly_connected_components(G):
        if len(component) >= MIN_COMPONENT_NODES:
            keep |= component
    dropped = len(G.nodes) - len(keep)
    G = G.subgraph(keep).copy()
    print(f"Dropped {dropped:,} nodes in small disconnected pieces")

    nodes = [[int(n), round(d["y"], 6), round(d["x"], 6)] for n, d in G.nodes(data=True)]

    # OSMnx stores a two-way path as two edges (A to B and B to A), and there can
    # be more than one path between the same two nodes. Walking works both ways,
    # so store each pair once, keeping the shortest.
    #
    # OSMnx also merges the points along a curved path into one edge and keeps
    # the curve in a "geometry" attribute, running from u to v. Save the points
    # in between so the map can draw the real path, not a straight line.
    best = {}
    for u, v, d in G.edges(data=True):
        if u == v:
            continue
        key = (min(u, v), max(u, v))
        if key not in best or d["length"] < best[key][0]:
            geom = d.get("geometry")
            between = [[round(y, 6), round(x, 6)] for x, y in geom.coords[1:-1]] if geom is not None else []
            best[key] = (d["length"], u, v, between)

    edges = []
    for length, u, v, between in best.values():
        edge = [int(u), int(v), round(length, 1)]
        if between:
            edge.append(between)  # [[lat, lng], ...] from u to v, ends left out
        edges.append(edge)

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "meta": {
                    "source": "OpenStreetMap contributors, via OSMnx",
                    "network_type": "walk",
                    "built": date.today().isoformat(),
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                },
                "nodes": nodes,  # [id, lat, lng]
                "edges": edges,  # [node_a, node_b, length_m, optional points between]
            },
            separators=(",", ":"),
        )
    )
    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"Saved {len(nodes):,} nodes and {len(edges):,} edges to {OUTPUT_FILE} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
