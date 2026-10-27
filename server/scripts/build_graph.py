"""Build Manhattan's walking graph from OpenStreetMap (card 3).

Run once from the server folder, with the virtual environment active:
    pip install -r requirements-build.txt
    python scripts/build_graph.py

It writes data/walk_graph.json. The server reads that file when it starts
and does not need OSMnx itself.
"""

import json
import time
from collections import defaultdict
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

# Streets that cars use, so crossing them means stepping off a curb (card 11).
STREET_TYPES = {
    "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "unclassified", "living_street",
}

# Drop disconnected bits of the graph smaller than this, such as a path on a
# pier or inside a courtyard that doesn't connect to any street.
MIN_COMPONENT_NODES = 50


def load_area():
    boundary = json.loads(BOUNDARY_FILE.read_text())
    # The JSON stores [lat, lng]. Shapely wants (x, y), which is (lng, lat).
    polygons = [Polygon([(lng, lat) for lat, lng in boundary[name]]) for name in LAND]
    return unary_union(polygons).buffer(BUFFER_DEGREES)


def as_set(value):
    """OSMnx gives a tag as a string, or a list when merged ways disagree."""
    if value is None:
        return set()
    return set(value) if isinstance(value, list) else {value}


def curb_nodes(G):
    """Nodes where a wheelchair user has to get off or onto a curb (card 11):
    street intersections (three or more street segments meet), and both ends
    of a mapped crosswalk (footway=crossing)."""
    street_neighbors = defaultdict(set)
    crossings = set()
    for u, v, d in G.edges(data=True):
        if as_set(d.get("highway")) & STREET_TYPES:
            street_neighbors[u].add(v)
            street_neighbors[v].add(u)
        if "crossing" in as_set(d.get("footway")):
            crossings |= {u, v}
    intersections = {n for n, nbrs in street_neighbors.items() if len(nbrs) >= 3}
    return sorted(int(n) for n in intersections | crossings)


def intersection_names(G):
    """{node id: [street names]} for intersections of two or more named
    streets, so a spot can be described as "W 125th St & Lenox Ave" (card 12)."""
    names = defaultdict(set)
    for u, v, d in G.edges(data=True):
        if as_set(d.get("highway")) & STREET_TYPES:
            for name in as_set(d.get("name")):
                names[u].add(name)
                names[v].add(name)
    return {str(int(n)): sorted(found) for n, found in names.items() if len(found) >= 2}


def main():
    overpass.configure()
    # Keep the footway tag, which OSMnx drops by default, to find crosswalks.
    # A cached download already has every tag, so this needs no new download.
    ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + ["footway"]

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

    curbs = curb_nodes(G)
    print(f"Found {len(curbs):,} street corners and crosswalk ends")
    streets = intersection_names(G)
    print(f"Named {len(streets):,} intersections")

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
                    "curb_count": len(curbs),
                },
                "nodes": nodes,  # [id, lat, lng]
                "edges": edges,  # [node_a, node_b, length_m, optional points between]
                "curb_nodes": curbs,  # nodes where you step off a curb (card 11)
                "streets": streets,  # {node id: street names} at intersections (card 12)
            },
            separators=(",", ":"),
        )
    )
    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"Saved {len(nodes):,} nodes and {len(edges):,} edges to {OUTPUT_FILE} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
